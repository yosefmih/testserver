import hashlib
import hmac
import json
import logging

from fastapi import APIRouter, Request, HTTPException, BackgroundTasks

from config import config
from db import get_pool
from services import linear_oauth
from services.sandbox_runner import launch_autopilot

router = APIRouter()
logger = logging.getLogger(__name__)

in_progress_issues: set[str] = set()


def _verify_signature(body: bytes, secret: str, signature: str) -> bool:
    expected = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature)


def _ignore(reason: str, **extra) -> dict:
    logger.info("Webhook ignored: %s %s", reason, " ".join(f"{k}={v}" for k, v in extra.items()) if extra else "")
    return {"status": "ignored", "reason": reason}


async def _resolve_issue_from_label_event(payload: dict) -> dict | None:
    """For IssueLabel events, fetch full issue details from Linear API."""
    data = payload.get("data", {})
    issue_id = data.get("issueId")
    if not issue_id:
        logger.warning("IssueLabel event missing issueId, payload data keys: %s", list(data.keys()))
        return None

    team_id = data.get("issue", {}).get("teamId")
    if not team_id:
        team_id = payload.get("teamId")

    pool = await get_pool()
    project = await pool.fetchrow("""
        SELECT linear_access_token FROM projects WHERE linear_team_id = $1
    """, team_id) if team_id else None

    if not project or not project["linear_access_token"]:
        projects = await pool.fetch("SELECT linear_team_id, linear_access_token FROM projects WHERE linear_access_token IS NOT NULL")
        for p in projects:
            issue = await linear_oauth.get_issue(p["linear_access_token"], issue_id)
            if issue:
                return issue
        return None

    return await linear_oauth.get_issue(project["linear_access_token"], issue_id)


@router.post("/linear")
async def linear_webhook(request: Request, background_tasks: BackgroundTasks):
    body = await request.body()
    signature = request.headers.get("Linear-Signature", "")

    if not _verify_signature(body, config.LINEAR_WEBHOOK_SECRET, signature):
        logger.warning("Webhook signature verification failed")
        raise HTTPException(status_code=401, detail="Invalid signature")

    payload = await request.json()
    event_type = payload.get("type")
    action = payload.get("action")

    logger.info("Webhook received: type=%s action=%s", event_type, action)
    logger.debug("Webhook payload: %s", json.dumps(payload, default=str)[:2000])

    if event_type == "IssueLabel":
        return await _handle_issue_label_event(payload, action, background_tasks)
    elif event_type == "Issue":
        return await _handle_issue_event(payload, action, background_tasks)
    else:
        return _ignore("unhandled event type", type=event_type)


async def _handle_issue_label_event(payload: dict, action: str, background_tasks: BackgroundTasks):
    data = payload.get("data", {})
    label_name = data.get("label", {}).get("name") or data.get("name", "")
    issue_id = data.get("issueId", "unknown")

    logger.info("IssueLabel event: action=%s label=%r issueId=%s data_keys=%s",
                action, label_name, issue_id, list(data.keys()))

    if action not in ("create",):
        return _ignore("IssueLabel action not relevant", action=action, label=label_name)

    pool = await get_pool()
    projects = await pool.fetch("SELECT autopilot_label FROM projects")
    autopilot_labels = {p["autopilot_label"] for p in projects}

    if label_name not in autopilot_labels:
        return _ignore("label is not an autopilot trigger", label=label_name, known_labels=autopilot_labels)

    logger.info("Autopilot label %r detected on issue %s, fetching issue details", label_name, issue_id)

    issue = await _resolve_issue_from_label_event(payload)
    if not issue:
        return _ignore("could not fetch issue details from Linear API", issue_id=issue_id)

    logger.info("Fetched issue: id=%s title=%r team=%s labels=%s",
                issue["id"], issue["title"], issue["teamId"],
                [l["name"] for l in issue["labels"]])

    return await _process_issue(issue, background_tasks)


