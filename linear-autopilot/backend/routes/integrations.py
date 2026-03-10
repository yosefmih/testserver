import logging
import secrets
from urllib.parse import urlencode

from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import RedirectResponse

from config import config
from db import get_pool
from middleware.auth import get_current_user_id
from services import github_app, linear_oauth

router = APIRouter()
callbacks_router = APIRouter()
logger = logging.getLogger(__name__)

LINEAR_AUTH_URL = "https://linear.app/oauth/authorize"


# --- GitHub App Installation ---

@router.get("/projects/{project_id}/integrations/github/install")
async def github_install(request: Request, project_id: str):
    get_current_user_id(request)
    install_url = f"https://github.com/apps/{config.GITHUB_APP_SLUG}/installations/new"
    params = urlencode({"state": project_id})
    return RedirectResponse(url=f"{install_url}?{params}")


@callbacks_router.get("/github/callback")
async def github_callback(request: Request, installation_id: int, state: str):
    user_id = get_current_user_id(request)
    project_id = state

    pool = await get_pool()
    project = await pool.fetchrow(
        "SELECT id FROM projects WHERE id = $1 AND user_id = $2", project_id, user_id
    )
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    await pool.execute(
        "UPDATE projects SET github_installation_id = $1, updated_at = now() WHERE id = $2",
        installation_id, project_id,
    )

    return RedirectResponse(url=f"/projects/{project_id}/settings", status_code=302)


@router.get("/projects/{project_id}/integrations/github/repos")
async def list_github_repos(request: Request, project_id: str):
    user_id = get_current_user_id(request)
    pool = await get_pool()

    project = await pool.fetchrow(
        "SELECT github_installation_id FROM projects WHERE id = $1 AND user_id = $2",
        project_id, user_id,
    )
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    if not project["github_installation_id"]:
        raise HTTPException(status_code=400, detail="GitHub not connected")

    repos = await github_app.get_installation_repos(project["github_installation_id"])
    return repos


# --- Linear OAuth ---

@router.get("/projects/{project_id}/integrations/linear/connect")
async def linear_connect(request: Request, project_id: str):
    get_current_user_id(request)

    state = f"{project_id}:{secrets.token_hex(16)}"
    params = urlencode({
        "client_id": config.LINEAR_CLIENT_ID,
        "redirect_uri": config.LINEAR_REDIRECT_URL,
        "response_type": "code",
        "scope": "read,write",
        "state": state,
        "actor": "app",
        "prompt": "consent",
    })

    response = RedirectResponse(url=f"{LINEAR_AUTH_URL}?{params}")
    response.set_cookie(
        "linear_oauth_state", state,
        httponly=True, samesite="lax", max_age=300,
        secure=request.url.scheme == "https",
    )
    return response


@callbacks_router.get("/linear/callback")
async def linear_callback(request: Request, code: str, state: str):
    stored_state = request.cookies.get("linear_oauth_state")
    if not stored_state or stored_state != state:
        raise HTTPException(status_code=400, detail="Invalid OAuth state")

    project_id = state.split(":")[0]
    user_id = get_current_user_id(request)

    pool = await get_pool()
    project = await pool.fetchrow(
        "SELECT id FROM projects WHERE id = $1 AND user_id = $2",
        project_id, user_id,
    )
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    tokens = await linear_oauth.exchange_code(code)

    org = await linear_oauth.get_organization(tokens["access_token"])
    org_id = org["id"]

    conflict = await pool.fetchrow(
        "SELECT id, name FROM projects WHERE linear_organization_id = $1 AND id != $2",
        org_id, project_id,
    )
    if conflict:
        raise HTTPException(
            status_code=409,
            detail=f"This Linear organization is already linked to project \"{conflict['name']}\"",
        )

    await pool.execute("""
        UPDATE projects SET
            linear_access_token = $1,
            linear_refresh_token = $2,
            linear_organization_id = $3,
            updated_at = now()
        WHERE id = $4
    """, tokens["access_token"], tokens.get("refresh_token"), org_id, project_id)

    logger.info("Linear connected: project=%s org=%s (%s)", project_id, org_id, org["name"])

    response = RedirectResponse(url=f"/projects/{project_id}/settings", status_code=302)
    response.delete_cookie("linear_oauth_state")
    return response
