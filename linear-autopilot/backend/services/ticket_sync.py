import asyncio
import logging

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
               p.github_installation_id, p.linear_access_token,
               p.anthropic_api_key, p.custom_tools, p.system_prompt
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
        run_id = run["id"]
        ticket_id = run["ticket_id"]

        active_run = await pool.fetchrow("""
            SELECT id FROM runs
            WHERE ticket_id = $1 AND status IN ('launching', 'running') AND id != $2
        """, ticket_id, run_id)
        if active_run:
            logger.info("Ticket sync: skipping run %s, ticket %s has active run", run_id, ticket_id)
            continue

        try:
            if not run["anthropic_api_key"]:
                raise Exception("No Claude/Anthropic API key configured for this project. Connect Claude in project settings.")

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
                run_id=str(run_id),
                callback_token=callback_token,
                kind=run["kind"],
                volume_id=volume_id,
                issue_id=run["linear_issue_id"],
                issue_title=run["linear_issue_title"],
                issue_description=run["linear_issue_description"] or "",
                issue_url=run["linear_issue_url"] or "",
                github_installation_id=run["github_installation_id"],
                linear_access_token=run["linear_access_token"],
                anthropic_api_key=run["anthropic_api_key"],
                custom_tools=run["custom_tools"],
                system_prompt=run["system_prompt"],
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
        run_id = run["id"]
        sandbox_id = run["sandbox_id"]
        ticket_id = run["ticket_id"]

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

            logger.info("Ticket sync: run %s finished as %s", run_id, final_status)

            try:
                ticket_info = await pool.fetchrow("""
                    SELECT t.linear_issue_id, r.summary, p.linear_access_token
                    FROM tickets t
                    JOIN runs r ON r.ticket_id = t.id
                    JOIN projects p ON p.id = t.project_id
                    WHERE r.id = $1
                """, run_id)
                if ticket_info and ticket_info["linear_access_token"]:
                    if final_status == "failed" and not ticket_info["summary"]:
                        fail_msg = "**Autopilot run failed.**"
                        if error_text:
                            truncated = error_text[-500:]
                            fail_msg += f"\n```\n{truncated}\n```"
                        await post_issue_comment(
                            ticket_info["linear_access_token"],
                            ticket_info["linear_issue_id"],
                            fail_msg,
                        )
            except Exception:
                logger.warning("Ticket sync: failed to post completion comment for run %s", run_id)

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


async def ticket_sync_loop():
    logger.info("Ticket sync loop started (interval=%ds)", SYNC_INTERVAL_SECONDS)
    while True:
        try:
            await _launch_pending_runs()
            await _sync_active_runs()
        except Exception:
            logger.exception("Ticket sync loop iteration failed")
        await asyncio.sleep(SYNC_INTERVAL_SECONDS)
