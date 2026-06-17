import jwt
from fastapi import Request, HTTPException

from config import config


def get_current_user_id(request: Request) -> str:
    token = request.cookies.get(config.SESSION_COOKIE_NAME)
    if not token:
        raise HTTPException(status_code=401, detail="Not authenticated")

    try:
        payload = jwt.decode(token, config.JWT_SECRET, algorithms=[config.JWT_ALGORITHM])
        return payload["user_id"]
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Session expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid session")


async def require_project_member(pool, user_id: str, project_id: str, min_role: str = "developer") -> str:
    """Check that user is a member of the project and return their role.
    Raises 404 if not a member. If min_role is 'admin', raises 403 for developers."""
    row = await pool.fetchrow(
        "SELECT role FROM project_members WHERE project_id = $1 AND user_id = $2",
        project_id, user_id,
    )
    if not row:
        raise HTTPException(status_code=404, detail="Project not found")
    if min_role == "admin" and row["role"] != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    return row["role"]
