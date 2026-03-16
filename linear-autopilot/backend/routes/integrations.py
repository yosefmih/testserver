import logging
import secrets
from urllib.parse import urlencode

from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import RedirectResponse

from config import config
from db import get_pool
from middleware.auth import get_current_user_id, require_project_member
from services import github_app, linear_oauth

router = APIRouter()
callbacks_router = APIRouter()
logger = logging.getLogger(__name__)

LINEAR_AUTH_URL = "https://linear.app/oauth/authorize"
LINEAR_OAUTH_STATE_COOKIE = "linear_oauth_state"
LINEAR_SCOPE = "read,write"
LINEAR_RESPONSE_TYPE = "code"
LINEAR_ACTOR = "app"
LINEAR_PROMPT = "consent"

GITHUB_INSTALL_BASE_URL = "https://github.com/apps"

STATUS_DISCONNECTED = "disconnected"


# --- GitHub App Installation ---

@router.get("/projects/{project_id}/integrations/github/install")
async def github_install(request: Request, project_id: str):
    user_id = get_current_user_id(request)
    pool = await get_pool()
    await require_project_member(pool, user_id, project_id, min_role="admin")

    install_url = f"{GITHUB_INSTALL_BASE_URL}/{config.GITHUB_APP_SLUG}/installations/new"
    params = urlencode({"state": project_id})
    return RedirectResponse(url=f"{install_url}?{params}")


@callbacks_router.get("/github/callback")
async def github_callback(request: Request, installation_id: int, state: str):
    user_id = get_current_user_id(request)
    project_id = state

    pool = await get_pool()
    await require_project_member(pool, user_id, project_id, min_role="admin")

    await pool.execute(
        "UPDATE projects SET github_installation_id = $1, updated_at = now() WHERE id = $2",
        installation_id, project_id,
    )

    return RedirectResponse(url=f"/projects/{project_id}/settings", status_code=302)


@router.get("/projects/{project_id}/integrations/github/repos")
async def list_github_repos(request: Request, project_id: str):
    user_id = get_current_user_id(request)
    pool = await get_pool()

    await require_project_member(pool, user_id, project_id)

    project = await pool.fetchrow(
        "SELECT github_installation_id FROM projects WHERE id = $1",
        project_id,
    )
    if not project["github_installation_id"]:
        raise HTTPException(status_code=400, detail="GitHub not connected")

    repos = await github_app.get_installation_repos(project["github_installation_id"])
    return repos


# --- Linear OAuth ---

@router.get("/projects/{project_id}/integrations/linear/connect")
async def linear_connect(request: Request, project_id: str):
    user_id = get_current_user_id(request)
    pool = await get_pool()
    await require_project_member(pool, user_id, project_id, min_role="admin")

    state = f"{project_id}:{secrets.token_hex(16)}"
    params = urlencode({
        "client_id": config.LINEAR_CLIENT_ID,
        "redirect_uri": config.LINEAR_REDIRECT_URL,
        "response_type": LINEAR_RESPONSE_TYPE,
        "scope": LINEAR_SCOPE,
        "state": state,
        "actor": LINEAR_ACTOR,
        "prompt": LINEAR_PROMPT,
    })

    response = RedirectResponse(url=f"{LINEAR_AUTH_URL}?{params}")
    response.set_cookie(
        LINEAR_OAUTH_STATE_COOKIE, state,
        httponly=True, samesite="lax", max_age=300,
        secure=request.url.scheme == "https",
    )
    return response


@router.delete("/projects/{project_id}/integrations/github")
async def github_disconnect(request: Request, project_id: str):
    user_id = get_current_user_id(request)
    pool = await get_pool()

    await require_project_member(pool, user_id, project_id, min_role="admin")

    await pool.execute(
        "UPDATE projects SET github_installation_id = NULL, updated_at = now() WHERE id = $1",
        project_id,
    )
    return {"status": STATUS_DISCONNECTED}


@router.delete("/projects/{project_id}/integrations/linear")
async def linear_disconnect(request: Request, project_id: str):
    user_id = get_current_user_id(request)
    pool = await get_pool()

    await require_project_member(pool, user_id, project_id, min_role="admin")

    await pool.execute("""
        UPDATE projects SET
            linear_access_token = NULL,
            linear_refresh_token = NULL,
            linear_organization_id = NULL,
            updated_at = now()
        WHERE id = $1
    """, project_id)
    return {"status": STATUS_DISCONNECTED}


@callbacks_router.get("/linear/callback")
async def linear_callback(request: Request, code: str, state: str):
    stored_state = request.cookies.get(LINEAR_OAUTH_STATE_COOKIE)
    if not stored_state or stored_state != state:
        raise HTTPException(status_code=400, detail="Invalid OAuth state")

    project_id = state.split(":")[0]
    user_id = get_current_user_id(request)

    pool = await get_pool()
    await require_project_member(pool, user_id, project_id, min_role="admin")

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
    response.delete_cookie(LINEAR_OAUTH_STATE_COOKIE)
    return response
