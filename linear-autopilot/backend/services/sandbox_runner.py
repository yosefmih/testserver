import logging

from porter_sandbox_api_client import Client
from porter_sandbox_api_client.api.sandboxes import create_sandbox
from porter_sandbox_api_client.models import SandboxSpec, SandboxSpecEnv

from config import config
from services.github_app import get_installation_token, get_installation_repos

logger = logging.getLogger(__name__)

SANDBOX_API_URL = "http://sandbox-central.kube-system.svc.cluster.local"

sandbox_client = Client(base_url=SANDBOX_API_URL)


async def create_sandbox_for_job(
    issue_id: str,
    issue_title: str,
    issue_description: str,
    issue_url: str,
    github_installation_id: int,
    linear_access_token: str,
) -> str:
    github_token = await get_installation_token(github_installation_id)
    repos = await get_installation_repos(github_installation_id)
    repo_list = "\n".join(f"- {r['full_name']}" for r in repos)

    prompt = f"""Fix this Linear issue and create a GitHub PR.

Issue Title: {issue_title}
Issue Description: {issue_description}
Linear URL: {issue_url}

You have access to the following GitHub repos:
{repo_list}

Steps:
1. Determine which repo is relevant based on the issue context
2. Clone that repo
3. Create a branch named autopilot/{issue_id}
4. Understand and fix the issue
5. Commit your changes with a descriptive message
6. Push the branch and create a PR linking to {issue_url}
7. Comment on the Linear issue with the PR URL"""

    spec = SandboxSpec(
        image=config.WORKER_IMAGE,
        command=["bash", "/app/entrypoint.sh"],
        ttl_seconds=config.SANDBOX_TTL,
        env=SandboxSpecEnv.from_dict({
            "CLAUDE_CODE_OAUTH_TOKEN": config.ANTHROPIC_API_KEY,
            "GITHUB_TOKEN": github_token,
            "LINEAR_API_KEY": linear_access_token,
            "ISSUE_PROMPT": prompt,
        }),
    )

    response = create_sandbox.sync(client=sandbox_client, body=spec)
    if not hasattr(response, "id"):
        raise Exception(f"Failed to create sandbox: {response}")

    logger.info("Sandbox created: sandbox_id=%s", response.id)
    return response.id
