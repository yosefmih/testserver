import hashlib
import hmac
import logging

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
        "identifier": issue_data.get("identifier"),
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
        INSERT INTO tickets (project_id, linear_issue_id, linear_issue_identifier,
                            linear_issue_title, linear_issue_description, linear_issue_url, status)
        VALUES ($1, $2, $3, $4, $5, $6, 'active')
        RETURNING id
    """, project_id, issue_id, issue.get("identifier"),
       issue.get("title", ""), issue.get("description", ""), issue.get("url", ""))

    ticket_id = str(ticket["id"])

    await pool.execute("""
        INSERT INTO runs (ticket_id, kind, status) VALUES ($1, 'initial', 'pending')
    """, ticket_id)

    logger.info("Ticket %s created with initial run for issue %s", ticket_id, issue_id)
    return {"status": "accepted", "ticket_id": ticket_id}


# --- GitHub webhook ---

AUTOPILOT_MENTION = "@autopilot"


async def _find_ticket_for_pr(repo_full_name: str, pr_number: int):
    pool = await get_pool()
    return await pool.fetchrow("""
        SELECT id FROM tickets
        WHERE pr_repo = $1 AND pr_number = $2 AND status = 'active'
    """, repo_full_name, pr_number)


async def _trigger_review_run(ticket_id: str, reason: str) -> dict:
    pool = await get_pool()
    active = await pool.fetchval("""
        SELECT COUNT(*) FROM runs
        WHERE ticket_id = $1 AND status IN ('pending', 'launching', 'running')
    """, ticket_id)
    if active > 0:
        logger.info("Review run skipped for ticket %s: already has active run (%s)", ticket_id, reason)
        return {"status": "accepted", "ticket_id": ticket_id, "run": "skipped_active"}

    await pool.execute("""
        INSERT INTO runs (ticket_id, kind, status) VALUES ($1, 'review', 'pending')
    """, ticket_id)
    await pool.execute(
        "UPDATE tickets SET debounce_until = NULL, updated_at = now() WHERE id = $1",
        ticket_id,
    )
    logger.info("Review run queued for ticket %s (%s)", ticket_id, reason)
    return {"status": "accepted", "ticket_id": ticket_id, "run": "queued"}


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

    if event == "pull_request_review" and payload.get("action") == "submitted":
        return await _handle_pr_review_submitted(payload)
    elif event == "pull_request_review_comment" and payload.get("action") == "created":
        return await _handle_pr_review_comment(payload)
    elif event == "issue_comment" and payload.get("action") == "created":
        return await _handle_issue_comment(payload)
    elif event == "pull_request":
        return await _handle_pr_event(payload)
    elif event == "check_suite" and payload.get("action") == "completed":
        return await _handle_check_suite_completed(payload)
    else:
        return _ignore("unhandled github event", event=event)


async def _handle_pr_review_submitted(payload: dict):
    review = payload.get("review", {})
    pr = payload.get("pull_request", {})
    repo = payload.get("repository", {})

    repo_full_name = repo.get("full_name", "")
    pr_number = pr.get("number")
    review_state = review.get("state", "")

    if not repo_full_name or not pr_number:
        return _ignore("missing repo or PR number")

    if review_state == "approved":
        return _ignore("review approved, nothing to address")

    ticket = await _find_ticket_for_pr(repo_full_name, pr_number)
    if not ticket:
        return _ignore("no active ticket for this PR", repo=repo_full_name, pr=pr_number)

    return await _trigger_review_run(str(ticket["id"]), f"review submitted ({review_state})")


async def _handle_issue_comment(payload: dict):
    issue = payload.get("issue", {})
    comment = payload.get("comment", {})
    repo = payload.get("repository", {})

    if not issue.get("pull_request"):
        return _ignore("issue_comment not on a PR")

    repo_full_name = repo.get("full_name", "")
    pr_number = issue.get("number")
    body = comment.get("body", "")

    if not repo_full_name or not pr_number:
        return _ignore("missing repo or PR number")

    if AUTOPILOT_MENTION not in body.lower():
        return _ignore("no autopilot mention")

    ticket = await _find_ticket_for_pr(repo_full_name, pr_number)
    if not ticket:
        return _ignore("no active ticket for this PR", repo=repo_full_name, pr=pr_number)

    return await _trigger_review_run(str(ticket["id"]), "mentioned in PR comment")


async def _handle_pr_review_comment(payload: dict):
    comment = payload.get("comment", {})
    pr = payload.get("pull_request", {})
    repo = payload.get("repository", {})

    repo_full_name = repo.get("full_name", "")
    pr_number = pr.get("number")
    body = comment.get("body", "")

    if not repo_full_name or not pr_number:
        return _ignore("missing repo or PR number")

    if AUTOPILOT_MENTION not in body.lower():
        return _ignore("no autopilot mention")

    ticket = await _find_ticket_for_pr(repo_full_name, pr_number)
    if not ticket:
        return _ignore("no active ticket for this PR", repo=repo_full_name, pr=pr_number)

    return await _trigger_review_run(str(ticket["id"]), "mentioned in review comment")


async def _handle_pr_event(payload: dict):
    action = payload.get("action", "")
    pr = payload.get("pull_request", {})
    repo = payload.get("repository", {})

    repo_full_name = repo.get("full_name", "")
    pr_number = pr.get("number")
    merged = pr.get("merged", False)

    if action not in ("closed",):
        return _ignore("PR action not relevant", action=action)

    ticket = await _find_ticket_for_pr(repo_full_name, pr_number)
    if not ticket:
        return _ignore("no active ticket for this PR")

    new_status = "merged" if merged else "closed"
    pool = await get_pool()
    await pool.execute("""
        UPDATE tickets SET status = $1, debounce_until = NULL, updated_at = now() WHERE id = $2
    """, new_status, str(ticket["id"]))

    logger.info("Ticket %s marked as %s (PR %s/%d)", ticket["id"], new_status, repo_full_name, pr_number)
    return {"status": "updated", "ticket_status": new_status}


async def _handle_check_suite_completed(payload: dict):
    check_suite = payload.get("check_suite", {})
    repo = payload.get("repository", {})

    conclusion = check_suite.get("conclusion", "")
    if conclusion not in ("failure", "timed_out"):
        return _ignore("check_suite passed", conclusion=conclusion)

    repo_full_name = repo.get("full_name", "")
    pull_requests = check_suite.get("pull_requests", [])

    if not pull_requests:
        return _ignore("check_suite has no associated PRs")

    for pr in pull_requests:
        pr_number = pr.get("number")
        if not pr_number:
            continue

        ticket = await _find_ticket_for_pr(repo_full_name, pr_number)
        if not ticket:
            continue

        result = await _trigger_review_run(str(ticket["id"]), f"CI failed ({conclusion})")
        logger.info("CI failure triggered review for ticket %s (PR %s#%d)", ticket["id"], repo_full_name, pr_number)
        return result

    return _ignore("no active tickets for failing PRs", repo=repo_full_name)
