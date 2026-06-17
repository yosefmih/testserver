import asyncio
import logging
import secrets

from porter_sandbox import AsyncPorter, NotFoundError, SandboxError
from porter_sandbox._models import StatusResponse, VolumeSpec
from porter_sandbox.enums import StatusResponsePhase, VolumePhase

from config import config
from services.github_app import get_installation_token, get_installation_repos

logger = logging.getLogger(__name__)

porter = AsyncPorter(
    base_url=config.PORTER_SANDBOX_BASE_URL or None,
    api_key=config.PORTER_SANDBOX_API_KEY or None,
)

VOLUME_READY_POLL_INTERVAL = 2
VOLUME_READY_TIMEOUT = 60
SANDBOX_CREATE_RETRIES = 3
SANDBOX_CREATE_RETRY_DELAY = 5

WORKSPACE_MOUNT_PATH = "/workspace"
APP_TAG = "linear-autopilot"

DEFAULT_ALLOWED_TOOLS = "mcp__github__*,mcp__linear__get_issue,mcp__linear__get_issue_comments,Read,Write,Edit,Bash,Glob,Grep"


def generate_callback_token() -> str:
    return secrets.token_urlsafe(48)


def _volume_name(ticket_id: str) -> str:
    return f"autopilot-{ticket_id}"


async def wait_for_volume_ready(volume_id: str) -> None:
    elapsed = 0
    while elapsed < VOLUME_READY_TIMEOUT:
        volume = await porter.volumes.get(volume_id)

        if volume.phase == VolumePhase.READY:
            logger.info("Volume %s is ready (waited %ds)", volume_id, elapsed)
            return
        if volume.phase == VolumePhase.FAILED:
            raise Exception(f"Volume {volume_id} failed to provision")

        logger.debug("Volume %s phase=%s, waiting...", volume_id, volume.phase.value)
        await asyncio.sleep(VOLUME_READY_POLL_INTERVAL)
        elapsed += VOLUME_READY_POLL_INTERVAL

    raise Exception(f"Volume {volume_id} not ready after {VOLUME_READY_TIMEOUT}s")


async def create_volume_for_ticket(ticket_id: str) -> str:
    name = _volume_name(ticket_id)
    try:
        volume = await porter.volumes.create(VolumeSpec(name=name))
        volume_id = volume.id
        logger.info("Volume created: volume_id=%s name=%s phase=%s", volume_id, name, volume.phase.value)
    except SandboxError:
        existing = await porter.volumes.list(name=name)
        if not existing.volumes:
            raise
        volume_id = existing.volumes[0].id
        logger.info("Reusing existing volume %s for name %s", volume_id, name)

    await wait_for_volume_ready(volume_id)
    return volume_id


async def ensure_volume_ready(volume_id: str) -> None:
    volume = await porter.volumes.get(volume_id)
    if volume.phase == VolumePhase.READY:
        return
    if volume.phase == VolumePhase.FAILED:
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
1. Determine which repos are relevant based on the issue context
2. Clone them under /workspace/ (e.g. /workspace/repo-name). Clone as many repos as you need.
3. Create a branch named autopilot/{issue_id} in the primary repo you are changing
4. Understand and fix the issue
5. Commit your changes with a descriptive message
6. Push the branch and create a PR linking to {issue_url}

Do NOT comment on the Linear issue — the server handles that automatically.

IMPORTANT: After creating the PR, you MUST report metadata and a summary by running:
curl -s -X POST "{callback_url}?token=$CALLBACK_TOKEN" \\
  -H "Content-Type: application/json" \\
  -d '{{"pr_url": "<THE_PR_URL>", "pr_repo": "<owner/repo>", "pr_number": <PR_NUMBER>, "summary": "<2-3 sentence summary of what you did and why>"}}'

The summary should be concise and explain what changes you made and the reasoning behind them. This gets posted to the Linear issue for the team."""



def _build_review_prompt(
    issue_title: str,
    issue_url: str,
    pr_url: str,
    pr_repo: str,
    pr_number: int,
    callback_url: str,
) -> str:
    owner, repo = pr_repo.split("/", 1)
    return f"""Address review comments and CI failures for this Linear issue.

Issue Title: {issue_title}
Linear URL: {issue_url}
PR: {pr_url}
Repo: {pr_repo}
PR Number: {pr_number}

This is a continuation of your previous session — you have full context of what you did before.

Steps:
1. Pull latest changes in the repo you were working in
2. Check CI status using mcp__github__pull_request_read with method="get_check_runs", owner="{owner}", repo="{repo}", pullNumber={pr_number}
   - If any check runs have failed, read their output and fix the issues
3. Fetch ALL comments on PR #{pr_number} in {pr_repo}:
   - Use mcp__github__pull_request_read with method="get_review_comments" to get review threads
   - Use mcp__github__pull_request_read with method="get_comments" to get general PR comments
