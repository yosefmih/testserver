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


@router.post("/linear")
async def linear_webhook(request: Request, background_tasks: BackgroundTasks):
    body = await request.body()
    signature = request.headers.get("Linear-Signature", "")

    if not _verify_signature(body, config.LINEAR_WEBHOOK_SECRET, signature):
        raise HTTPException(status_code=401, detail="Invalid signature")

    payload = await request.json()

    if payload.get("type") != "Issue":
        return {"status": "ignored", "reason": "not an issue event"}

    action = payload.get("action")
    if action not in ("create", "update"):
        return {"status": "ignored", "reason": f"action {action} not handled"}

    issue_data = payload.get("data", {})
    team_id = issue_data.get("teamId") or payload.get("teamId")
    if not team_id:
        return {"status": "ignored", "reason": "no team in payload"}

    pool = await get_pool()
    project = await pool.fetchrow("""
        SELECT id, linear_access_token, autopilot_label,
               github_installation_id, github_repo
        FROM projects WHERE linear_team_id = $1
    """, team_id)

    if not project:
        return {"status": "ignored", "reason": "no project for this team"}

    labels = [l.get("name", "") for l in issue_data.get("labels", [])]
    if project["autopilot_label"] not in labels:
        return {"status": "ignored", "reason": "autopilot label not present"}

    if not project["github_installation_id"] or not project["github_repo"]:
        logger.warning("Project %s missing GitHub config, skipping", project["id"])
        return {"status": "ignored", "reason": "GitHub not configured"}

    issue_id = issue_data.get("id", "")
    project_id = str(project["id"])
    guard_key = f"{project_id}:{issue_id}"
    if guard_key in in_progress_issues:
        return {"status": "ignored", "reason": "already processing this issue"}

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
