import hashlib
import hmac
import logging
from datetime import datetime, timezone, timedelta

from fastapi import APIRouter, Request, HTTPException

from config import config
from db import get_pool
from services import linear_oauth

router = APIRouter()
logger = logging.getLogger(__name__)


def _verify_hmac(body: bytes, secret: str, signature: str) -> bool:
    expected = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature)


def _ignore(reason: str, **extra) -> dict:
    logger.info("Webhook ignored: %s %s", reason, " ".join(f"{k}={v}" for k, v in extra.items()) if extra else "")
    return {"status": "ignored", "reason": reason}


# --- Linear webhook ---

@router.post("/linear")
async def linear_webhook(request: Request):
    body = await request.body()
    signature = request.headers.get("Linear-Signature", "")

    if not _verify_hmac(body, config.LINEAR_WEBHOOK_SECRET, signature):
        logger.warning("Linear webhook signature verification failed")
        raise HTTPException(status_code=401, detail="Invalid signature")

    payload = await request.json()
    event_type = payload.get("type")
    action = payload.get("action")
    organization_id = payload.get("organizationId")

    logger.info("Linear webhook: type=%s action=%s org=%s", event_type, action, organization_id)

    if not organization_id:
        return _ignore("no organizationId in payload")

    pool = await get_pool()
    project = await pool.fetchrow("""
        SELECT id, linear_access_token, autopilot_label, github_installation_id
        FROM projects WHERE linear_organization_id = $1
    """, organization_id)

    if not project:
        return _ignore("no project for this organization", org=organization_id)

    if event_type == "IssueLabel":
        return await _handle_issue_label(payload, action, project)
    elif event_type == "Issue":
        return await _handle_issue(payload, action, project)
    else:
        return _ignore("unhandled event type", type=event_type)


async def _handle_issue_label(payload: dict, action: str, project):
    data = payload.get("data", {})
    label_name = data.get("label", {}).get("name") or data.get("name", "")
    issue_id = data.get("issueId", "unknown")

    if action != "create":
        return _ignore("IssueLabel action not relevant", action=action)

    if label_name != project["autopilot_label"]:
        return _ignore("label mismatch", label=label_name, expected=project["autopilot_label"])

    issue = await linear_oauth.get_issue(project["linear_access_token"], issue_id)
    if not issue:
        return _ignore("could not fetch issue", issue_id=issue_id)

    return await _create_ticket_for_issue(issue, project)


async def _handle_issue(payload: dict, action: str, project):
    issue_data = payload.get("data", {})
    issue_id = issue_data.get("id", "unknown")

    if action not in ("create", "update"):
        return _ignore("action not handled", action=action)

    if action == "update":
        updated_from = payload.get("updatedFrom", {})
        if "labelIds" not in updated_from:
            return _ignore("labels not changed", issue_id=issue_id)
        old_ids = set(updated_from.get("labelIds", []))
        new_ids = set(issue_data.get("labelIds", []))
        if old_ids == new_ids:
            return _ignore("label set unchanged", issue_id=issue_id)

    issue = {
        "id": issue_data.get("id", ""),
        "title": issue_data.get("title", ""),
        "description": issue_data.get("description", ""),
        "url": issue_data.get("url", ""),
        "labels": issue_data.get("labels", []),
    }

    return await _create_ticket_for_issue(issue, project)


async def _create_ticket_for_issue(issue: dict, project):
    issue_id = issue["id"]
    project_id = str(project["id"])

    labels = [l.get("name", "") for l in issue.get("labels", [])]
    if project["autopilot_label"] not in labels:
        return _ignore("autopilot label not present", labels=labels)

    if not project["github_installation_id"]:
        return _ignore("GitHub not configured", project_id=project_id)

    pool = await get_pool()

    existing = await pool.fetchrow("""
        SELECT id, status FROM tickets
        WHERE project_id = $1 AND linear_issue_id = $2
    """, project_id, issue_id)

    if existing:
        if existing["status"] == "active":
            active_run = await pool.fetchrow("""
                SELECT id FROM runs
                WHERE ticket_id = $1 AND status IN ('pending', 'launching', 'running')
            """, str(existing["id"]))
            if active_run:
                return _ignore("ticket already has active run", issue_id=issue_id)
        return _ignore("ticket already exists", issue_id=issue_id, status=existing["status"])

    ticket = await pool.fetchrow("""
        INSERT INTO tickets (project_id, linear_issue_id, linear_issue_title,
                            linear_issue_description, linear_issue_url, status)
        VALUES ($1, $2, $3, $4, $5, 'active')
        RETURNING id
    """, project_id, issue_id, issue.get("title", ""),
       issue.get("description", ""), issue.get("url", ""))

    ticket_id = str(ticket["id"])

    await pool.execute("""
        INSERT INTO runs (ticket_id, kind, status) VALUES ($1, 'initial', 'pending')
    """, ticket_id)

    logger.info("Ticket %s created with initial run for issue %s", ticket_id, issue_id)
    return {"status": "accepted", "ticket_id": ticket_id}


