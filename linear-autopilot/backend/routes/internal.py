import logging

from fastapi import APIRouter, Request, HTTPException
from pydantic import BaseModel

from db import get_pool
from services.linear_oauth import post_issue_comment

router = APIRouter()
logger = logging.getLogger(__name__)


class RunMetadata(BaseModel):
    pr_url: str | None = None
    pr_repo: str | None = None
    pr_number: int | None = None
    status: str | None = None
    summary: str | None = None


@router.post("/runs/{run_id}/metadata")
async def report_run_metadata(request: Request, run_id: str, body: RunMetadata):
    token = request.headers.get("Authorization", "").removeprefix("Bearer ").strip()
    if not token:
        token = request.query_params.get("token", "")

    pool = await get_pool()

    run = await pool.fetchrow("""
        SELECT r.id, r.ticket_id, r.callback_token, r.status
        FROM runs r WHERE r.id = $1
    """, run_id)

    if not run:
        raise HTTPException(status_code=404, detail="Run not found")

    if not run["callback_token"] or run["callback_token"] != token:
        raise HTTPException(status_code=401, detail="Invalid callback token")

    ticket_id = str(run["ticket_id"])

    if body.pr_url or body.pr_repo or body.pr_number:
        updates = []
        params = []
        idx = 1

        if body.pr_url:
            updates.append(f"pr_url = ${idx}")
            params.append(body.pr_url)
            idx += 1
        if body.pr_repo:
            updates.append(f"pr_repo = ${idx}")
            params.append(body.pr_repo)
            idx += 1
        if body.pr_number:
            updates.append(f"pr_number = ${idx}")
            params.append(body.pr_number)
            idx += 1

        updates.append("updated_at = now()")
        params.append(ticket_id)

        query = f"UPDATE tickets SET {', '.join(updates)} WHERE id = ${idx}"
        await pool.execute(query, *params)
        logger.info("Run %s reported PR metadata for ticket %s: url=%s repo=%s number=%s",
                     run_id, ticket_id, body.pr_url, body.pr_repo, body.pr_number)

        if body.pr_url:
            try:
                ticket = await pool.fetchrow("""
                    SELECT t.linear_issue_id, p.linear_access_token
                    FROM tickets t
                    JOIN projects p ON p.id = t.project_id
                    WHERE t.id = $1
                """, ticket_id)
                if ticket and ticket["linear_access_token"]:
                    pr_label = f"#{body.pr_number}" if body.pr_number else "PR"
                    await post_issue_comment(
                        ticket["linear_access_token"],
                        ticket["linear_issue_id"],
                        f"**Pull request opened:** [{pr_label}]({body.pr_url})",
                    )
            except Exception:
                logger.warning("Failed to post PR comment to Linear for ticket %s", ticket_id)

    if body.summary:
        await pool.execute(
            "UPDATE runs SET summary = $1 WHERE id = $2",
            body.summary, run_id,
        )
        logger.info("Run %s saved summary for ticket %s", run_id, ticket_id)

    await pool.execute(
        "UPDATE runs SET callback_token = NULL WHERE id = $1",
        run_id,
    )

    return {"status": "ok"}
