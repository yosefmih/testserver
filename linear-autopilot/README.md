# Linear Autopilot

A web app that automatically creates GitHub PRs from Linear issues using Claude Code. Tag a Linear issue with a label, and Claude Code will read the issue, fix the code, and open a PR.

## How It Works

1. You sign in with Google and create a project
2. You install a GitHub App on your repo and connect your Linear workspace via OAuth
3. You pick a target repo, a Linear team, and a trigger label (default: `autopilot`)
4. When a Linear issue in that team gets the trigger label, a webhook fires to this server
5. The server launches a Porter Sandbox container running Claude Code CLI with GitHub and Linear MCP servers
6. Claude Code reads the issue, clones the repo, fixes the code, pushes a branch, creates a PR, and comments back on the Linear issue with the PR link

## Architecture

```
Linear (webhook) → FastAPI server → Porter Sandbox
                                        │
                                    Container:
                                    - Claude Code CLI
                                    - GitHub MCP server
                                    - Linear MCP server
                                        │
                                    Reads issue → fixes code → creates PR → comments on Linear
```

The server is a single Docker image: SvelteKit frontend compiled to static assets and served by the FastAPI backend. The Claude Code work runs in isolated Porter Sandbox containers, one per issue.

## Prerequisites

- Python 3.13+
- Node.js 22+
- PostgreSQL
- A Google OAuth application
- A GitHub App
- A Linear OAuth application
- An Anthropic API key
- Access to Porter Sandbox (for production; local testing can use the sandbox SDK)

## Setup

### 1. Create a Google OAuth Application

