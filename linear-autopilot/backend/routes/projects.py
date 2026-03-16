import json
import logging
import re
import secrets

from fastapi import APIRouter, Request, HTTPException, WebSocket, WebSocketDisconnect
from pydantic import BaseModel
import websockets

from config import config
from db import get_pool
from middleware.auth import get_current_user_id, require_project_member
from services.sandbox_runner import SANDBOX_API_URL

logger = logging.getLogger(__name__)

router = APIRouter()

# Ticket status constants
TICKET_STATUS_ACTIVE = "active"
TICKET_STATUS_CANCELLED = "cancelled"
TICKET_STATUS_CLOSED = "closed"
TICKET_STATUS_FAILED = "failed"
TICKET_STATUS_MERGED = "merged"

# Run status constants
RUN_STATUS_PENDING = "pending"
RUN_STATUS_LAUNCHING = "launching"
RUN_STATUS_RUNNING = "running"
RUN_STATUS_CANCELLED = "cancelled"

ACTIVE_RUN_STATUSES = (RUN_STATUS_PENDING, RUN_STATUS_LAUNCHING, RUN_STATUS_RUNNING)


class CreateProjectRequest(BaseModel):
    name: str


@router.get("/projects")
async def list_projects(request: Request):
    user_id = get_current_user_id(request)
    pool = await get_pool()

    rows = await pool.fetch("""
        SELECT p.id, p.name, p.github_installation_id,
               p.linear_access_token, p.linear_organization_id, p.anthropic_api_key,
               p.autopilot_label, p.created_at, pm.role
        FROM projects p
        JOIN project_members pm ON pm.project_id = p.id
        WHERE pm.user_id = $1
        ORDER BY p.created_at DESC
    """, user_id)

    return [
        {
            "id": str(r["id"]),
            "name": r["name"],
            "github_connected": r["github_installation_id"] is not None,
            "linear_connected": r["linear_organization_id"] is not None,
            "linear_has_token": r["linear_access_token"] is not None,
            "claude_connected": r["anthropic_api_key"] is not None,
            "autopilot_label": r["autopilot_label"],
            "created_at": r["created_at"].isoformat(),
            "role": r["role"],
        }
        for r in rows
    ]


@router.post("/projects")
async def create_project(request: Request, body: CreateProjectRequest):
    user_id = get_current_user_id(request)
    pool = await get_pool()

    row = await pool.fetchrow(
        "INSERT INTO projects (user_id, name) VALUES ($1, $2) RETURNING id, name, created_at",
        user_id, body.name,
    )

    await pool.execute(
        "INSERT INTO project_members (project_id, user_id, role) VALUES ($1, $2, 'admin')",
        row["id"], user_id,
    )

    return {
        "id": str(row["id"]),
        "name": row["name"],
        "created_at": row["created_at"].isoformat(),
    }


@router.get("/projects/{project_id}")
async def get_project(request: Request, project_id: str):
    user_id = get_current_user_id(request)
    pool = await get_pool()

    role = await require_project_member(pool, user_id, project_id)

    project = await pool.fetchrow("""
        SELECT id, name, github_installation_id,
               linear_access_token, linear_organization_id, anthropic_api_key,
               custom_tools, system_prompt, autopilot_label, created_at
        FROM projects
        WHERE id = $1
    """, project_id)

    tickets = await pool.fetch("""
        SELECT id, linear_issue_id, linear_issue_title, linear_issue_url,
               pr_url, status, created_at, updated_at
        FROM tickets
        WHERE project_id = $1
        ORDER BY created_at DESC
        LIMIT 50
    """, project_id)

    return {
        "id": str(project["id"]),
        "name": project["name"],
        "github_connected": project["github_installation_id"] is not None,
        "linear_connected": project["linear_organization_id"] is not None,
        "linear_has_token": project["linear_access_token"] is not None,
        "claude_connected": project["anthropic_api_key"] is not None,
        "linear_organization_id": project["linear_organization_id"],
        "autopilot_label": project["autopilot_label"],
        "custom_tools": project["custom_tools"] or "",
        "system_prompt": project["system_prompt"] or "",
        "created_at": project["created_at"].isoformat(),
        "role": role,
        "tickets": [
            {
                "id": str(t["id"]),
                "linear_issue_id": t["linear_issue_id"],
                "linear_issue_title": t["linear_issue_title"],
                "linear_issue_url": t["linear_issue_url"],
                "pr_url": t["pr_url"],
                "status": t["status"],
                "created_at": t["created_at"].isoformat(),
                "updated_at": t["updated_at"].isoformat(),
            }
            for t in tickets
        ],
    }


