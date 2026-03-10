import asyncio
import logging
import secrets

from porter_sandbox_api_client import Client
from porter_sandbox_api_client.api.sandboxes import create_sandbox, get_sandbox, get_sandbox_logs, delete_sandbox
from porter_sandbox_api_client.api.volumes import create_volume, get_volume
from porter_sandbox_api_client.models import (
    SandboxSpec, SandboxSpecEnv, Mount, MountAccessMode,
    VolumeSpec, VolumeSpecType,
)
from porter_sandbox_api_client.types import Unset

from config import config
from services.github_app import get_installation_token, get_installation_repos

logger = logging.getLogger(__name__)

SANDBOX_API_URL = "http://sandbox-central.kube-system.svc.cluster.local"

sandbox_client = Client(base_url=SANDBOX_API_URL)

VOLUME_READY_POLL_INTERVAL = 2
VOLUME_READY_TIMEOUT = 60
SANDBOX_CREATE_RETRIES = 3
SANDBOX_CREATE_RETRY_DELAY = 5


def generate_callback_token() -> str:
    return secrets.token_urlsafe(48)


async def wait_for_volume_ready(volume_id: str) -> None:
    elapsed = 0
    while elapsed < VOLUME_READY_TIMEOUT:
        response = get_volume.sync(id=volume_id, client=sandbox_client)
        phase = response.phase.value if hasattr(response.phase, "value") else str(response.phase)

        if phase == "ready":
            logger.info("Volume %s is ready (waited %ds)", volume_id, elapsed)
            return
        if phase == "failed":
            raise Exception(f"Volume {volume_id} failed to provision")

        logger.debug("Volume %s phase=%s, waiting...", volume_id, phase)
        await asyncio.sleep(VOLUME_READY_POLL_INTERVAL)
        elapsed += VOLUME_READY_POLL_INTERVAL

    raise Exception(f"Volume {volume_id} not ready after {VOLUME_READY_TIMEOUT}s")


async def create_volume_for_ticket() -> str:
    spec = VolumeSpec(
        type_=VolumeSpecType.EFS,
        storage_size="10Gi",
        ttl_seconds=config.VOLUME_TTL,
    )
    response = create_volume.sync(client=sandbox_client, body=spec)
    if not hasattr(response, "id"):
        raise Exception(f"Failed to create volume: {response}")
    logger.info("Volume created: volume_id=%s phase=%s", response.id, response.phase)

    await wait_for_volume_ready(response.id)
    return response.id


async def ensure_volume_ready(volume_id: str) -> None:
    response = get_volume.sync(id=volume_id, client=sandbox_client)
    phase = response.phase.value if hasattr(response.phase, "value") else str(response.phase)
    if phase == "ready":
        return
    if phase == "failed":
        raise Exception(f"Volume {volume_id} is in failed state")
    await wait_for_volume_ready(volume_id)


def _build_initial_prompt(
    issue_title: str,
    issue_description: str,
    issue_url: str,
    issue_id: str,
    repo_list: str,
    callback_url: str,
) -> str:
    return f"""Fix this Linear issue and create a GitHub PR.

Issue Title: {issue_title}
Issue Description: {issue_description}
Linear URL: {issue_url}

You have access to the following GitHub repos:
{repo_list}

Steps:
1. Determine which repo is relevant based on the issue context
2. Clone that repo into /workspace/repo
3. Create a branch named autopilot/{issue_id}
4. Understand and fix the issue
5. Commit your changes with a descriptive message
6. Push the branch and create a PR linking to {issue_url}

Do NOT comment on the Linear issue — the server handles that automatically.

IMPORTANT: After creating the PR, you MUST report the metadata by running:
curl -s -X POST "{callback_url}?token=$CALLBACK_TOKEN" \\
  -H "Content-Type: application/json" \\
  -d '{{"pr_url": "<THE_PR_URL>", "pr_repo": "<owner/repo>", "pr_number": <PR_NUMBER>}}'

Work inside /workspace/repo for your cloned code. Any state you want preserved across runs should be in /workspace."""


