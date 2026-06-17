CREATE EXTENSION IF NOT EXISTS "pgcrypto";

CREATE TABLE users (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    email TEXT UNIQUE NOT NULL,
    name TEXT NOT NULL,
    google_id TEXT UNIQUE NOT NULL,
    avatar_url TEXT,
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE projects (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(id),
    name TEXT NOT NULL,
    github_installation_id BIGINT,
    github_repo TEXT,
    linear_access_token TEXT,
    linear_refresh_token TEXT,
    linear_team_id TEXT,
    linear_webhook_id TEXT,
    linear_webhook_secret TEXT,
    autopilot_label TEXT DEFAULT 'autopilot',
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE jobs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id UUID NOT NULL REFERENCES projects(id),
    linear_issue_id TEXT NOT NULL,
    linear_issue_title TEXT NOT NULL,
    linear_issue_url TEXT,
    status TEXT NOT NULL DEFAULT 'pending',
    pr_url TEXT,
    error TEXT,
    sandbox_id TEXT,
    created_at TIMESTAMPTZ DEFAULT now(),
    finished_at TIMESTAMPTZ
);

CREATE INDEX idx_jobs_project_id ON jobs(project_id);
CREATE INDEX idx_jobs_status ON jobs(status);
CREATE INDEX idx_projects_user_id ON projects(user_id);
