# CLAUDE.md — linear-autopilot

This file provides guidance to Claude Code when working in the `linear-autopilot` directory.

## App Overview

**linear-autopilot** is an AI-powered automation tool that listens for Linear issues, runs Claude Code in a sandbox to produce a fix, and opens a GitHub PR automatically.

The app consists of:
- **Backend** (`backend/`) — FastAPI (Python) REST API
- **Frontend** (`frontend/`) — SvelteKit (TypeScript) UI
- **Worker** (`worker/`) — Celery background worker that processes tickets

## Key Architecture

### Backend

| File | Purpose |
|------|---------|
| `backend/main.py` | FastAPI app factory, mounts routers |
| `backend/db.py` | asyncpg connection pool helper (`get_pool()`) |
| `backend/config.py` | Env-var config (Pydantic Settings) |
| `backend/routes/auth.py` | Google OAuth login/logout |
| `backend/routes/projects.py` | CRUD for projects and tickets |
| `backend/routes/integrations.py` | GitHub App install + Linear OAuth connect/disconnect |
| `backend/routes/webhooks.py` | Linear webhook receiver |
| `backend/routes/internal.py` | Internal endpoints (e.g. run metadata reporting) |
| `backend/services/github_app.py` | GitHub App JWT auth + installation token |
| `backend/services/linear_oauth.py` | Linear OAuth token exchange + org lookup |
| `backend/services/sandbox_runner.py` | Porter sandbox API client (starts/stops Claude Code runs) |
| `backend/services/ticket_sync.py` | Syncs Linear issue state into the DB |

### Frontend

SvelteKit app with file-based routing under `frontend/src/routes/`:

| Route | Purpose |
|-------|---------|
| `/` | Landing / login page |
| `/projects` | List all projects |
| `/projects/[id]` | Project detail with ticket list |
| `/projects/[id]/settings` | Project settings: integrations, autopilot label, delete |

`frontend/src/lib/api.ts` — typed wrapper over `fetch` for all API calls.

### Worker

Celery worker that picks up `process_ticket` tasks, spins up a Porter sandbox running Claude Code, and polls for completion.

## Database Schema

PostgreSQL. Key tables:

- `users` — Google OAuth users
- `projects` — one per user workspace; stores integration credentials
- `tickets` — one per Linear issue processed
- `runs` — one per Claude Code execution attempt for a ticket

Important `projects` columns:
- `github_installation_id` — GitHub App installation (NULL = not connected)
- `linear_access_token`, `linear_refresh_token`, `linear_organization_id` — Linear OAuth (all NULL = not connected)
- `autopilot_label` — the Linear label that triggers runs (default: `"autopilot"`)

Migrations live in `backend/migrations/` and are numbered sequentially (`001_initial.sql`, …).

## Integrations

### GitHub

- Connection: user visits `/api/v1/projects/{id}/integrations/github/install` → GitHub App install flow → callback saves `github_installation_id`.
- Update: same install URL allows changing/updating the installation.
- Disconnect: `DELETE /api/v1/projects/{id}/integrations/github` clears `github_installation_id`.

### Linear

- Connection: user visits `/api/v1/projects/{id}/integrations/linear/connect` → Linear OAuth → callback exchanges code for tokens, saves `linear_access_token`, `linear_refresh_token`, `linear_organization_id`.
- Reconnect: same connect URL (uses `prompt=consent`).
- Disconnect: `DELETE /api/v1/projects/{id}/integrations/linear` clears all Linear token fields.

## Ticket Lifecycle

Ticket statuses and their meanings:

| Status | Trigger |
|--------|---------|
| `active` | Linear webhook fires, issue labelled with autopilot label |
| `merged` | GitHub webhook: PR was merged |
| `closed` | GitHub webhook: PR was closed without merging |
| `cancelled` | User manually cancels via UI — deletes sandboxes + volume |
| `failed` | All runs failed with no pending runs remaining |

When a ticket is cancelled (`DELETE /api/v1/projects/{id}/tickets/{tid}`):
1. All active runs (pending/launching/running) have their sandboxes deleted via Porter API.
2. All active runs are set to `cancelled`.
3. The ticket's EFS volume is deleted via Porter API (best-effort; errors are logged, not raised).
4. Ticket status is set to `cancelled`.

## Porter Sandbox API Client

Installed from a private wheel: `porter-sandbox-api-client @ https://...`. Key modules:

- `porter_sandbox_api_client.api.sandboxes` — `create_sandbox`, `get_sandbox`, `get_sandbox_logs`, `delete_sandbox`
- `porter_sandbox_api_client.api.volumes` — `create_volume`, `get_volume`, `delete_volume`

The `sandbox_client` is a module-level singleton in `services/sandbox_runner.py`.

## Key API Endpoints

| Method | Path | Purpose |
|--------|------|---------|
| `DELETE` | `/api/v1/projects/{id}/tickets/{tid}` | Cancel ticket, delete sandboxes + volume |
| `POST` | `/api/v1/projects/{id}/tickets/{tid}/trigger-review` | Queue a manual review run |
| `GET` | `/api/v1/projects/{id}/tickets/{tid}` | Ticket detail + runs |
| `GET` | `/api/v1/projects/{id}/tickets/{tid}/runs/{rid}/logs` | Stream sandbox logs |
| `POST` | `/api/internal/runs/{rid}/metadata` | Sandbox callback to report PR metadata |

## Frontend Notes

The ticket detail page (`frontend/src/routes/projects/[id]/tickets/[ticketId]/+page.svelte`) has:
- A **"Cancel ticket"** button (red, visible only for `active` tickets) that calls `closeTicket()` from `api.ts`.
- A **"Run review"** button (visible for active tickets with a PR) to manually queue a review run.
- Auto-refresh every 5s while any run is in an active state.

`frontend/src/lib/api.ts` contains `closeTicket(projectId, ticketId)` which calls `DELETE /api/v1/projects/{id}/tickets/{tid}`.

## Development Notes

- **Major branch is `dev`** — not `main`. Always branch from and PR against `dev`.
- The frontend dev server is Vite; run `npm run dev` inside `frontend/`.
- The backend is uvicorn/FastAPI; run with `uvicorn main:app --reload` inside `backend/`.
- Auth is session-cookie based (Google OAuth). Middleware in `backend/middleware/auth.py`.
- The frontend makes all API calls through `/api/v1/...` — proxied by Vite in dev and served directly in production.