def _build_review_prompt(
    issue_title: str,
    issue_url: str,
    pr_url: str,
    comments_text: str,
    callback_url: str,
) -> str:
    return f"""Address these PR review comments for the Linear issue.

Issue Title: {issue_title}
Linear URL: {issue_url}
PR: {pr_url}

Review comments to address:
{comments_text}

The repo is already cloned at /workspace/repo. Your previous work is preserved there.

Steps:
1. cd /workspace/repo and pull latest changes
2. Read and understand each review comment
3. Make the requested changes
4. Commit and push to the existing branch

IMPORTANT: After pushing, report completion by running:
curl -s -X POST "{callback_url}?token=$CALLBACK_TOKEN" \\
  -H "Content-Type: application/json" \\
  -d '{{"status": "addressed"}}'

Work inside /workspace/repo."""


async def create_sandbox_for_run(
    run_id: str,
    callback_token: str,
    kind: str,
    volume_id: str,
    issue_id: str,
    issue_title: str,
    issue_description: str,
    issue_url: str,
    github_installation_id: int,
    linear_access_token: str,
    pr_url: str | None = None,
    review_comments: str | None = None,
) -> str:
    await ensure_volume_ready(volume_id)

    github_token = await get_installation_token(github_installation_id)
    repos = await get_installation_repos(github_installation_id)
    repo_list = "\n".join(f"- {r['full_name']}" for r in repos)

    callback_url = f"{config.BASE_URL}/api/internal/runs/{run_id}/metadata"

    if kind == "review" and pr_url and review_comments:
        prompt = _build_review_prompt(
            issue_title=issue_title,
            issue_url=issue_url,
            pr_url=pr_url,
            comments_text=review_comments,
            callback_url=callback_url,
        )
    else:
        prompt = _build_initial_prompt(
            issue_title=issue_title,
            issue_description=issue_description or "",
            issue_url=issue_url or "",
            issue_id=issue_id,
            repo_list=repo_list,
            callback_url=callback_url,
        )

    spec = SandboxSpec(
        image=config.WORKER_IMAGE,
        command=["bash", "/app/entrypoint.sh"],
        ttl_seconds=config.SANDBOX_TTL,
        env=SandboxSpecEnv.from_dict({
            "CLAUDE_CODE_OAUTH_TOKEN": config.ANTHROPIC_API_KEY,
            "GITHUB_TOKEN": github_token,
            "LINEAR_API_KEY": linear_access_token,
            "ISSUE_PROMPT": prompt,
            "CALLBACK_TOKEN": callback_token,
            "CALLBACK_URL": callback_url,
        }),
        mounts=[
            Mount(
                path_in_sandbox="/workspace",
                volume_id=volume_id,
                access_mode=MountAccessMode.RW,
            ),
        ],
    )

    last_error = None
    for attempt in range(1, SANDBOX_CREATE_RETRIES + 1):
        response = create_sandbox.sync(client=sandbox_client, body=spec)
        if hasattr(response, "id"):
            logger.info("Sandbox created: sandbox_id=%s run_id=%s kind=%s (attempt %d)",
                        response.id, run_id, kind, attempt)
            return response.id

        last_error = response
        logger.warning("Sandbox creation attempt %d/%d failed: %s", attempt, SANDBOX_CREATE_RETRIES, response)
        if attempt < SANDBOX_CREATE_RETRIES:
            await asyncio.sleep(SANDBOX_CREATE_RETRY_DELAY)

    raise Exception(f"Failed to create sandbox after {SANDBOX_CREATE_RETRIES} attempts: {last_error}")


def parse_sandbox_phase(status_response) -> str:
    if hasattr(status_response, "phase"):
        raw = status_response.phase
        return raw.value if hasattr(raw, "value") else str(raw)
    return "unknown"


def parse_sandbox_exit_code(status_response):
    raw = getattr(status_response, "exit_code", None)
    if raw is not None and not isinstance(raw, Unset):
        return raw
    return None
