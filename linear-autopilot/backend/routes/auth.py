import hashlib
import hmac
import os
import secrets
from datetime import datetime, timedelta, timezone
from urllib.parse import urlencode

import httpx
import jwt
from fastapi import APIRouter, Request, Response, HTTPException
from fastapi.responses import RedirectResponse

from config import config
from db import get_pool

router = APIRouter()

GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GOOGLE_USERINFO_URL = "https://www.googleapis.com/oauth2/v3/userinfo"
GOOGLE_SCOPES = "openid email profile"


def _create_session_token(user_id: str, email: str) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "user_id": user_id,
        "email": email,
        "iat": now,
        "exp": now + timedelta(minutes=config.SESSION_TTL_MINUTES),
    }
    return jwt.encode(payload, config.JWT_SECRET, algorithm=config.JWT_ALGORITHM)


@router.get("/google/login")
async def google_login(request: Request):
    state = secrets.token_hex(16)

    params = urlencode({
        "client_id": config.GOOGLE_CLIENT_ID,
        "redirect_uri": config.GOOGLE_REDIRECT_URL,
        "response_type": "code",
        "scope": GOOGLE_SCOPES,
        "state": state,
        "access_type": "offline",
        "prompt": "consent",
    })

    response = RedirectResponse(url=f"{GOOGLE_AUTH_URL}?{params}")
    response.set_cookie(
        "oauth_state",
        state,
        httponly=True,
        samesite="lax",
        max_age=300,
        secure=request.url.scheme == "https",
    )
    return response


@router.get("/google/callback")
async def google_callback(request: Request, code: str, state: str):
    stored_state = request.cookies.get("oauth_state")
    if not stored_state or not hmac.compare_digest(stored_state, state):
        raise HTTPException(status_code=400, detail="Invalid OAuth state")

    async with httpx.AsyncClient() as client:
        token_resp = await client.post(GOOGLE_TOKEN_URL, data={
            "code": code,
            "client_id": config.GOOGLE_CLIENT_ID,
            "client_secret": config.GOOGLE_CLIENT_SECRET,
            "redirect_uri": config.GOOGLE_REDIRECT_URL,
            "grant_type": "authorization_code",
        })
        if token_resp.status_code != 200:
            raise HTTPException(status_code=400, detail="Failed to exchange code for token")
        tokens = token_resp.json()

        userinfo_resp = await client.get(GOOGLE_USERINFO_URL, headers={
            "Authorization": f"Bearer {tokens['access_token']}"
        })
        if userinfo_resp.status_code != 200:
            raise HTTPException(status_code=400, detail="Failed to fetch user info")
        userinfo = userinfo_resp.json()

    pool = await get_pool()
    user = await pool.fetchrow("""
        INSERT INTO users (email, name, google_id, avatar_url)
        VALUES ($1, $2, $3, $4)
        ON CONFLICT (google_id) DO UPDATE SET
            email = EXCLUDED.email,
            name = EXCLUDED.name,
            avatar_url = EXCLUDED.avatar_url,
            updated_at = now()
        RETURNING id, email
    """, userinfo["email"], userinfo.get("name", ""), userinfo["sub"], userinfo.get("picture"))

    session_token = _create_session_token(str(user["id"]), user["email"])

    response = RedirectResponse(url="/projects", status_code=302)
    response.set_cookie(
        config.SESSION_COOKIE_NAME,
        session_token,
        httponly=True,
        samesite="lax",
        max_age=config.SESSION_TTL_MINUTES * 60,
        secure=request.url.scheme == "https",
    )
    response.delete_cookie("oauth_state")
    return response


@router.post("/logout")
async def logout():
    response = Response(status_code=200)
    response.delete_cookie(config.SESSION_COOKIE_NAME)
    return response


@router.get("/me")
async def get_me(request: Request):
    from middleware.auth import get_current_user_id
    user_id = get_current_user_id(request)

    pool = await get_pool()
    user = await pool.fetchrow(
        "SELECT id, email, name, avatar_url FROM users WHERE id = $1", user_id
    )
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    return {
        "id": str(user["id"]),
        "email": user["email"],
        "name": user["name"],
        "avatar_url": user["avatar_url"],
    }
