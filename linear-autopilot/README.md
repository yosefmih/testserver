# Linear Autopilot

A web app that automatically creates GitHub PRs from Linear issues using Claude Code. Tag a Linear issue with a label, and Claude Code will read the issue, fix the code, and open a PR. When reviewers leave comments on the PR, the agent automatically addresses them.

## How It Works

1. You sign in with Google and create a project
2. You install a GitHub App on your repos and connect your Linear workspace via OAuth
3. You set a trigger label (default: `autopilot`)
4. When a Linear issue gets the trigger label, a webhook fires to this server
5. The server creates a **ticket** for the issue and launches a Porter Sandbox running Claude Code CLI with GitHub and Linear MCP servers
6. Claude Code reads the issue, clones the repo, fixes the code, pushes a branch, creates a PR, and reports metadata back to the server via a callback API
7. When PR review comments are posted, the GitHub webhook stores them and triggers a **review run** after a debounce window (default: 10 minutes)
8. The review run reuses the same persistent EFS volume, so the agent has full context from previous runs

## Architecture

```
Linear (webhook) ──► FastAPI server ──► Porter Sandbox (initial run)
                          │                    │
GitHub (webhook) ──►      │              Container:
                          │              - Claude Code CLI
                          │              - GitHub MCP server
                          │              - Linear MCP server
                          │              - /workspace (EFS volume)
                          │                    │
                          │              Reads issue → fixes code → creates PR
                          │              Calls back with PR metadata
                          │                    │
                          ├── stores review comments ◄── PR review comments
                          │
                          ├── debounce timer fires ──► Porter Sandbox (review run)
                          │                                  │
                          │                            Same /workspace volume
                          │                            Addresses review comments
                          │
                          └── PR merged/closed ──► ticket marked merged/closed
```

### Data Model

- **Project** — one per user, links a GitHub App installation and Linear organization
- **Ticket** — one per Linear issue. Tracks the PR URL, EFS volume, and lifecycle status (active/merged/closed)
- **Run** — one per sandbox execution. Kind is `initial` (first fix) or `review` (addressing PR comments). Each run gets a one-time callback token for reporting metadata
- **Review Comment** — stored from GitHub webhooks, batched by the debounce timer into review runs

### Key Patterns

- **Organization-based routing**: Linear webhooks are matched to projects via `organizationId` in the payload. One Linear org per project (enforced by unique constraint)
- **actor=app OAuth**: Linear OAuth uses `actor=app` so agent actions appear as the app, not the user
- **Callback API**: Sandboxes report PR metadata by calling `POST /api/internal/runs/{id}/metadata` with a one-time token (no log parsing needed)
- **Persistent volumes**: Each ticket gets an EFS volume mounted at `/workspace`. The agent clones into `/workspace/repo` and context is preserved across runs
- **Review debounce**: PR review comments reset a 10-minute timer. When it fires, all unaddressed comments are batched into a single review run
- **Volume locking**: Only one run per ticket at a time (enforced in the sync loop)

## Prerequisites

- Python 3.13+
- Node.js 22+
- PostgreSQL
- A Google OAuth application
- A GitHub App (with webhook enabled for PR review comments)
- A Linear OAuth application (with webhook configured for Issue events)
- An Anthropic API key
- Access to Porter Sandbox

## Setup

### 1. Create a Google OAuth Application

