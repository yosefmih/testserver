import logging
import secrets

import httpx

from config import config

logger = logging.getLogger(__name__)

LINEAR_AUTH_URL = "https://linear.app/oauth/authorize"
LINEAR_TOKEN_URL = "https://api.linear.app/oauth/token"
LINEAR_GRAPHQL_URL = "https://api.linear.app/graphql"


async def exchange_code(code: str) -> dict:
    async with httpx.AsyncClient() as client:
        resp = await client.post(LINEAR_TOKEN_URL, data={
            "code": code,
            "client_id": config.LINEAR_CLIENT_ID,
            "client_secret": config.LINEAR_CLIENT_SECRET,
            "redirect_uri": config.LINEAR_REDIRECT_URL,
            "grant_type": "authorization_code",
        })
        resp.raise_for_status()
        data = resp.json()
        return {
            "access_token": data["access_token"],
            "refresh_token": data.get("refresh_token"),
        }


async def get_teams(access_token: str) -> list[dict]:
    query = """
    query {
        teams {
            nodes {
                id
                name
                key
            }
        }
    }
    """
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            LINEAR_GRAPHQL_URL,
            json={"query": query},
            headers={"Authorization": access_token},
        )
        resp.raise_for_status()
        nodes = resp.json()["data"]["teams"]["nodes"]
        return [{"id": n["id"], "name": n["name"], "key": n["key"]} for n in nodes]


async def create_webhook(access_token: str, project_id: str, base_url: str) -> dict:
    webhook_url = f"{base_url}/webhooks/linear/{project_id}"
    secret = secrets.token_hex(32)

    mutation = """
    mutation WebhookCreate($input: WebhookCreateInput!) {
        webhookCreate(input: $input) {
            success
            webhook {
                id
            }
        }
    }
    """
    variables = {
        "input": {
            "url": webhook_url,
            "secret": secret,
            "resourceTypes": ["Issue"],
        }
    }
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            LINEAR_GRAPHQL_URL,
            json={"query": mutation, "variables": variables},
            headers={"Authorization": access_token},
        )
        resp.raise_for_status()
        body = resp.json()
        if body.get("errors"):
            logger.error("Linear webhookCreate errors: %s", body["errors"])
            raise Exception(f"Linear webhook creation failed: {body['errors']}")
        result = body["data"]["webhookCreate"]
        if not result["success"]:
            raise Exception("Failed to create Linear webhook")
        return {
            "webhook_id": result["webhook"]["id"],
            "webhook_secret": secret,
        }


async def delete_webhook(access_token: str, webhook_id: str):
    mutation = """
    mutation($id: String!) {
        webhookDelete(id: $id) {
            success
        }
    }
    """
    async with httpx.AsyncClient() as client:
        await client.post(
            LINEAR_GRAPHQL_URL,
            json={"query": mutation, "variables": {"id": webhook_id}},
            headers={"Authorization": access_token},
        )


async def post_issue_comment(access_token: str, issue_id: str, body: str):
    mutation = """
    mutation($issueId: String!, $body: String!) {
        commentCreate(input: { issueId: $issueId, body: $body }) {
            success
        }
    }
    """
    async with httpx.AsyncClient() as client:
        await client.post(
            LINEAR_GRAPHQL_URL,
            json={"query": mutation, "variables": {"issueId": issue_id, "body": body}},
            headers={"Authorization": access_token},
        )
