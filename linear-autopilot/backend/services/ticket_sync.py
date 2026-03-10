import asyncio
import logging
from datetime import datetime, timezone

from porter_sandbox_api_client.api.sandboxes import get_sandbox, delete_sandbox

from config import config
from db import get_pool
from services.sandbox_runner import (
    sandbox_client, create_sandbox_for_run, create_volume_for_ticket,
    generate_callback_token, parse_sandbox_phase, parse_sandbox_exit_code,
)
from services.linear_oauth import post_issue_comment

logger = logging.getLogger(__name__)

SYNC_INTERVAL_SECONDS = 15


async def _launch_pending_runs():
    pool = await get_pool()

    runs = await pool.fetch("""
        SELECT r.id, r.ticket_id, r.kind,
               t.linear_issue_id, t.linear_issue_title, t.linear_issue_description,
               t.linear_issue_url, t.volume_id, t.pr_url, t.project_id,
               p.github_installation_id, p.linear_access_token
        FROM runs r
        JOIN tickets t ON t.id = r.ticket_id
        JOIN projects p ON p.id = t.project_id
        WHERE r.status = 'pending'
        ORDER BY r.created_at ASC
    """)

    if not runs:
        return

    logger.info("Ticket sync: launching %d pending runs", len(runs))

    for run in runs:
        run_id = str(run["id"])
        ticket_id = str(run["ticket_id"])

        active_run = await pool.fetchrow("""
            SELECT id FROM runs
            WHERE ticket_id = $1 AND status IN ('launching', 'running') AND id != $2
        """, ticket_id, run_id)
        if active_run:
            logger.info("Ticket sync: skipping run %s, ticket %s has active run", run_id, ticket_id)
            continue

        try:
            await pool.execute("UPDATE runs SET status = 'launching' WHERE id = $1", run_id)

            volume_id = run["volume_id"]
            if not volume_id:
                volume_id = await create_volume_for_ticket()
                await pool.execute(
                    "UPDATE tickets SET volume_id = $1, updated_at = now() WHERE id = $2",
                    volume_id, ticket_id,
                )

            callback_token = generate_callback_token()
            await pool.execute(
                "UPDATE runs SET callback_token = $1 WHERE id = $2",
                callback_token, run_id,
            )

            pr_repo = None
            pr_number = None
            if run["kind"] == "review":
                ticket_info = await pool.fetchrow(
                    "SELECT pr_repo, pr_number FROM tickets WHERE id = $1",
                    ticket_id,
                )
                if ticket_info:
                    pr_repo = ticket_info["pr_repo"]
                    pr_number = ticket_info["pr_number"]

            sandbox_id = await create_sandbox_for_run(
                run_id=run_id,
                callback_token=callback_token,
                kind=run["kind"],
                volume_id=volume_id,
                issue_id=run["linear_issue_id"],
                issue_title=run["linear_issue_title"],
                issue_description=run["linear_issue_description"] or "",
                issue_url=run["linear_issue_url"] or "",
                github_installation_id=run["github_installation_id"],
                linear_access_token=run["linear_access_token"],
                pr_url=run["pr_url"],
                pr_repo=pr_repo,
                pr_number=pr_number,
            )

            await pool.execute(
                "UPDATE runs SET status = 'running', sandbox_id = $1 WHERE id = $2",
                sandbox_id, run_id,
            )
            logger.info("Ticket sync: run %s launched sandbox %s", run_id, sandbox_id)

            if run["kind"] == "initial" and run["linear_access_token"]:
                try:
                    ticket_url = f"{config.BASE_URL}/projects/{run['project_id']}/tickets/{ticket_id}"
                    await post_issue_comment(
                        run["linear_access_token"],
                        run["linear_issue_id"],
                        f"Autopilot is working on this issue. [View ticket]({ticket_url})",
                    )
                except Exception:
                    logger.warning("Ticket sync: failed to post launch comment for run %s", run_id)

        except Exception as e:
            logger.exception("Ticket sync: failed to launch run %s", run_id)
            await pool.execute(
                "UPDATE runs SET status = 'failed', error = $1, finished_at = now() WHERE id = $2",
                str(e), run_id,
            )
            remaining = await pool.fetchval("""
                SELECT COUNT(*) FROM runs
                WHERE ticket_id = $1 AND status IN ('pending', 'launching', 'running') AND id != $2
            """, ticket_id, run_id)
            if remaining == 0:
                await pool.execute(
                    "UPDATE tickets SET status = 'failed', updated_at = now() WHERE id = $1 AND status = 'active'",
                    ticket_id,
                )


