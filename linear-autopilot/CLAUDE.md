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
- Update: the same install route now checks whether the project already has a `github_installation_id`. If it does, it redirects to `https://github.com/apps/{slug}/installations/{id}/permissions/update` so the user updates the *existing* installation (change repo access etc.) rather than creating a duplicate one. If not connected, it redirects to `/installations/new` as before.
- GitHub callback (`GET /integrations/github/callback`): `state` is now **optional**. When GitHub omits `state` (e.g. updates triggered from GitHub's own settings UI), the callback falls back to looking up the project by `installation_id`. `setup_action` is accepted but ignored.
- Disconnect: `DELETE /api/v1/projects/{id}/integrations/github` clears `github_installation_id`.
- The project API (`GET /api/v1/projects/{id}`) now returns `github_installation_id` so the frontend can display it and construct management links if needed.

### Linear

- Connection: user visits `/api/v1/projects/{id}/integrations/linear/connect` → Linear OAuth (with `prompt=consent` to force re-auth) → callback exchanges code for tokens, saves `linear_access_token`, `linear_refresh_token`, `linear_organization_id`.
- Update / Reconnect: same connect URL. The callback does an `UPDATE` (not `INSERT`) so revisiting the connect URL is idempotent — it simply refreshes the stored tokens. Connecting to a different org overwrites the old credentials.
- Conflict handling: if the target org is already linked to *another* project, the callback now redirects back to the settings page with a `?error=...` query param instead of returning a raw JSON 409, so the user sees a clear error message in the UI.
- Disconnect: `DELETE /api/v1/projects/{id}/integrations/linear` clears all Linear token fields.
- The project API returns `linear_organization_id` so the settings UI can display which org is currently connected.

### Frontend (`settings/+page.svelte`)

- On mount, reads any `?error=` query param left by an OAuth callback redirect and displays it in the message area (then removes it from the URL).
- Message colour is now context-aware: green for "Settings saved", red for error messages.
- GitHub section shows the installation ID when connected.
- Linear section shows the connected organization ID when connected.

## Development Notes

- **Major branch is `dev`** — not `main`. Always branch from and PR against `dev`.
- The frontend dev server is Vite; run `npm run dev` inside `frontend/`.
- The backend is uvicorn/FastAPI; run with `uvicorn main:app --reload` inside `backend/`.
- Auth is session-cookie based (Google OAuth). Middleware in `backend/middleware/auth.py`.
- The frontend makes all API calls through `/api/v1/...` — proxied by Vite in dev and served directly in production.