class UpdateProjectSettingsRequest(BaseModel):
    autopilot_label: str | None = None
    custom_tools: str | None = None
    system_prompt: str | None = None
    anthropic_api_key: str | None = None


@router.patch("/projects/{project_id}/settings")
async def update_project_settings(request: Request, project_id: str, body: UpdateProjectSettingsRequest):
    user_id = get_current_user_id(request)
    pool = await get_pool()

    await require_project_member(pool, user_id, project_id, min_role="admin")

    field_map = {
        "autopilot_label": body.autopilot_label,
        "custom_tools": body.custom_tools,
        "system_prompt": body.system_prompt,
        "anthropic_api_key": body.anthropic_api_key,
    }

    updates = []
    params = []
    param_idx = 1

    for col, val in field_map.items():
        if val is not None:
            updates.append(f"{col} = ${param_idx}")
            params.append(val)
            param_idx += 1

    if not updates:
        raise HTTPException(status_code=400, detail="No fields to update")

    updates.append("updated_at = now()")
    params.append(project_id)

    query = f"UPDATE projects SET {', '.join(updates)} WHERE id = ${param_idx}"
    await pool.execute(query, *params)

    return {"status": "updated"}


@router.delete("/projects/{project_id}")
async def delete_project(request: Request, project_id: str):
    user_id = get_current_user_id(request)
    pool = await get_pool()

    await require_project_member(pool, user_id, project_id, min_role="admin")

    await pool.execute("DELETE FROM review_comments WHERE ticket_id IN (SELECT id FROM tickets WHERE project_id = $1)", project_id)
    await pool.execute("DELETE FROM runs WHERE ticket_id IN (SELECT id FROM tickets WHERE project_id = $1)", project_id)
    await pool.execute("DELETE FROM tickets WHERE project_id = $1", project_id)
    await pool.execute("DELETE FROM invites WHERE project_id = $1", project_id)
    await pool.execute("DELETE FROM project_members WHERE project_id = $1", project_id)
    await pool.execute("DELETE FROM projects WHERE id = $1", project_id)

    return {"status": "deleted"}


# --- Ticket routes ---

@router.get("/projects/{project_id}/tickets/{ticket_id}")
async def get_ticket(request: Request, project_id: str, ticket_id: str):
    user_id = get_current_user_id(request)
    pool = await get_pool()

    await require_project_member(pool, user_id, project_id)

    ticket = await pool.fetchrow("""
        SELECT id, linear_issue_id, linear_issue_title, linear_issue_url,
               pr_repo, pr_number, pr_url, volume_id, status, created_at, updated_at
        FROM tickets WHERE id = $1 AND project_id = $2
    """, ticket_id, project_id)
    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket not found")

    runs = await pool.fetch("""
        SELECT id, kind, sandbox_id, status, error, created_at, finished_at
        FROM runs WHERE ticket_id = $1
        ORDER BY created_at DESC
    """, ticket_id)

    return {
        "id": str(ticket["id"]),
        "linear_issue_id": ticket["linear_issue_id"],
        "linear_issue_title": ticket["linear_issue_title"],
        "linear_issue_url": ticket["linear_issue_url"],
        "pr_repo": ticket["pr_repo"],
        "pr_number": ticket["pr_number"],
        "pr_url": ticket["pr_url"],
        "volume_id": ticket["volume_id"],
        "status": ticket["status"],
        "created_at": ticket["created_at"].isoformat(),
        "updated_at": ticket["updated_at"].isoformat(),
        "runs": [
            {
                "id": str(r["id"]),
                "kind": r["kind"],
                "sandbox_id": r["sandbox_id"],
                "status": r["status"],
                "error": r["error"],
                "created_at": r["created_at"].isoformat(),
                "finished_at": r["finished_at"].isoformat() if r["finished_at"] else None,
            }
            for r in runs
        ],
    }