async def _handle_issue_event(payload: dict, action: str, background_tasks: BackgroundTasks):
    issue_data = payload.get("data", {})
    issue_id = issue_data.get("id", "unknown")
    issue_title = issue_data.get("title", "")

    logger.info("Issue event: action=%s issue_id=%s title=%r", action, issue_id, issue_title[:80])

    if action not in ("create", "update"):
        return _ignore("action not handled", action=action, issue_id=issue_id)

    if action == "update":
        updated_from = payload.get("updatedFrom", {})
        old_label_ids = set(updated_from.get("labelIds", []))
        new_label_ids = set(issue_data.get("labelIds", []))
        logger.info("Update event: updatedFrom_keys=%s old_labels=%s new_labels=%s",
                     list(updated_from.keys()), old_label_ids, new_label_ids)
        if "labelIds" not in updated_from:
            return _ignore("labels not changed in this update", issue_id=issue_id, updatedFrom_keys=list(updated_from.keys()))
        if old_label_ids == new_label_ids:
            return _ignore("label set unchanged", issue_id=issue_id)

    issue = {
        "id": issue_data.get("id", ""),
        "title": issue_data.get("title", ""),
        "description": issue_data.get("description", ""),
        "url": issue_data.get("url", ""),
        "teamId": issue_data.get("teamId") or payload.get("teamId"),
        "labels": issue_data.get("labels", []),
    }

    return await _process_issue(issue, background_tasks)


async def _process_issue(issue: dict, background_tasks: BackgroundTasks):
    """Common path: we have a resolved issue, check project match and launch autopilot."""
    team_id = issue.get("teamId")
    issue_id = issue["id"]

    if not team_id:
        return _ignore("no team on issue", issue_id=issue_id)

    pool = await get_pool()
    project = await pool.fetchrow("""
        SELECT id, linear_access_token, autopilot_label,
               github_installation_id, github_repo
        FROM projects WHERE linear_team_id = $1
    """, team_id)

    if not project:
        return _ignore("no project for this team", team_id=team_id, issue_id=issue_id)

    labels = [l.get("name", "") for l in issue.get("labels", [])]
    logger.info("Issue labels: %s, autopilot_label=%r, project_id=%s",
                labels, project["autopilot_label"], project["id"])

    if project["autopilot_label"] not in labels:
        return _ignore("autopilot label not present", labels=labels, expected=project["autopilot_label"], issue_id=issue_id)

    if not project["github_installation_id"] or not project["github_repo"]:
        return _ignore("GitHub not configured", project_id=str(project["id"]), issue_id=issue_id)

    project_id = str(project["id"])
    guard_key = f"{project_id}:{issue_id}"
    if guard_key in in_progress_issues:
        return _ignore("already processing this issue", issue_id=issue_id, project_id=project_id)

    logger.info("Launching autopilot for issue %s (title=%r) in project %s", issue_id, issue["title"], project_id)

    job = await pool.fetchrow("""
        INSERT INTO jobs (project_id, linear_issue_id, linear_issue_title, linear_issue_url, status)
        VALUES ($1, $2, $3, $4, 'pending')
        RETURNING id
    """, project_id, issue_id, issue.get("title", ""), issue.get("url", ""))

    in_progress_issues.add(guard_key)

    background_tasks.add_task(
        _run_autopilot,
        project_id=project_id,
        job_id=str(job["id"]),
        issue_id=issue_id,
        issue_title=issue.get("title", ""),
        issue_description=issue.get("description", ""),
        issue_url=issue.get("url", ""),
        github_installation_id=project["github_installation_id"],
        github_repo=project["github_repo"],
        linear_access_token=project["linear_access_token"],
        guard_key=guard_key,
    )

    logger.info("Job %s created for issue %s", job["id"], issue_id)
    return {"status": "accepted", "job_id": str(job["id"])}


async def _run_autopilot(
    project_id: str,
    job_id: str,
    issue_id: str,
    issue_title: str,
    issue_description: str,
    issue_url: str,
    github_installation_id: int,
    github_repo: str,
    linear_access_token: str,
    guard_key: str,
):
    try:
        await launch_autopilot(
            job_id=job_id,
            issue_id=issue_id,
            issue_title=issue_title,
            issue_description=issue_description,
            issue_url=issue_url,
            github_installation_id=github_installation_id,
            github_repo=github_repo,
            linear_access_token=linear_access_token,
        )
    except Exception as e:
        logger.exception("Autopilot failed for job %s", job_id)
        pool = await get_pool()
        await pool.execute(
            "UPDATE jobs SET status = 'failed', error = $1, finished_at = now() WHERE id = $2",
            str(e), job_id,
        )
    finally:
        in_progress_issues.discard(guard_key)
