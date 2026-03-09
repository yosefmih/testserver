from fastapi import APIRouter, Request, HTTPException
from pydantic import BaseModel

from db import get_pool
from middleware.auth import get_current_user_id

router = APIRouter()


class CreateProjectRequest(BaseModel):
    name: str


@router.get("/projects")
async def list_projects(request: Request):
    user_id = get_current_user_id(request)
    pool = await get_pool()

    rows = await pool.fetch("""
        SELECT id, name, github_installation_id, github_repo,
               linear_team_id, autopilot_label, created_at
        FROM projects
        WHERE user_id = $1
        ORDER BY created_at DESC
    """, user_id)

    return [
        {
            "id": str(r["id"]),
            "name": r["name"],
            "github_connected": r["github_installation_id"] is not None,
            "github_repo": r["github_repo"],
            "linear_connected": r["linear_team_id"] is not None,
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
        SELECT id, name, github_installation_id, github_repo,
               linear_team_id, autopilot_label, created_at
        FROM projects
        WHERE id = $1 AND user_id = $2
    """, project_id, user_id)

    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    jobs = await pool.fetch("""
        SELECT id, linear_issue_id, linear_issue_title, status, pr_url, error, created_at, finished_at
        FROM jobs
        WHERE project_id = $1
        ORDER BY created_at DESC
        LIMIT 50
    """, project_id)

    return {
        "id": str(project["id"]),
        "name": project["name"],
        "github_connected": project["github_installation_id"] is not None,
        "github_repo": project["github_repo"],
        "linear_connected": project["linear_team_id"] is not None,
        "autopilot_label": project["autopilot_label"],
        "created_at": project["created_at"].isoformat(),
        "jobs": [
            {
                "id": str(j["id"]),
                "linear_issue_id": j["linear_issue_id"],
                "linear_issue_title": j["linear_issue_title"],
                "status": j["status"],
                "pr_url": j["pr_url"],
                "error": j["error"],
                "created_at": j["created_at"].isoformat(),
                "finished_at": j["finished_at"].isoformat() if j["finished_at"] else None,
            }
            for j in jobs
        ],
    }


class UpdateProjectSettingsRequest(BaseModel):
    github_repo: str | None = None
    autopilot_label: str | None = None


@router.patch("/projects/{project_id}/settings")
async def update_project_settings(request: Request, project_id: str, body: UpdateProjectSettingsRequest):
    user_id = get_current_user_id(request)
    pool = await get_pool()

    project = await pool.fetchrow(
        "SELECT id FROM projects WHERE id = $1 AND user_id = $2", project_id, user_id
    )
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    updates = []
    params = []
    param_idx = 1

    if body.github_repo is not None:
        updates.append(f"github_repo = ${param_idx}")
        params.append(body.github_repo)
        param_idx += 1

    if body.autopilot_label is not None:
        updates.append(f"autopilot_label = ${param_idx}")
        params.append(body.autopilot_label)
        param_idx += 1

    if not updates:
        raise HTTPException(status_code=400, detail="No fields to update")

    updates.append(f"updated_at = now()")
    params.append(project_id)

    query = f"UPDATE projects SET {', '.join(updates)} WHERE id = ${param_idx}"
    await pool.execute(query, *params)

    return {"status": "updated"}
