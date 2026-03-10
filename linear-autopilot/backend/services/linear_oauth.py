import logging

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
