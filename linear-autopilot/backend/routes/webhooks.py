import hashlib
import hmac
import logging

from fastapi import APIRouter, Request, HTTPException, BackgroundTasks

from config import config
from db import get_pool
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
    issue_data = payload.get("data", {})
    issue_id = issue_data.get("id", "unknown")
    issue_title = issue_data.get("title", "")

    logger.info(
        "Webhook received: type=%s action=%s issue_id=%s title=%r",
        event_type, action, issue_id, issue_title[:80] if issue_title else "",
    )

    if event_type != "Issue":
        return _ignore("not an issue event", type=event_type)

    if action not in ("create", "update"):
        return _ignore(f"action not handled", action=action, issue_id=issue_id)

    team_id = issue_data.get("teamId") or payload.get("teamId")
    if not team_id:
        return _ignore("no team in payload", issue_id=issue_id)

    pool = await get_pool()
    project = await pool.fetchrow("""
        SELECT id, linear_access_token, autopilot_label,
               github_installation_id, github_repo
        FROM projects WHERE linear_team_id = $1
    """, team_id)

    if not project:
        return _ignore("no project for this team", team_id=team_id, issue_id=issue_id)

    labels = [l.get("name", "") for l in issue_data.get("labels", [])]
    logger.info(
        "Issue labels: %s, autopilot_label=%r, project_id=%s",
        labels, project["autopilot_label"], project["id"],
    )
    if project["autopilot_label"] not in labels:
        return _ignore("autopilot label not present", labels=labels, expected=project["autopilot_label"], issue_id=issue_id)

    if action == "update":
        updated_from = payload.get("updatedFrom", {})
        old_label_ids = set(updated_from.get("labelIds", []))
        new_label_ids = set(issue_data.get("labelIds", []))
        logger.info(
            "Update event label check: old_label_ids=%s new_label_ids=%s updatedFrom_keys=%s",
            old_label_ids, new_label_ids, list(updated_from.keys()),
        )
        if not old_label_ids or old_label_ids == new_label_ids:
            return _ignore("labels not changed in this update", issue_id=issue_id, updatedFrom_keys=list(updated_from.keys()))

    if not project["github_installation_id"] or not project["github_repo"]:
        return _ignore("GitHub not configured", project_id=str(project["id"]), issue_id=issue_id)

    project_id = str(project["id"])
    guard_key = f"{project_id}:{issue_id}"
    if guard_key in in_progress_issues:
        return _ignore("already processing this issue", issue_id=issue_id, project_id=project_id)

    logger.info("Launching autopilot for issue %s (title=%r) in project %s", issue_id, issue_title, project_id)

    job = await pool.fetchrow("""
        INSERT INTO jobs (project_id, linear_issue_id, linear_issue_title, linear_issue_url, status)
        VALUES ($1, $2, $3, $4, 'pending')
        RETURNING id
    """, project_id, issue_id,
        issue_data.get("title", ""),
        issue_data.get("url", ""))

    in_progress_issues.add(guard_key)

    background_tasks.add_task(
        _run_autopilot,
        project_id=project_id,
        job_id=str(job["id"]),
        issue_id=issue_id,
        issue_title=issue_data.get("title", ""),
        issue_description=issue_data.get("description", ""),
        issue_url=issue_data.get("url", ""),
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