4. Identify which comments are NEW (ones you haven't addressed yet) and not authored by you
5. Address each new comment by making the requested code changes
6. Commit and push to the existing branch
7. Reply to EACH comment individually on GitHub:
   - For inline review comments: use mcp__github__add_reply_to_pull_request_comment
   - For general PR conversation comments: use mcp__github__add_issue_comment
   - Keep replies concise — briefly describe what you changed
8. Report completion

IMPORTANT: After pushing, report completion by running:
curl -s -X POST "{callback_url}?token=$CALLBACK_TOKEN" \\
  -H "Content-Type: application/json" \\
  -d '{{"status": "addressed", "summary": "<2-3 sentence summary of what review comments you addressed, CI failures you fixed, and what changes you made>"}}'

The summary gets posted to the Linear issue for the team."""


def _build_worker_command(env: dict[str, str]) -> list[str]:
    env_pairs = [f"{key}={value}" for key, value in env.items()]
    return ["env", *env_pairs, "bash", "/app/entrypoint.sh"]


async def create_sandbox_for_run(
    run_id: str,
    callback_token: str,
    kind: str,
    volume_id: str,
    ticket_id: str,
    issue_id: str,
    issue_title: str,
    issue_description: str,
    issue_url: str,
    github_installation_id: int,
    linear_access_token: str,
    anthropic_api_key: str,
    custom_tools: str | None = None,
    system_prompt: str | None = None,
    pr_url: str | None = None,
    pr_repo: str | None = None,
    pr_number: int | None = None,
) -> str:
    await ensure_volume_ready(volume_id)

    github_token = await get_installation_token(github_installation_id)
    repos = await get_installation_repos(github_installation_id)
    repo_list = "\n".join(f"- {r['full_name']}" for r in repos)

    callback_url = f"{config.BASE_URL}/api/internal/runs/{run_id}/metadata"

    if kind == "review" and pr_url and pr_repo and pr_number:
        prompt = _build_review_prompt(
            issue_title=issue_title,
            issue_url=issue_url,
            pr_url=pr_url,
            pr_repo=pr_repo,
            pr_number=pr_number,
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

    if system_prompt:
        prompt = f"{prompt}\n\n--- Organization Instructions ---\n{system_prompt}"

    allowed_tools = DEFAULT_ALLOWED_TOOLS
    if custom_tools:
        allowed_tools = f"{allowed_tools},{custom_tools}"

    command = _build_worker_command({
        "CLAUDE_CODE_OAUTH_TOKEN": anthropic_api_key,
        "GITHUB_TOKEN": github_token,
        "LINEAR_API_KEY": linear_access_token,
        "ISSUE_PROMPT": prompt,
        "CALLBACK_TOKEN": callback_token,
        "CALLBACK_URL": callback_url,
        "RUN_KIND": kind,
        "ALLOWED_TOOLS": allowed_tools,
    })

    tags = {
        "app": APP_TAG,
        "run_id": run_id,
        "ticket_id": ticket_id,
        "kind": kind,
    }

    last_error: Exception | None = None
    for attempt in range(1, SANDBOX_CREATE_RETRIES + 1):
        try:
            sandbox = await porter.sandboxes.create(
                image=config.WORKER_IMAGE,
                command=command,
                volume_mounts={WORKSPACE_MOUNT_PATH: volume_id},
                tags=tags,
            )
            logger.info("Sandbox created: sandbox_id=%s run_id=%s kind=%s (attempt %d)",
                        sandbox.id, run_id, kind, attempt)
            return sandbox.id
        except SandboxError as e:
            last_error = e
            logger.warning("Sandbox creation attempt %d/%d failed: %s", attempt, SANDBOX_CREATE_RETRIES, e)
            if attempt < SANDBOX_CREATE_RETRIES:
                await asyncio.sleep(SANDBOX_CREATE_RETRY_DELAY)

    raise Exception(f"Failed to create sandbox after {SANDBOX_CREATE_RETRIES} attempts: {last_error}")


async def get_sandbox_status(sandbox_id: str) -> StatusResponse | None:
    try:
        return await porter.sandboxes.raw.get_sandbox(id=sandbox_id)
    except NotFoundError:
        return None


async def delete_sandbox(sandbox_id: str) -> None:
    await porter.sandboxes.raw.delete_sandbox(id=sandbox_id)


async def delete_volume(volume_id: str) -> None:
    await porter.volumes.delete(volume_id)


async def get_sandbox_logs(sandbox_id: str, limit: int = 1000, since: str = "6h") -> list[str]:
    response = await porter.sandboxes.raw.get_sandbox_logs(id=sandbox_id, limit=limit, since=since)
    return [entry.line for entry in response.logs]


def parse_sandbox_phase(status: StatusResponse) -> str:
    return status.phase.value


def parse_sandbox_exit_code(status: StatusResponse) -> int | None:
    return status.exit_code


def is_terminal_phase(phase: StatusResponsePhase) -> bool:
    return phase in (
        StatusResponsePhase.SUCCEEDED,
        StatusResponsePhase.FAILED,
        StatusResponsePhase.TERMINATED,
    )
