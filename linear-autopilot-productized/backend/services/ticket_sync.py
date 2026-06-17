import asyncio
import logging

from config import config
from db import get_pool
from services.sandbox_runner import (
    create_sandbox_for_run, create_volume_for_ticket, delete_sandbox,
    generate_callback_token, get_sandbox_logs, get_sandbox_status,
    parse_sandbox_exit_code, parse_sandbox_phase,
)
from services.linear_oauth import post_issue_comment_with_refresh

logger = logging.getLogger(__name__)

SYNC_INTERVAL_SECONDS = 15


async def _launch_pending_runs():
    pool = await get_pool()

    runs = await pool.fetch("""
        SELECT r.id, r.ticket_id, r.kind,
               t.linear_issue_id, t.linear_issue_identifier, t.linear_issue_title,
               t.linear_issue_description, t.linear_issue_url, t.volume_id, t.pr_url, t.project_id,
               p.github_installation_id, p.linear_access_token, p.linear_refresh_token,
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
                volume_id = await create_volume_for_ticket(str(ticket_id))
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
                ticket_id=str(ticket_id),
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

            if run["linear_access_token"]:
                try:
                    ticket_ref = run["linear_issue_identifier"] or ticket_id
                    run_url = f"{config.BASE_URL}/projects/{run['project_id']}/tickets/{ticket_ref}?run={run_id}"
                    if run["kind"] == "initial":
                        msg = f"**Autopilot is working on this issue.**\n\n[View progress]({run_url})"
                    else:
                        msg = f"**Autopilot is addressing review feedback.**\n\n[View progress]({run_url})"
                    await post_issue_comment_with_refresh(
                        str(run["project_id"]),
                        run["linear_access_token"],
                        run["linear_refresh_token"],
                        run["linear_issue_id"],
                        msg,
                    )
                    logger.info("Ticket sync: posted launch comment for run %s to issue %s", run_id, run["linear_issue_id"])
                except Exception:
                    logger.warning("Ticket sync: failed to post launch comment for run %s", run_id, exc_info=True)
            else:
                logger.warning("Ticket sync: no linear_access_token for run %s, skipping launch comment", run_id)

        except Exception as e:
            logger.exception("Ticket sync: failed to launch run %s", run_id)
            await pool.execute(
                "UPDATE runs SET status = 'failed', error = $1, finished_at = now() WHERE id = $2",
                str(e), run_id,
            )

            if run["linear_access_token"]:
                try:
                    ticket_ref = run["linear_issue_identifier"] or ticket_id
                    run_url = f"{config.BASE_URL}/projects/{run['project_id']}/tickets/{ticket_ref}?run={run_id}"
                    msg = f"**Autopilot failed to start.**\n\n{str(e)}\n\n[View details]({run_url})"
                    await post_issue_comment_with_refresh(
                        str(run["project_id"]),
                        run["linear_access_token"],
                        run["linear_refresh_token"],
                        run["linear_issue_id"],
                        msg,
                    )
                except Exception:
                    logger.warning("Ticket sync: failed to post launch failure comment for run %s", run_id, exc_info=True)

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
            status_response = await get_sandbox_status(sandbox_id)

            if status_response is None:
                logger.warning("Ticket sync: run=%s sandbox=%s gone (not found)", run_id, sandbox_id)
                has_summary = await pool.fetchval(
                    "SELECT summary IS NOT NULL FROM runs WHERE id = $1", run_id
                )
                phase = "gone"
                exit_code = None
                terminal = True
                final_status = "success" if has_summary else "failed"
            else:
                phase = parse_sandbox_phase(status_response)
                exit_code = parse_sandbox_exit_code(status_response)

                terminal = False
                final_status = None

                if exit_code is not None:
                    terminal = True
                    final_status = "success" if exit_code == 0 else "failed"
                elif phase in ("succeeded", "failed", "terminated"):
                    terminal = True
                    final_status = "success" if phase == "succeeded" else "failed"

            logger.info("Ticket sync: run=%s sandbox=%s phase=%s exit_code=%r terminal=%s", run_id, sandbox_id, phase, exit_code, terminal)

            if not terminal:
                continue

            error_text = None
            if final_status == "failed":
                try:
                    log_lines = await get_sandbox_logs(sandbox_id)
                    if log_lines:
                        error_text = "\n".join(log_lines)[-2000:]
                except Exception:
                    error_text = f"Sandbox exited: phase={phase} exit_code={exit_code}"

            await pool.execute("""
                UPDATE runs SET status = $1, error = $2, finished_at = now()
                WHERE id = $3 AND status = 'running'
            """, final_status, error_text, run_id)

            logger.info("Ticket sync: run %s finished as %s", run_id, final_status)

            try:
                ticket_info = await pool.fetchrow("""
                    SELECT t.linear_issue_id, t.linear_issue_identifier, t.project_id, t.pr_url,
                           r.summary, r.kind, p.linear_access_token, p.linear_refresh_token
                    FROM tickets t
                    JOIN runs r ON r.ticket_id = t.id
                    JOIN projects p ON p.id = t.project_id
                    WHERE r.id = $1
                """, run_id)
                if not ticket_info:
                    logger.warning("Ticket sync: no ticket_info found for run %s, skipping completion comment", run_id)
                elif not ticket_info["linear_access_token"]:
                    logger.warning("Ticket sync: no linear_access_token for run %s, skipping completion comment", run_id)
                elif ticket_info and ticket_info["linear_access_token"]:
                    ticket_ref = ticket_info["linear_issue_identifier"] or ticket_id
                    run_url = f"{config.BASE_URL}/projects/{ticket_info['project_id']}/tickets/{ticket_ref}?run={run_id}"

                    if final_status == "success":
                        summary = ticket_info["summary"] or "Run completed successfully."
                        kind_label = "initial run" if ticket_info["kind"] == "initial" else "review run"
                        msg = f"**Autopilot {kind_label} completed successfully.**\n\n{summary}"
                        if ticket_info["pr_url"]:
                            msg += f"\n\n[View PR]({ticket_info['pr_url']}) · [View run]({run_url})"
                        else:
                            msg += f"\n\n[View run]({run_url})"
                        await post_issue_comment_with_refresh(
                            str(ticket_info["project_id"]),
                            ticket_info["linear_access_token"],
                            ticket_info["linear_refresh_token"],
                            ticket_info["linear_issue_id"],
                            msg,
                        )
                        logger.info("Ticket sync: posted success comment for run %s to issue %s", run_id, ticket_info["linear_issue_id"])
                    elif final_status == "failed":
                        kind_label = "initial run" if ticket_info["kind"] == "initial" else "review run"
                        msg = f"**Autopilot {kind_label} failed.**"
                        if error_text:
                            truncated = error_text[-500:]
                            msg += f"\n\n```\n{truncated}\n```"
                        msg += f"\n\n[View run]({run_url})"
                        await post_issue_comment_with_refresh(
                            str(ticket_info["project_id"]),
                            ticket_info["linear_access_token"],
                            ticket_info["linear_refresh_token"],
                            ticket_info["linear_issue_id"],
                            msg,
                        )
                        logger.info("Ticket sync: posted failure comment for run %s to issue %s", run_id, ticket_info["linear_issue_id"])
            except Exception:
                logger.warning("Ticket sync: failed to post completion comment for run %s", run_id, exc_info=True)

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
                await delete_sandbox(sandbox_id)
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