@router.post("/projects/{project_id}/tickets/{ticket_id}/trigger-review")
async def trigger_review(request: Request, project_id: str, ticket_id: str):
    user_id = get_current_user_id(request)
    pool = await get_pool()

    await require_project_member(pool, user_id, project_id)

    ticket = await pool.fetchrow(
        "SELECT id, status, pr_url FROM tickets WHERE id = $1 AND project_id = $2",
        ticket_id, project_id,
    )
    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket not found")
    if ticket["status"] != TICKET_STATUS_ACTIVE:
        raise HTTPException(status_code=400, detail="Ticket is not active")
    if not ticket["pr_url"]:
        raise HTTPException(status_code=400, detail="Ticket has no PR")

    active = await pool.fetchval(f"""
        SELECT COUNT(*) FROM runs
        WHERE ticket_id = $1 AND status IN ('{RUN_STATUS_PENDING}', '{RUN_STATUS_LAUNCHING}', '{RUN_STATUS_RUNNING}')
    """, ticket_id)
    if active > 0:
        raise HTTPException(status_code=409, detail="A run is already in progress")

    await pool.execute("""
        INSERT INTO runs (ticket_id, kind, status) VALUES ($1, 'review', 'pending')
    """, ticket_id)
    await pool.execute(
        "UPDATE tickets SET debounce_until = NULL, updated_at = now() WHERE id = $1",
        ticket_id,
    )

    logger.info("Manual review triggered for ticket %s", ticket_id)
    return {"status": "triggered"}


@router.delete("/projects/{project_id}/tickets/{ticket_id}")
async def cancel_ticket(request: Request, project_id: str, ticket_id: str):
    user_id = get_current_user_id(request)
    pool = await get_pool()

    await require_project_member(pool, user_id, project_id)

    ticket = await pool.fetchrow(
        "SELECT id, status, volume_id FROM tickets WHERE id = $1 AND project_id = $2",
        ticket_id, project_id,
    )
    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket not found")

    active_runs = await pool.fetch(f"""
        SELECT id, sandbox_id FROM runs
        WHERE ticket_id = $1 AND status IN ('{RUN_STATUS_PENDING}', '{RUN_STATUS_LAUNCHING}', '{RUN_STATUS_RUNNING}')
    """, ticket_id)

    for run in active_runs:
        if run["sandbox_id"]:
            try:
                from porter_sandbox_api_client.api.sandboxes import delete_sandbox
                from services.sandbox_runner import sandbox_client
                delete_sandbox.sync(id=run["sandbox_id"], client=sandbox_client)
            except Exception as e:
                logger.warning("Failed to delete sandbox %s: %s", run["sandbox_id"], e)

        await pool.execute(
            f"UPDATE runs SET status = '{RUN_STATUS_CANCELLED}', finished_at = now() WHERE id = $1",
            str(run["id"]),
        )

    if ticket["volume_id"]:
        try:
            from porter_sandbox_api_client.api.volumes import delete_volume
            from services.sandbox_runner import sandbox_client
            delete_volume.sync(id=ticket["volume_id"], client=sandbox_client)
            logger.info("Deleted volume %s for ticket %s", ticket["volume_id"], ticket_id)
        except Exception as e:
            logger.warning("Failed to delete volume %s: %s", ticket["volume_id"], e)

    await pool.execute(
        f"UPDATE tickets SET status = '{TICKET_STATUS_CANCELLED}', debounce_until = NULL, updated_at = now() WHERE id = $1",
        ticket_id,
    )

    return {"status": TICKET_STATUS_CANCELLED}


