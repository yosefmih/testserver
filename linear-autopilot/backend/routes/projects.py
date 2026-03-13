import json
import logging
import re

from fastapi import APIRouter, Request, HTTPException, WebSocket, WebSocketDisconnect
from pydantic import BaseModel
import websockets

from db import get_pool
from middleware.auth import get_current_user_id
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
        SELECT id, name, github_installation_id,
               linear_access_token, linear_organization_id, anthropic_api_key,
               autopilot_label, created_at
        FROM projects
        WHERE user_id = $1
        ORDER BY created_at DESC
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

    return {
        "id": str(row["id"]),
        "name": row["name"],
        "created_at": row["created_at"].isoformat(),
    }


@router.get("/projects/{project_id}")
async def get_project(request: Request, project_id: str):
    user_id = get_current_user_id(request)
    pool = await get_pool()

    project = await pool.fetchrow("""
        SELECT id, name, github_installation_id,
               linear_access_token, linear_organization_id, anthropic_api_key,
               custom_tools, system_prompt, autopilot_label, created_at
        FROM projects
        WHERE id = $1 AND user_id = $2
    """, project_id, user_id)

    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

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

    project = await pool.fetchrow(
        "SELECT id FROM projects WHERE id = $1 AND user_id = $2", project_id, user_id
    )
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

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

    project = await pool.fetchrow(
        "SELECT id FROM projects WHERE id = $1 AND user_id = $2", project_id, user_id
    )
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    await pool.execute("DELETE FROM review_comments WHERE ticket_id IN (SELECT id FROM tickets WHERE project_id = $1)", project_id)
    await pool.execute("DELETE FROM runs WHERE ticket_id IN (SELECT id FROM tickets WHERE project_id = $1)", project_id)
    await pool.execute("DELETE FROM tickets WHERE project_id = $1", project_id)
    await pool.execute("DELETE FROM projects WHERE id = $1", project_id)

    return {"status": "deleted"}


# --- Ticket routes ---

@router.get("/projects/{project_id}/tickets/{ticket_id}")
async def get_ticket(request: Request, project_id: str, ticket_id: str):
    user_id = get_current_user_id(request)
    pool = await get_pool()

    project = await pool.fetchrow(
        "SELECT id FROM projects WHERE id = $1 AND user_id = $2", project_id, user_id
    )
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

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

    project = await pool.fetchrow(
        "SELECT id FROM projects WHERE id = $1 AND user_id = $2", project_id, user_id
    )
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

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

    project = await pool.fetchrow(
        "SELECT id FROM projects WHERE id = $1 AND user_id = $2", project_id, user_id
    )
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

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

    project = await pool.fetchrow(
        "SELECT id FROM projects WHERE id = $1 AND user_id = $2", project_id, user_id
    )
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

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
        lines = [_clean_log_line(line) for line in raw_lines]
        return {"logs": lines}
    except Exception as e:
        logger.warning("Failed to fetch sandbox logs for run %s: %s", run_id, e)
        return {"logs": [], "error": f"Sandbox logs unavailable: {e}"}


_LOG_PREFIX_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T[\d:.]+Z\s+(stdout|stderr)\s+F\s+")


def _clean_log_line(line: str) -> str:
    return _LOG_PREFIX_RE.sub("", line)


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
        async with websockets.connect(upstream_url) as upstream:
            async for raw_msg in upstream:
                try:
                    msg = json.loads(raw_msg)
                    for stream in msg.get('streams', []):
                        for _ts, line in stream.get('values', []):
                            cleaned = _clean_log_line(line)
                            await ws.send_text(cleaned)
                except json.JSONDecodeError:
                    pass
    except WebSocketDisconnect:
        pass
    except Exception as e:
        logger.error('Log stream error for run %s (sandbox %s): %s', run_id, run['sandbox_id'], e)