async def _sync_active_runs():
    pool = await get_pool()

    runs = await pool.fetch("""
        SELECT r.id, r.sandbox_id, r.ticket_id, r.kind
        FROM runs r
        WHERE r.status = 'running' AND r.sandbox_id IS NOT NULL
    """)

    if not runs:
        return

    logger.info("Ticket sync: checking %d running runs", len(runs))

    for run in runs:
        run_id = str(run["id"])
        sandbox_id = run["sandbox_id"]
        ticket_id = str(run["ticket_id"])

        try:
            status_response = get_sandbox.sync(id=sandbox_id, client=sandbox_client)
            phase = parse_sandbox_phase(status_response)
            exit_code = parse_sandbox_exit_code(status_response)

            logger.info("Ticket sync: run=%s sandbox=%s phase=%s exit_code=%r", run_id, sandbox_id, phase, exit_code)

            terminal = False
            final_status = None

            if exit_code is not None:
                terminal = True
                final_status = "success" if exit_code == 0 else "failed"
            elif phase in ("succeeded", "failed", "cancelled"):
                terminal = True
                final_status = "success" if phase == "succeeded" else "failed"

            if not terminal:
                continue

            error_text = None
            if final_status == "failed":
                try:
                    from porter_sandbox_api_client.api.sandboxes import get_sandbox_logs
                    logs_response = get_sandbox_logs.sync(id=sandbox_id, client=sandbox_client)
                    if hasattr(logs_response, "logs") and logs_response.logs:
                        log_text = "\n".join(logs_response.logs)
                        error_text = log_text[-2000:]
                except Exception:
                    error_text = f"Sandbox exited: phase={phase} exit_code={exit_code}"

            await pool.execute("""
                UPDATE runs SET status = $1, error = $2, finished_at = now()
                WHERE id = $3 AND status = 'running'
            """, final_status, error_text, run_id)

            if run["kind"] == "review" and final_status == "success":
                await pool.execute("""
                    UPDATE review_comments SET addressed = true
                    WHERE ticket_id = $1 AND addressed = false
                """, ticket_id)
                await pool.execute(
                    "UPDATE tickets SET debounce_until = NULL, updated_at = now() WHERE id = $1",
                    ticket_id,
                )

            logger.info("Ticket sync: run %s finished as %s", run_id, final_status)

            if final_status == "failed":
                remaining = await pool.fetchval("""
                    SELECT COUNT(*) FROM runs
                    WHERE ticket_id = $1 AND status IN ('pending', 'launching', 'running')
                """, ticket_id)
                if remaining == 0:
                    await pool.execute(
                        "UPDATE tickets SET status = 'failed', updated_at = now() WHERE id = $1 AND status = 'active'",
                        ticket_id,
                    )
                    logger.info("Ticket sync: ticket %s marked as failed (no remaining runs)", ticket_id)

            try:
                delete_sandbox.sync(id=sandbox_id, client=sandbox_client)
                logger.info("Ticket sync: deleted sandbox %s", sandbox_id)
            except Exception:
                logger.warning("Ticket sync: failed to delete sandbox %s", sandbox_id)

        except Exception:
            logger.exception("Ticket sync: error checking run %s sandbox %s", run_id, sandbox_id)


async def _check_review_debounce():
    pool = await get_pool()

    cutoff = datetime.now(timezone.utc).timestamp() - config.REVIEW_DEBOUNCE_SECONDS
    tickets = await pool.fetch("""
        SELECT DISTINCT t.id, t.debounce_until
        FROM tickets t
        WHERE t.status = 'active'
          AND t.debounce_until IS NOT NULL
          AND t.debounce_until <= now()
          AND NOT EXISTS (
              SELECT 1 FROM runs r
              WHERE r.ticket_id = t.id AND r.status IN ('pending', 'launching', 'running')
          )
          AND EXISTS (
              SELECT 1 FROM review_comments rc
              WHERE rc.ticket_id = t.id AND rc.addressed = false
          )
    """)

    for ticket in tickets:
        ticket_id = str(ticket["id"])
        logger.info("Ticket sync: debounce fired for ticket %s, creating review run", ticket_id)

        await pool.execute("""
            INSERT INTO runs (ticket_id, kind, status) VALUES ($1, 'review', 'pending')
        """, ticket_id)

        await pool.execute(
            "UPDATE tickets SET debounce_until = NULL, updated_at = now() WHERE id = $1",
            ticket_id,
        )


async def ticket_sync_loop():
    logger.info("Ticket sync loop started (interval=%ds)", SYNC_INTERVAL_SECONDS)
    while True:
        try:
            await _launch_pending_runs()
            await _sync_active_runs()
            await _check_review_debounce()
        except Exception:
            logger.exception("Ticket sync loop iteration failed")
        await asyncio.sleep(SYNC_INTERVAL_SECONDS)
