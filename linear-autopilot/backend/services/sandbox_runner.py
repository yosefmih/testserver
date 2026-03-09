import asyncio
import logging

import porter_sdk

from config import config
from db import get_pool
from services.github_app import get_installation_token
from services.linear_oauth import post_issue_comment

logger = logging.getLogger(__name__)


async def launch_autopilot(
    job_id: str,
    issue_id: str,
    issue_title: str,
    issue_description: str,
    issue_url: str,
    github_installation_id: int,
    github_repo: str,
    linear_access_token: str,
):
    pool = await get_pool()

    github_token = await get_installation_token(github_installation_id)

    prompt = f"""Fix this Linear issue and create a GitHub PR.

Repo: {github_repo}
Issue Title: {issue_title}
Issue Description: {issue_description}
Linear URL: {issue_url}

Steps:
1. Clone the repo {github_repo}
2. Create a branch named autopilot/{issue_id}
3. Understand and fix the issue
4. Commit your changes with a descriptive message
5. Push the branch and create a PR linking to {issue_url}
6. Comment on the Linear issue with the PR URL"""

    sb = porter_sdk.NewSandbox(
        image=config.WORKER_IMAGE,
        command=["bash", "/app/entrypoint.sh"],
        env={
            "ANTHROPIC_API_KEY": config.ANTHROPIC_API_KEY,
            "GITHUB_TOKEN": github_token,
            "LINEAR_API_KEY": linear_access_token,
            "ISSUE_PROMPT": prompt,
        },
        ttl_seconds=config.SANDBOX_TTL,
    )

    try:
        sb.Run(wait=True, timeout=60)

        await pool.execute(
            "UPDATE jobs SET status = 'running', sandbox_id = $1 WHERE id = $2",
            sb.id, job_id,
        )

        while True:
            status = sb.Status()
            if status.get("phase") in ("succeeded", "failed"):
                break
            await asyncio.sleep(10)

        logs = sb.Logs()
        phase = status.get("phase", "failed")
        log_text = "\n".join(logs) if logs else ""

        pr_url = _extract_pr_url(log_text)

        await pool.execute("""
            UPDATE jobs SET status = $1, pr_url = $2, finished_at = now() WHERE id = $3
        """, "success" if phase == "succeeded" else "failed", pr_url, job_id)

        if phase == "succeeded" and pr_url:
            await post_issue_comment(
                linear_access_token, issue_id,
                f"Autopilot created a PR: {pr_url}"
            )
        elif phase == "failed":
            await pool.execute(
                "UPDATE jobs SET error = $1 WHERE id = $2", log_text[-2000:], job_id
            )
            await post_issue_comment(
                linear_access_token, issue_id,
                "Autopilot failed to create a fix. Check the dashboard for details."
            )

    except Exception:
        logger.exception("Sandbox execution failed for job %s", job_id)
        raise
    finally:
        try:
            sb.Destroy()
        except Exception:
            logger.warning("Failed to destroy sandbox for job %s", job_id)


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