# --- GitHub webhook ---

@router.post("/github")
async def github_webhook(request: Request):
    body = await request.body()
    signature = request.headers.get("X-Hub-Signature-256", "")

    if config.GITHUB_APP_WEBHOOK_SECRET:
        expected = "sha256=" + hmac.new(
            config.GITHUB_APP_WEBHOOK_SECRET.encode(), body, hashlib.sha256
        ).hexdigest()
        if not hmac.compare_digest(expected, signature):
            raise HTTPException(status_code=401, detail="Invalid signature")

    event = request.headers.get("X-GitHub-Event", "")
    payload = await request.json()

    logger.info("GitHub webhook: event=%s action=%s", event, payload.get("action"))

    if event == "pull_request_review_comment" and payload.get("action") == "created":
        return await _handle_pr_review_comment(payload)
    elif event == "pull_request":
        return await _handle_pr_event(payload)
    else:
        return _ignore("unhandled github event", event=event)


async def _handle_pr_review_comment(payload: dict):
    comment = payload.get("comment", {})
    pr = payload.get("pull_request", {})
    repo = payload.get("repository", {})

    repo_full_name = repo.get("full_name", "")
    pr_number = pr.get("number")
    comment_id = comment.get("id")
    author = comment.get("user", {}).get("login", "")
    body = comment.get("body", "")
    path = comment.get("path")
    position = comment.get("position")

    if not repo_full_name or not pr_number:
        return _ignore("missing repo or PR number")

    pool = await get_pool()
    ticket = await pool.fetchrow("""
        SELECT id FROM tickets
        WHERE pr_repo = $1 AND pr_number = $2 AND status = 'active'
    """, repo_full_name, pr_number)

    if not ticket:
        return _ignore("no active ticket for this PR", repo=repo_full_name, pr=pr_number)

    ticket_id = str(ticket["id"])

    await pool.execute("""
        INSERT INTO review_comments (ticket_id, github_comment_id, author, body, path, position)
        VALUES ($1, $2, $3, $4, $5, $6)
        ON CONFLICT (github_comment_id) DO NOTHING
    """, ticket_id, comment_id, author, body, path, position)

    debounce_until = datetime.now(timezone.utc) + timedelta(seconds=config.REVIEW_DEBOUNCE_SECONDS)
    await pool.execute("""
        UPDATE tickets SET debounce_until = $1, updated_at = now() WHERE id = $2
    """, debounce_until, ticket_id)

    logger.info("Review comment stored for ticket %s, debounce set to %s", ticket_id, debounce_until)
    return {"status": "accepted", "ticket_id": ticket_id}


async def _handle_pr_event(payload: dict):
    action = payload.get("action", "")
    pr = payload.get("pull_request", {})
    repo = payload.get("repository", {})

    repo_full_name = repo.get("full_name", "")
    pr_number = pr.get("number")
    merged = pr.get("merged", False)

    if action not in ("closed",):
        return _ignore("PR action not relevant", action=action)

    pool = await get_pool()
    ticket = await pool.fetchrow("""
        SELECT id FROM tickets
        WHERE pr_repo = $1 AND pr_number = $2 AND status = 'active'
    """, repo_full_name, pr_number)

    if not ticket:
        return _ignore("no active ticket for this PR")

    new_status = "merged" if merged else "closed"
    await pool.execute("""
        UPDATE tickets SET status = $1, debounce_until = NULL, updated_at = now() WHERE id = $2
    """, new_status, str(ticket["id"]))

    logger.info("Ticket %s marked as %s (PR %s/%d)", ticket["id"], new_status, repo_full_name, pr_number)
    return {"status": "updated", "ticket_status": new_status}