1. Go to [Google Cloud Console](https://console.cloud.google.com/apis/credentials)
2. Create a new OAuth 2.0 Client ID (Web application)
3. Add authorized redirect URI: `http://localhost:8080/auth/google/callback`
4. Note the Client ID and Client Secret

### 2. Create a GitHub App

1. Go to [GitHub Developer Settings](https://github.com/settings/apps/new)
2. Set the following:
   - **Homepage URL**: your app's URL
   - **Callback URL**: `http://localhost:8080/integrations/github/callback`
   - **Webhook URL**: `https://your-production-url/webhooks/github`
   - **Webhook Active**: checked
   - **Webhook Secret**: generate a random string
3. Under **Permissions**, set:
   - **Repository permissions**:
     - Contents: Read & write
     - Pull requests: Read & write
4. Under **Subscribe to events**, check:
   - Pull request review comment
   - Pull request
5. Click "Create GitHub App"
6. Note the **App ID**, **App slug**, and **Webhook secret**
7. Generate a **Private Key** (PEM file)

### 3. Create a Linear OAuth Application

1. Go to [Linear Developer Settings](https://linear.app/settings/api/applications/new)
2. Set:
   - **Redirect URI**: `http://localhost:8080/integrations/linear/callback`
   - **Webhook URL**: `https://your-production-url/webhooks/linear`
   - **Webhook resource types**: `Issue`, `IssueLabel`
3. Note the **Client ID**, **Client Secret**, and **Webhook signing secret**

### 4. Set Up PostgreSQL

```bash
createdb linear_autopilot
```

The app runs migrations automatically on startup.

### 5. Configure Environment Variables

```bash
cd testserver/linear-autopilot
cp .env.example backend/.env
```

Edit `backend/.env` with your values. See `.env.example` for all available variables.

For `GITHUB_APP_PRIVATE_KEY`, either paste the PEM contents with `\n` for newlines, or set it to the file path and adjust `config.py` to read from file.

### 6. Build the Worker Image

```bash
cd worker
docker build -t linear-autopilot-worker .
```

### 7. Install Backend Dependencies

```bash
cd backend
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
pip install -e ../../experimental/porter-sdk
```

### 8. Install Frontend Dependencies

```bash
cd frontend
npm install
```

## Running Locally

### Development (backend + frontend separately)

Terminal 1 — backend:

```bash
cd backend
source venv/bin/activate
uvicorn main:app --reload --port 8080
```

Terminal 2 — frontend (with hot reload):

```bash
cd frontend
npm run dev -- --port 5173
```

In dev mode, proxy API requests from the Vite dev server to the backend. Add to `frontend/vite.config.ts`:

```ts
server: {
  proxy: {
    '/api': 'http://localhost:8080',
    '/auth': 'http://localhost:8080',
    '/webhooks': 'http://localhost:8080',
  }
}
```

### Production (single server)

Build the frontend and run the backend with embedded static assets:

```bash
cd frontend && npm run build
cp -r build ../backend/static
cd ../backend
uvicorn main:app --host 0.0.0.0 --port 8080
```

Or build the Docker image:

```bash
docker build -t linear-autopilot .
docker run -p 8080:8080 --env-file backend/.env linear-autopilot
```

### Exposing Webhooks Locally

Both Linear and GitHub need to reach your server for webhooks. Use ngrok or cloudflared:

```bash
ngrok http 8080
```

Then update:
- **Linear app settings** → Webhook URL: `https://abc123.ngrok.io/webhooks/linear`
- **GitHub App settings** → Webhook URL: `https://abc123.ngrok.io/webhooks/github`

## Usage

1. Open `http://localhost:8080` and sign in with Google
2. Create a project
3. Go to project **Settings**:
   - Click **Install GitHub App** → install on the repos you want Claude to fix
   - Click **Connect Linear** → authorize with your Linear workspace
   - Set the trigger label (default: `autopilot`)
4. Save settings
5. In Linear, create or update an issue and add the `autopilot` label
6. The server creates a ticket, launches a sandbox, and Claude Code gets to work
7. Check the project dashboard for ticket status, PR links, and run history
8. Review the PR — any review comments will automatically trigger follow-up runs

## Project Structure

```
linear-autopilot/
  backend/
    main.py              # FastAPI app, lifespan, route mounting, static file serving
    config.py            # Environment variable configuration
    db.py                # asyncpg pool, migration runner
    migrations/          # SQL migration files (001-004)
    routes/
      auth.py            # Google OAuth login/callback/logout, /auth/me
      projects.py        # Project CRUD, ticket/run endpoints, run logs
      integrations.py    # GitHub App install + Linear OAuth flows
      webhooks.py        # Linear webhook (creates tickets) + GitHub webhook (PR comments, PR close)
      internal.py        # Callback API for sandbox metadata reporting
    services/
      github_app.py      # GitHub App JWT signing, installation token exchange
      linear_oauth.py    # Linear OAuth token exchange, GraphQL client (org, issues, comments)
      sandbox_runner.py  # Sandbox creation with EFS volumes, callback tokens, prompt building
      ticket_sync.py     # Async loop: launches runs, syncs sandbox status, review debounce
    middleware/
      auth.py            # JWT session cookie verification
  worker/
    Dockerfile           # Claude Code CLI + gh + MCP servers
    entrypoint.sh        # Authenticates gh, renders MCP config, runs claude
    mcp_config.template.json  # GitHub + Linear MCP server definitions
  frontend/
    src/
      lib/api.ts         # Typed API client with Ticket/Run types
      routes/            # SvelteKit pages (login, projects, tickets, settings)
  Dockerfile             # Multi-stage: builds frontend, embeds into backend
  porter.yaml            # Porter deployment config
  .env.example           # All required environment variables
```

## Database Tables

- **users** — Google OAuth profiles (email, google_id, avatar)
- **projects** — user's projects with GitHub/Linear integration state, organization ID
- **tickets** — one per Linear issue (PR metadata, EFS volume ID, status, debounce timer)
- **runs** — sandbox executions per ticket (kind: initial/review, callback token, status)
- **review_comments** — PR review comments from GitHub webhooks (batched into review runs)

## API Endpoints

| Method | Path | Auth | Purpose |
|--------|------|------|---------|
| GET | `/health` | No | Health check |
| GET | `/auth/google/login` | No | Start Google OAuth |
| GET | `/auth/google/callback` | No | Google OAuth callback |
| POST | `/auth/logout` | Yes | Clear session |
| GET | `/auth/me` | Yes | Current user info |
| GET | `/api/v1/projects` | Yes | List projects |
| POST | `/api/v1/projects` | Yes | Create project |
| GET | `/api/v1/projects/:id` | Yes | Get project + tickets |
| PATCH | `/api/v1/projects/:id/settings` | Yes | Update label |
| DELETE | `/api/v1/projects/:id` | Yes | Delete project |
| GET | `/api/v1/projects/:id/tickets/:tid` | Yes | Get ticket + runs |
| DELETE | `/api/v1/projects/:id/tickets/:tid` | Yes | Close ticket, cancel runs |
| GET | `/api/v1/projects/:id/tickets/:tid/runs/:rid/logs` | Yes | Get run sandbox logs |
| GET | `/api/v1/projects/:id/integrations/github/install` | Yes | Redirect to GitHub App install |
| GET | `/integrations/github/callback` | Yes | GitHub App install callback |
| GET | `/api/v1/projects/:id/integrations/github/repos` | Yes | List repos from GitHub App |
| GET | `/api/v1/projects/:id/integrations/linear/connect` | Yes | Start Linear OAuth |
| GET | `/integrations/linear/callback` | Yes | Linear OAuth callback |
| POST | `/webhooks/linear` | HMAC | Linear webhook (creates tickets by organizationId) |
| POST | `/webhooks/github` | HMAC | GitHub webhook (PR comments, PR close events) |
| POST | `/api/internal/runs/:rid/metadata` | Token | Sandbox callback for PR metadata |
