import asyncio
import logging
import time

from porter_sandbox_api_client import Client
from porter_sandbox_api_client.api.sandboxes import create_sandbox, get_sandbox, delete_sandbox, get_sandbox_logs
from porter_sandbox_api_client.models import SandboxSpec, SandboxSpecEnv

from config import config
from db import get_pool
from services.github_app import get_installation_token
from services.linear_oauth import post_issue_comment

logger = logging.getLogger(__name__)

SANDBOX_API_URL = config.BASE_URL.replace("://", "://sandbox-central.kube-system.svc.cluster.local") if False else "http://sandbox-central.kube-system.svc.cluster.local"

sandbox_client = Client(base_url=SANDBOX_API_URL)


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

    spec = SandboxSpec(
        image=config.WORKER_IMAGE,
        command=["bash", "/app/entrypoint.sh"],
        ttl_seconds=config.SANDBOX_TTL,
        env=SandboxSpecEnv.from_dict({
            "ANTHROPIC_API_KEY": config.ANTHROPIC_API_KEY,
            "GITHUB_TOKEN": github_token,
            "LINEAR_API_KEY": linear_access_token,
            "ISSUE_PROMPT": prompt,
        }),
    )

    sandbox_id = None
    try:
        response = create_sandbox.sync(client=sandbox_client, body=spec)
        if not hasattr(response, "id"):
            raise Exception(f"Failed to create sandbox: {response}")
        sandbox_id = response.id

        await pool.execute(
            "UPDATE jobs SET status = 'running', sandbox_id = $1 WHERE id = $2",
            sandbox_id, job_id,
        )

        deadline = time.time() + config.SANDBOX_TTL
        phase = "pending"
        exit_code = None
        while time.time() < deadline:
            status_response = get_sandbox.sync(id=sandbox_id, client=sandbox_client)
            if hasattr(status_response, "phase"):
                phase = status_response.phase
            if hasattr(status_response, "exit_code") and status_response.exit_code is not None:
                exit_code = status_response.exit_code
                logger.info("Sandbox %s exited with code %d (phase=%s)", sandbox_id, exit_code, phase)
                if phase not in ("succeeded", "failed"):
                    phase = "succeeded" if exit_code == 0 else "failed"
                break
            if phase in ("succeeded", "failed", "cancelled"):
                break
            await asyncio.sleep(10)

        logs_response = get_sandbox_logs.sync(id=sandbox_id, client=sandbox_client)
        log_text = ""
        if hasattr(logs_response, "logs") and logs_response.logs:
            log_text = "\n".join(logs_response.logs)

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
        if sandbox_id:
            try:
                delete_sandbox.sync(id=sandbox_id, client=sandbox_client)
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
