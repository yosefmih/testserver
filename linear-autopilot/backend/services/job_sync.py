import asyncio
import logging

from porter_sandbox_api_client.api.sandboxes import get_sandbox, get_sandbox_logs, delete_sandbox
from porter_sandbox_api_client.types import Unset

from config import config
from db import get_pool
from services.sandbox_runner import sandbox_client, create_sandbox_for_job
from services.linear_oauth import post_issue_comment

logger = logging.getLogger(__name__)

SYNC_INTERVAL_SECONDS = 15


def _parse_phase(status_response) -> str:
    if hasattr(status_response, "phase"):
        raw = status_response.phase
        return raw.value if hasattr(raw, "value") else str(raw)
    return "unknown"


def _parse_exit_code(status_response):
    raw = getattr(status_response, "exit_code", None)
    if raw is not None and not isinstance(raw, Unset):
        return raw
    return None


def _extract_pr_url(log_text: str) -> str | None:
    for line in log_text.split("\n"):
        stripped = line.strip()
        if "github.com" in stripped and "/pull/" in stripped:
            for word in stripped.split():
                if "github.com" in word and "/pull/" in word:
                    url = word.strip("()[]<>\"'")
                    if url.startswith("http"):
                        return url
    return None


async def _launch_pending_jobs():
    pool = await get_pool()

    jobs = await pool.fetch("""
        SELECT j.id, j.project_id, j.linear_issue_id, j.linear_issue_title,
               j.linear_issue_description, j.linear_issue_url,
               p.github_installation_id, p.linear_access_token
        FROM jobs j
        JOIN projects p ON p.id = j.project_id
        WHERE j.status = 'pending'
    """)

    if not jobs:
        return

    logger.info("Job sync: launching %d pending jobs", len(jobs))

    for job in jobs:
        job_id = str(job["id"])
        try:
            await pool.execute("UPDATE jobs SET status = 'launching' WHERE id = $1", job_id)

            sandbox_id = await create_sandbox_for_job(
                issue_id=job["linear_issue_id"],
                issue_title=job["linear_issue_title"],
                issue_description=job["linear_issue_description"] or "",
                issue_url=job["linear_issue_url"] or "",
                github_installation_id=job["github_installation_id"],
                linear_access_token=job["linear_access_token"],
            )

            await pool.execute(
                "UPDATE jobs SET status = 'running', sandbox_id = $1 WHERE id = $2",
                sandbox_id, job_id,
            )
            logger.info("Job sync: job %s launched sandbox %s", job_id, sandbox_id)

            if job["linear_access_token"]:
                try:
                    job_url = f"{config.BASE_URL}/projects/{job['project_id']}/jobs/{job_id}"
                    await post_issue_comment(
                        job["linear_access_token"],
                        job["linear_issue_id"],
                        f"Autopilot is working on this issue. [View job]({job_url})",
                    )
                except Exception:
                    logger.warning("Job sync: failed to post launch comment for job %s", job_id)

        except Exception as e:
            logger.exception("Job sync: failed to launch sandbox for job %s", job_id)
            await pool.execute(
                "UPDATE jobs SET status = 'failed', error = $1, finished_at = now() WHERE id = $2",
                str(e), job_id,
            )


async def _sync_active_jobs():
    pool = await get_pool()

    jobs = await pool.fetch("""
        SELECT j.id, j.sandbox_id, j.linear_issue_id
        FROM jobs j
        WHERE j.status = 'running'
          AND j.sandbox_id IS NOT NULL
    """)

    if not jobs:
        return

    logger.info("Job sync: checking %d running jobs", len(jobs))

    for job in jobs:
        job_id = str(job["id"])
        sandbox_id = job["sandbox_id"]

        try:
            status_response = get_sandbox.sync(id=sandbox_id, client=sandbox_client)
            phase = _parse_phase(status_response)
            exit_code = _parse_exit_code(status_response)

            logger.info("Job sync: job=%s sandbox=%s phase=%s exit_code=%r", job_id, sandbox_id, phase, exit_code)

            terminal = False
            final_status = None

            if exit_code is not None:
                terminal = True
                final_status = "success" if exit_code == 0 else "failed"
            elif phase in ("succeeded", "failed", "cancelled"):
                terminal = True
                final_status = "success" if phase == "succeeded" else "failed"

            if not terminal:
                continue

            log_text = ""
            try:
                logs_response = get_sandbox_logs.sync(id=sandbox_id, client=sandbox_client)
                if hasattr(logs_response, "logs") and logs_response.logs:
                    log_text = "\n".join(logs_response.logs)
            except Exception:
                logger.warning("Job sync: failed to fetch logs for sandbox %s", sandbox_id)

            pr_url = _extract_pr_url(log_text)

            await pool.execute("""
                UPDATE jobs SET status = $1, pr_url = $2, finished_at = now() WHERE id = $3 AND status = 'running'
            """, final_status, pr_url, job_id)

            if final_status == "failed":
                error_text = log_text[-2000:] if log_text else f"Sandbox exited: phase={phase} exit_code={exit_code}"
                await pool.execute("UPDATE jobs SET error = $1 WHERE id = $2", error_text, job_id)

            logger.info("Job sync: marked job %s as %s (phase=%s exit_code=%s pr=%s)", job_id, final_status, phase, exit_code, pr_url)

            try:
                delete_sandbox.sync(id=sandbox_id, client=sandbox_client)
                logger.info("Job sync: deleted sandbox %s", sandbox_id)
            except Exception:
                logger.warning("Job sync: failed to delete sandbox %s", sandbox_id)

        except Exception:
            logger.exception("Job sync: error checking job %s sandbox %s", job_id, sandbox_id)


async def job_sync_loop():
    logger.info("Job sync loop started (interval=%ds)", SYNC_INTERVAL_SECONDS)
    while True:
        try:
            await _launch_pending_jobs()
            await _sync_active_jobs()
        except Exception:
            logger.exception("Job sync loop iteration failed")
        await asyncio.sleep(SYNC_INTERVAL_SECONDS)