@router.get("/projects/{project_id}/tickets/{ticket_id}/runs/{run_id}/logs")
async def get_run_logs(request: Request, project_id: str, ticket_id: str, run_id: str):
    user_id = get_current_user_id(request)
    pool = await get_pool()

    await require_project_member(pool, user_id, project_id)

    run = await pool.fetchrow("""
        SELECT r.sandbox_id, r.status
        FROM runs r
        JOIN tickets t ON t.id = r.ticket_id
        WHERE r.id = $1 AND r.ticket_id = $2 AND t.project_id = $3
    """, run_id, ticket_id, project_id)
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")

    if not run["sandbox_id"]:
        return {"logs": [], "error": "No sandbox associated with this run"}

    try:
        from porter_sandbox_api_client.api.sandboxes import get_sandbox_logs
        from services.sandbox_runner import sandbox_client

        response = get_sandbox_logs.sync(id=run["sandbox_id"], client=sandbox_client)
        raw_lines = response.logs if hasattr(response, "logs") and response.logs else []
        lines = _reassemble_lines(raw_lines)
        return {"logs": lines}
    except Exception as e:
        logger.warning("Failed to fetch sandbox logs for run %s: %s", run_id, e)
        return {"logs": [], "error": f"Sandbox logs unavailable: {e}"}


_LOG_PREFIX_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T[\d:.]+Z\s+(stdout|stderr)\s+([FP])\s+")


def _is_partial(line: str) -> bool:
    m = _LOG_PREFIX_RE.match(line)
    return m is not None and m.group(2) == "P"


def _clean_log_line(line: str) -> str:
    return _LOG_PREFIX_RE.sub("", line)


def _reassemble_lines(raw_lines: list[str]) -> list[str]:
    result = []
    buf = ""
    for line in raw_lines:
        partial = _is_partial(line)
        cleaned = _clean_log_line(line)
        buf += cleaned
        if not partial:
            result.append(buf)
            buf = ""
    if buf:
        result.append(buf)
    return result


@router.websocket('/projects/{project_id}/tickets/{ticket_id}/runs/{run_id}/logs/stream')
async def stream_run_logs(ws: WebSocket, project_id: str, ticket_id: str, run_id: str):
    pool = await get_pool()

    run = await pool.fetchrow("""
        SELECT r.sandbox_id, r.status
        FROM runs r
        JOIN tickets t ON t.id = r.ticket_id
        WHERE r.id = $1 AND r.ticket_id = $2 AND t.project_id = $3
    """, run_id, ticket_id, project_id)

    if not run or not run['sandbox_id']:
        await ws.close(code=4004, reason='Run not found or no sandbox')
        return

    await ws.accept()

    central_ws_url = SANDBOX_API_URL.replace('http://', 'ws://').replace('https://', 'wss://')
    upstream_url = f'{central_ws_url}/v1/sandbox/{run["sandbox_id"]}/logs/stream'

    try:
        partial_buf = ""
        async with websockets.connect(upstream_url) as upstream:
            async for raw_msg in upstream:
                try:
                    msg = json.loads(raw_msg)
                    for stream in msg.get('streams', []):
                        for _ts, line in stream.get('values', []):
                            partial = _is_partial(line)
                            cleaned = _clean_log_line(line)
                            partial_buf += cleaned
                            if not partial:
                                await ws.send_text(partial_buf)
                                partial_buf = ""
                except json.JSONDecodeError:
                    pass
    except WebSocketDisconnect:
        pass
    except Exception as e:
        logger.error('Log stream error for run %s (sandbox %s): %s', run_id, run['sandbox_id'], e)


# --- Member routes ---

@router.get("/projects/{project_id}/members")
async def list_members(request: Request, project_id: str):
    user_id = get_current_user_id(request)
    pool = await get_pool()

    await require_project_member(pool, user_id, project_id)

    rows = await pool.fetch("""
        SELECT pm.id, pm.role, pm.created_at,
               u.id AS user_id, u.email, u.name, u.avatar_url
        FROM project_members pm
        JOIN users u ON u.id = pm.user_id
        WHERE pm.project_id = $1
        ORDER BY pm.created_at ASC
    """, project_id)

    return [
        {
            "id": str(r["id"]),
            "user_id": str(r["user_id"]),
            "email": r["email"],
            "name": r["name"],
            "avatar_url": r["avatar_url"],
            "role": r["role"],
            "created_at": r["created_at"].isoformat(),
        }
        for r in rows
    ]


class AddMemberRequest(BaseModel):
    email: str
    role: str = "developer"


