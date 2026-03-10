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

## Development Notes

- **Major branch is `dev`** — not `main`. Always branch from and PR against `dev`.
- The frontend dev server is Vite; run `npm run dev` inside `frontend/`.
- The backend is uvicorn/FastAPI; run with `uvicorn main:app --reload` inside `backend/`.
- Auth is session-cookie based (Google OAuth). Middleware in `backend/middleware/auth.py`.
- The frontend makes all API calls through `/api/v1/...` — proxied by Vite in dev and served directly in production.