1. Go to [Google Cloud Console](https://console.cloud.google.com/apis/credentials)
2. Create a new OAuth 2.0 Client ID (Web application)
3. Add authorized redirect URI: `http://localhost:8080/auth/google/callback` (or your production URL)
4. Note the Client ID and Client Secret

### 2. Create a GitHub App

1. Go to [GitHub Developer Settings](https://github.com/settings/apps/new)
2. Set the following:
   - **Homepage URL**: your app's URL
   - **Callback URL**: `http://localhost:8080/integrations/github/callback` (or production URL)
   - **Setup URL** (optional): same as callback URL
   - **Webhook**: uncheck "Active" (we don't need GitHub webhooks, only Linear webhooks)
3. Under **Permissions**, set:
   - **Repository permissions**:
     - Contents: Read & write
     - Pull requests: Read & write
4. Click "Create GitHub App"
5. Note the **App ID** and **App slug** (from the URL)
6. Generate a **Private Key** (PEM file) — download and save it

### 3. Create a Linear OAuth Application

1. Go to [Linear Developer Settings](https://linear.app/settings/api/applications/new)
2. Set:
   - **Redirect URI**: `http://localhost:8080/integrations/linear/callback` (or production URL)
   - **Webhook URL**: `https://your-production-url/webhooks/linear`
   - **Webhook resource types**: `Issue`
3. Note the **Client ID**, **Client Secret**, and **Webhook signing secret**
4. The webhook is configured here in app settings (not created programmatically), so it uses `read,write` OAuth scope instead of `admin`

### 4. Set Up PostgreSQL

Create a database:

```bash
createdb linear_autopilot
```

The app runs migrations automatically on startup.

### 5. Configure Environment Variables

```bash
cd testserver/linear-autopilot
cp .env.example backend/.env
```

Edit `backend/.env` with your values:

```
DB_URL=postgresql://user:password@localhost:5432/linear_autopilot
BASE_URL=http://localhost:8080

GOOGLE_CLIENT_ID=your-google-client-id
GOOGLE_CLIENT_SECRET=your-google-client-secret
GOOGLE_REDIRECT_URL=http://localhost:8080/auth/google/callback

JWT_SECRET=generate-a-random-string-here

GITHUB_APP_ID=123456
GITHUB_APP_PRIVATE_KEY=-----BEGIN RSA PRIVATE KEY-----\n...\n-----END RSA PRIVATE KEY-----
GITHUB_APP_SLUG=your-app-slug

LINEAR_CLIENT_ID=your-linear-client-id
LINEAR_CLIENT_SECRET=your-linear-client-secret
LINEAR_REDIRECT_URL=http://localhost:8080/integrations/linear/callback
LINEAR_WEBHOOK_SECRET=your-webhook-signing-secret

ANTHROPIC_API_KEY=sk-ant-...
WORKER_IMAGE=linear-autopilot-worker:latest
```

For `GITHUB_APP_PRIVATE_KEY`, either paste the PEM contents with `\n` for newlines, or set it to the file path and adjust `config.py` to read from file.

### 6. Build the Worker Image

The worker image contains Claude Code CLI, GitHub CLI, and the MCP servers:

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
```

You also need `porter_sdk` from the local SDK:

```bash
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

In dev mode, you'll need to proxy API requests from the Vite dev server to the backend. Add to `frontend/vite.config.ts`:

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

Linear needs to reach your server for webhooks. Use ngrok or cloudflared:

```bash
ngrok http 8080
```

Then update the **Webhook URL** in your Linear OAuth app settings to point to your tunnel URL (e.g., `https://abc123.ngrok.io/webhooks/linear`). The webhook is configured in Linear app settings, not created programmatically. Set the signing secret from Linear as `LINEAR_WEBHOOK_SECRET` in your `.env`.

## Usage

1. Open `http://localhost:8080` and sign in with Google
2. Create a project
3. Go to project **Settings**:
   - Click **Install GitHub App** → install on the repo you want Claude to fix
   - Select the target repository from the dropdown
   - Click **Connect Linear** → authorize with your Linear workspace
   - Select the Linear team to watch
   - Set the trigger label (default: `autopilot`)
4. Save settings
5. In Linear, create or update an issue and add the `autopilot` label
6. The server receives the webhook, launches a sandbox, and Claude Code gets to work
7. Check the project dashboard for job status and PR links

## Project Structure

```
linear-autopilot/
  backend/
    main.py              # FastAPI app, lifespan, route mounting, static file serving
    config.py            # Environment variable configuration
    db.py                # asyncpg pool, migration runner
    migrations/          # SQL migration files
    routes/
      auth.py            # Google OAuth login/callback/logout, /auth/me
      projects.py        # Project CRUD and settings
      integrations.py    # GitHub App install + Linear OAuth flows
      webhooks.py        # Single Linear webhook endpoint, HMAC verification, team-based project matching
    services/
      github_app.py      # GitHub App JWT signing, installation token exchange
      linear_oauth.py    # Linear OAuth token exchange, GraphQL client (teams, comments)
      sandbox_runner.py  # Porter SDK sandbox creation and monitoring
    middleware/
      auth.py            # JWT session cookie verification
  worker/
    Dockerfile           # Claude Code CLI + gh + MCP servers
    entrypoint.sh        # Authenticates gh, renders MCP config, runs claude
    mcp_config.template.json  # GitHub + Linear MCP server definitions
  frontend/
    src/
      lib/api.ts         # Typed API client with auth redirect
      routes/            # SvelteKit pages (login, projects, dashboard, settings)
  Dockerfile             # Multi-stage: builds frontend, embeds into backend
  porter.yaml            # Porter deployment config
  .env.example           # All required environment variables
```

## Database Tables

- **users** — Google OAuth profiles (email, google_id, avatar)
- **projects** — user's projects with GitHub/Linear integration state
- **jobs** — autopilot job history (one per triggered issue, tracks status/PR URL/errors)

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
| GET | `/api/v1/projects/:id` | Yes | Get project + jobs |
| PATCH | `/api/v1/projects/:id/settings` | Yes | Update repo/label |
| GET | `/api/v1/projects/:id/integrations/github/install` | Yes | Redirect to GitHub App install |
| GET | `/integrations/github/callback` | Yes | GitHub App install callback |
| GET | `/api/v1/projects/:id/integrations/github/repos` | Yes | List repos from GitHub App |
| GET | `/api/v1/projects/:id/integrations/linear/connect` | Yes | Start Linear OAuth |
| GET | `/integrations/linear/callback` | Yes | Linear OAuth callback |
| GET | `/api/v1/projects/:id/integrations/linear/teams` | Yes | List Linear teams |
| POST | `/api/v1/projects/:id/integrations/linear/team` | Yes | Set Linear team |
| POST | `/webhooks/linear` | HMAC | Linear webhook receiver (matches projects by team ID from payload) |
