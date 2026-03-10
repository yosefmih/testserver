import hashlib
import hmac
import json
import logging

from fastapi import APIRouter, Request, HTTPException

from config import config
from db import get_pool
from services import linear_oauth

router = APIRouter()
logger = logging.getLogger(__name__)


def _verify_signature(body: bytes, secret: str, signature: str) -> bool:
    expected = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature)


def _ignore(reason: str, **extra) -> dict:
    logger.info("Webhook ignored: %s %s", reason, " ".join(f"{k}={v}" for k, v in extra.items()) if extra else "")
    return {"status": "ignored", "reason": reason}


@router.post("/linear")
async def linear_webhook(request: Request):
    body = await request.body()
    signature = request.headers.get("Linear-Signature", "")

    if not _verify_signature(body, config.LINEAR_WEBHOOK_SECRET, signature):
        logger.warning("Webhook signature verification failed")
        raise HTTPException(status_code=401, detail="Invalid signature")

    payload = await request.json()
    event_type = payload.get("type")
    action = payload.get("action")
    organization_id = payload.get("organizationId")

    logger.info("Webhook received: type=%s action=%s org=%s", event_type, action, organization_id)
    logger.debug("Webhook payload: %s", json.dumps(payload, default=str)[:2000])

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
        return await _handle_issue_label_event(payload, action, project)
    elif event_type == "Issue":
        return await _handle_issue_event(payload, action, project)
    else:
        return _ignore("unhandled event type", type=event_type)


async def _handle_issue_label_event(payload: dict, action: str, project):
    data = payload.get("data", {})
    label_name = data.get("label", {}).get("name") or data.get("name", "")
    issue_id = data.get("issueId", "unknown")

    logger.info("IssueLabel event: action=%s label=%r issueId=%s", action, label_name, issue_id)

    if action not in ("create",):
        return _ignore("IssueLabel action not relevant", action=action, label=label_name)

    if label_name != project["autopilot_label"]:
        return _ignore("label is not autopilot trigger", label=label_name, expected=project["autopilot_label"])

    logger.info("Autopilot label %r detected on issue %s, fetching issue details", label_name, issue_id)

    issue = await linear_oauth.get_issue(project["linear_access_token"], issue_id)
    if not issue:
        return _ignore("could not fetch issue details from Linear API", issue_id=issue_id)

    logger.info("Fetched issue: id=%s title=%r labels=%s",
                issue["id"], issue["title"], [l["name"] for l in issue["labels"]])

    return await _process_issue(issue, project)


async def _handle_issue_event(payload: dict, action: str, project):
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
        if "labelIds" not in updated_from:
            return _ignore("labels not changed in this update", issue_id=issue_id)
        if old_label_ids == new_label_ids:
            return _ignore("label set unchanged", issue_id=issue_id)

    issue = {
        "id": issue_data.get("id", ""),
        "title": issue_data.get("title", ""),
        "description": issue_data.get("description", ""),
        "url": issue_data.get("url", ""),
        "labels": issue_data.get("labels", []),
    }

    return await _process_issue(issue, project)


async def _process_issue(issue: dict, project):
    issue_id = issue["id"]
    project_id = str(project["id"])

    labels = [l.get("name", "") for l in issue.get("labels", [])]
    logger.info("Issue labels: %s, autopilot_label=%r, project_id=%s",
                labels, project["autopilot_label"], project_id)

    if project["autopilot_label"] not in labels:
        return _ignore("autopilot label not present", labels=labels, expected=project["autopilot_label"], issue_id=issue_id)

    if not project["github_installation_id"]:
        return _ignore("GitHub not configured", project_id=project_id, issue_id=issue_id)

    pool = await get_pool()

    existing = await pool.fetchrow("""
        SELECT id FROM jobs
        WHERE project_id = $1 AND linear_issue_id = $2 AND status IN ('pending', 'running')
    """, project_id, issue_id)
    if existing:
        return _ignore("job already in progress", issue_id=issue_id, project_id=project_id)

    job = await pool.fetchrow("""
        INSERT INTO jobs (project_id, linear_issue_id, linear_issue_title, linear_issue_description, linear_issue_url, status)
        VALUES ($1, $2, $3, $4, $5, 'pending')
        RETURNING id
    """, project_id, issue_id, issue.get("title", ""), issue.get("description", ""), issue.get("url", ""))

    logger.info("Job %s queued for issue %s in project %s", job["id"], issue_id, project_id)
    return {"status": "accepted", "job_id": str(job["id"])}
