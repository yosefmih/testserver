import logging
import secrets

from fastapi import APIRouter, Request, HTTPException

from config import config
from db import get_pool
from middleware.auth import get_current_user_id, require_project_member

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/projects/{project_id}/invites")
async def list_invites(request: Request, project_id: str):
    user_id = get_current_user_id(request)
    pool = await get_pool()

    await require_project_member(pool, user_id, project_id)

    rows = await pool.fetch("""
        SELECT i.id, i.email, i.role, i.token, i.created_at, i.expires_at,
               u.name AS invited_by_name, u.email AS invited_by_email
        FROM invites i
        JOIN users u ON u.id = i.invited_by
        WHERE i.project_id = $1 AND i.accepted_at IS NULL AND i.expires_at > now()
        ORDER BY i.created_at DESC
    """, project_id)

    return [
        {
            "id": str(r["id"]),
            "email": r["email"],
            "role": r["role"],
            "invited_by": r["invited_by_name"] or r["invited_by_email"],
            "created_at": r["created_at"].isoformat(),
            "expires_at": r["expires_at"].isoformat(),
            "invite_url": f"{config.BASE_URL}/invite/{r['token']}",
        }
        for r in rows
    ]


@router.delete("/projects/{project_id}/invites/{invite_id}")
async def revoke_invite(request: Request, project_id: str, invite_id: str):
    user_id = get_current_user_id(request)
    pool = await get_pool()

    await require_project_member(pool, user_id, project_id, min_role="admin")

    result = await pool.execute(
        "DELETE FROM invites WHERE id = $1 AND project_id = $2 AND accepted_at IS NULL",
        invite_id, project_id,
    )
    if result == "DELETE 0":
        raise HTTPException(status_code=404, detail="Invite not found")

    return {"status": "revoked"}


# --- Public invite endpoints (no project context) ---

public_router = APIRouter()


@public_router.get("/invites/{token}")
async def get_invite(token: str):
    pool = await get_pool()

    row = await pool.fetchrow("""
        SELECT i.id, i.email, i.role, i.accepted_at, i.expires_at,
               p.id AS project_id, p.name AS project_name
        FROM invites i
        JOIN projects p ON p.id = i.project_id
        WHERE i.token = $1
    """, token)

    if not row:
        raise HTTPException(status_code=404, detail="Invite not found")

    if row["accepted_at"]:
        return {"status": "already_accepted", "project_name": row["project_name"], "project_id": str(row["project_id"])}

    from datetime import datetime, timezone
    if row["expires_at"] < datetime.now(timezone.utc):
        return {"status": "expired", "project_name": row["project_name"]}

    return {
        "status": "pending",
        "email": row["email"],
        "role": row["role"],
        "project_id": str(row["project_id"]),
        "project_name": row["project_name"],
    }


@public_router.post("/invites/{token}/accept")
async def accept_invite(request: Request, token: str):
    user_id = get_current_user_id(request)
    pool = await get_pool()

    row = await pool.fetchrow("""
        SELECT i.id, i.email, i.role, i.project_id, i.accepted_at, i.expires_at
        FROM invites i
        WHERE i.token = $1
    """, token)

    if not row:
        raise HTTPException(status_code=404, detail="Invite not found")

    if row["accepted_at"]:
        raise HTTPException(status_code=400, detail="Invite has already been accepted")

    from datetime import datetime, timezone
    if row["expires_at"] < datetime.now(timezone.utc):
        raise HTTPException(status_code=400, detail="Invite has expired")

    user = await pool.fetchrow("SELECT id, email FROM users WHERE id = $1", user_id)

    if user["email"].lower() != row["email"].lower():
        raise HTTPException(
            status_code=403,
            detail=f"This invite was sent to {row['email']}. You are signed in as {user['email']}.",
        )

    existing = await pool.fetchrow(
        "SELECT id FROM project_members WHERE project_id = $1 AND user_id = $2",
        row["project_id"], user_id,
    )
    if existing:
        await pool.execute("UPDATE invites SET accepted_at = now() WHERE id = $1", row["id"])
        return {"status": "already_member", "project_id": str(row["project_id"])}

    await pool.execute(
        "INSERT INTO project_members (project_id, user_id, role) VALUES ($1, $2, $3)",
        row["project_id"], user_id, row["role"],
    )
    await pool.execute("UPDATE invites SET accepted_at = now() WHERE id = $1", row["id"])

    logger.info("User %s accepted invite %s to project %s", user_id, row["id"], row["project_id"])

    return {"status": "accepted", "project_id": str(row["project_id"])}
