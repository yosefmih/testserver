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


async def get_organization(access_token: str) -> dict:
    query = """
    query {
        organization {
            id
            name
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
        org = resp.json()["data"]["organization"]
        return {"id": org["id"], "name": org["name"]}


async def get_issue(access_token: str, issue_id: str) -> dict | None:
    query = """
    query($id: String!) {
        issue(id: $id) {
            id
            title
            description
            url
            team { id }
            labels { nodes { id name } }
        }
    }
    """
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            LINEAR_GRAPHQL_URL,
            json={"query": query, "variables": {"id": issue_id}},
            headers={"Authorization": access_token},
        )
        resp.raise_for_status()
        body = resp.json()
        if body.get("errors") or not body.get("data", {}).get("issue"):
            logger.error("Failed to fetch issue %s: %s", issue_id, body.get("errors"))
            return None
        issue = body["data"]["issue"]
        return {
            "id": issue["id"],
            "title": issue["title"],
            "description": issue.get("description", ""),
            "url": issue.get("url", ""),
            "teamId": issue["team"]["id"] if issue.get("team") else None,
            "labels": [{"id": l["id"], "name": l["name"]} for l in issue.get("labels", {}).get("nodes", [])],
        }


async def post_issue_comment(access_token: str, issue_id: str, body: str):
    mutation = """
    mutation($issueId: String!, $body: String!) {
        commentCreate(input: {
            issueId: $issueId,
            body: $body,
            createAsUser: "Autopilot"
        }) {
            success
        }
    }
    """
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            LINEAR_GRAPHQL_URL,
            json={"query": mutation, "variables": {"issueId": issue_id, "body": body}},
            headers={"Authorization": access_token},
        )
        resp.raise_for_status()
        data = resp.json()
        if data.get("errors"):
            logger.error("Linear commentCreate failed for issue %s: %s", issue_id, data["errors"])
            raise Exception(f"Linear API error: {data['errors']}")
        if not data.get("data", {}).get("commentCreate", {}).get("success"):
            logger.error("Linear commentCreate returned success=false for issue %s: %s", issue_id, data)
            raise Exception("Linear commentCreate returned success=false")
