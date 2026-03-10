# linear-autopilot — Claude Code Notes

This directory contains the **Linear Autopilot** application, which watches for Linear issues labeled `autopilot` and automatically creates GitHub PRs via Claude Code running in a Porter Sandbox.

## Architecture

```
linear-autopilot/
├── backend/       FastAPI + asyncpg (Python)
├── frontend/      SvelteKit + Tailwind CSS (TypeScript)
└── worker/        Claude Code CLI container (Dockerfile)
```

### Backend (`backend/`)

| File | Purpose |
|------|---------|
| `main.py` | FastAPI app setup, route mounting, lifespan (DB pool init) |
| `config.py` | All env vars via `config.*` singleton |
| `db.py` | `asyncpg` connection pool + migration runner |
| `routes/auth.py` | Google OAuth login, `/auth/me`, logout |
| `routes/integrations.py` | GitHub App install/callback, Linear OAuth flow, repo selection, disconnect endpoints |
| `routes/projects.py` | Project CRUD, settings update, job management |
| `routes/webhooks.py` | Linear webhook receiver (HMAC-SHA256 verified) |
| `services/github_app.py` | GitHub App JWT auth, installation token exchange, repo listing |
| `services/linear_oauth.py` | Linear OAuth token exchange, GraphQL queries (org, issue, comment) |
| `services/job_sync.py` | Background loop that launches Porter Sandboxes for pending jobs |
| `services/sandbox_runner.py` | Porter Sandbox API client wrapper |
| `middleware/auth.py` | JWT session cookie validation |
| `migrations/` | Sequential SQL migrations run at startup |

### Frontend (`frontend/src/`)

| Path | Purpose |
|------|---------|
| `lib/api.ts` | Typed `apiFetch` wrappers for all backend endpoints |
| `routes/+page.svelte` | Landing / login page |
| `routes/projects/+page.svelte` | Projects list |
| `routes/projects/[id]/+page.svelte` | Project dashboard (job list, status badges) |
| `routes/projects/[id]/settings/+page.svelte` | Integration settings (GitHub, Linear, autopilot label) |
| `routes/projects/[id]/jobs/[job_id]/+page.svelte` | Job detail + logs |

## Data Model

**`projects`** table — the central record:
- `github_installation_id` (BIGINT) — set after GitHub App install
- `github_repo` (TEXT) — user-selected repo (set via `PATCH /integrations/github/repo`)
- `linear_access_token`, `linear_refresh_token` — Linear OAuth tokens
- `linear_organization_id` — Linear workspace/org ID (set after OAuth callback)
- `autopilot_label` (TEXT, default `'autopilot'`) — label that triggers job creation

**`jobs`** table — one row per Claude Code run:
- `status`: `pending → launching → running → success | failed | cancelled`
- `sandbox_id` — Porter Sandbox container ID (used for logs/cancellation)

## Integration Flows

### GitHub App
1. User clicks "Install GitHub App" → redirected to GitHub with `state=project_id`
2. GitHub callback → `github_installation_id` stored on project
3. User loads repo list via `GET /integrations/github/repos`
4. User selects repo → `PATCH /integrations/github/repo` stores `github_repo`
5. To disconnect: `DELETE /integrations/github` (clears `installation_id` + `github_repo`)

### Linear OAuth
1. User clicks "Connect Linear" → secure cookie + redirect to Linear OAuth
2. Callback validates cookie, exchanges code for tokens, fetches org ID
3. Conflict check: same org cannot link to multiple projects
4. Tokens + org ID stored on project
5. To disconnect: `DELETE /integrations/linear` (clears tokens + org ID)

### Webhook → Job
```
Linear issue label added
  → POST /webhooks/linear (HMAC verified)
  → project looked up by linear_organization_id
  → autopilot_label check + github_installation_id check
  → Job record created (status=pending)
  → job_sync loop picks it up → launches Porter Sandbox
  → sandbox runs Claude Code CLI with issue context
  → Claude creates a PR, updates job with pr_url
```

## API Endpoints

### Integration endpoints (`/api/v1/projects/{id}/integrations/...`)
| Method | Path | Description |
|--------|------|-------------|
| GET | `.../github/install` | Redirect to GitHub App install |
| GET | `.../github/repos` | List repos accessible to installation |
| PATCH | `.../github/repo` | Save selected repo `{"repo": "owner/name"}` |
| DELETE | `.../github` | Disconnect GitHub (clear installation + repo) |
| GET | `.../linear/connect` | Start Linear OAuth flow |
| DELETE | `.../linear` | Disconnect Linear (clear tokens + org) |

## Key Configuration Variables

```
GITHUB_APP_SLUG         # e.g. "my-autopilot-app"
GITHUB_APP_ID           # numeric App ID
GITHUB_APP_PRIVATE_KEY  # PEM private key
LINEAR_CLIENT_ID
LINEAR_CLIENT_SECRET
LINEAR_REDIRECT_URL     # e.g. https://yourapp.com/integrations/linear/callback
LINEAR_WEBHOOK_SECRET   # HMAC secret configured in Linear settings
DATABASE_URL            # asyncpg DSN
SESSION_SECRET          # JWT signing key
```

## Development Notes

- The backend uses `asyncpg` directly (no ORM). Use parameterized queries with `$1`, `$2`, etc.
- Migrations run automatically at startup via `db.py:run_migrations()`.
- The frontend uses SvelteKit with Svelte 5 runes (`$state`, `$derived`).
- Auth is Google OAuth → JWT stored in a `session` httponly cookie.
- The `worker/` Dockerfile is a Claude Code CLI container that gets launched per-job by the Porter Sandbox API.