@router.post("/projects/{project_id}/members")
async def add_member(request: Request, project_id: str, body: AddMemberRequest):
    user_id = get_current_user_id(request)
    pool = await get_pool()

    await require_project_member(pool, user_id, project_id, min_role="admin")

    if body.role not in ("admin", "developer"):
        raise HTTPException(status_code=400, detail="Role must be 'admin' or 'developer'")

    target_user = await pool.fetchrow("SELECT id FROM users WHERE email = $1", body.email)

    if not target_user:
        existing_invite = await pool.fetchrow(
            "SELECT id FROM invites WHERE project_id = $1 AND email = $2 AND accepted_at IS NULL AND expires_at > now()",
            project_id, body.email,
        )
        if existing_invite:
            raise HTTPException(status_code=409, detail="An invite has already been sent to this email")

        token = secrets.token_urlsafe(32)
        row = await pool.fetchrow("""
            INSERT INTO invites (project_id, email, role, token, invited_by)
            VALUES ($1, $2, $3, $4, $5)
            ON CONFLICT (project_id, email) DO UPDATE SET
                role = EXCLUDED.role, token = EXCLUDED.token,
                invited_by = EXCLUDED.invited_by,
                expires_at = now() + INTERVAL '7 days',
                accepted_at = NULL
            RETURNING id, created_at, expires_at
        """, project_id, body.email, body.role, token, user_id)

        invite_url = f"{config.BASE_URL}/invite/{token}"
        logger.info("Created invite for %s to project %s: %s", body.email, project_id, invite_url)

        return {
            "id": str(row["id"]),
            "email": body.email,
            "role": body.role,
            "status": "invited",
            "invite_url": invite_url,
            "created_at": row["created_at"].isoformat(),
            "expires_at": row["expires_at"].isoformat(),
        }

    existing = await pool.fetchrow(
        "SELECT id FROM project_members WHERE project_id = $1 AND user_id = $2",
        project_id, target_user["id"],
    )
    if existing:
        raise HTTPException(status_code=409, detail="User is already a member of this project")

    row = await pool.fetchrow(
        "INSERT INTO project_members (project_id, user_id, role) VALUES ($1, $2, $3) RETURNING id, created_at",
        project_id, target_user["id"], body.role,
    )

    return {
        "id": str(row["id"]),
        "user_id": str(target_user["id"]),
        "email": body.email,
        "role": body.role,
        "status": "added",
        "created_at": row["created_at"].isoformat(),
    }


class UpdateMemberRequest(BaseModel):
    role: str


@router.patch("/projects/{project_id}/members/{member_id}")
async def update_member(request: Request, project_id: str, member_id: str):
    user_id = get_current_user_id(request)
    pool = await get_pool()

    await require_project_member(pool, user_id, project_id, min_role="admin")

    body = UpdateMemberRequest(**(await request.json()))
    if body.role not in ("admin", "developer"):
        raise HTTPException(status_code=400, detail="Role must be 'admin' or 'developer'")

    member = await pool.fetchrow(
        "SELECT id, user_id FROM project_members WHERE id = $1 AND project_id = $2",
        member_id, project_id,
    )
    if not member:
        raise HTTPException(status_code=404, detail="Member not found")

    await pool.execute(
        "UPDATE project_members SET role = $1 WHERE id = $2",
        body.role, member_id,
    )

    return {"status": "updated"}


@router.delete("/projects/{project_id}/members/{member_id}")
async def remove_member(request: Request, project_id: str, member_id: str):
    user_id = get_current_user_id(request)
    pool = await get_pool()

    await require_project_member(pool, user_id, project_id, min_role="admin")

    member = await pool.fetchrow(
        "SELECT id, user_id FROM project_members WHERE id = $1 AND project_id = $2",
        member_id, project_id,
    )
    if not member:
        raise HTTPException(status_code=404, detail="Member not found")

    if str(member["user_id"]) == user_id:
        raise HTTPException(status_code=400, detail="Cannot remove yourself from the project")

    admin_count = await pool.fetchval(
        "SELECT COUNT(*) FROM project_members WHERE project_id = $1 AND role = 'admin'",
        project_id,
    )
    if admin_count <= 1 and member["user_id"] != user_id:
        current_member_role = await pool.fetchval(
            "SELECT role FROM project_members WHERE id = $1", member_id
        )
        if current_member_role == "admin":
            raise HTTPException(status_code=400, detail="Cannot remove the last admin")

    await pool.execute("DELETE FROM project_members WHERE id = $1", member_id)

    return {"status": "removed"}
