DROP TABLE IF EXISTS jobs;

CREATE TABLE tickets (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    linear_issue_id TEXT NOT NULL,
    linear_issue_title TEXT NOT NULL,
    linear_issue_description TEXT,
    linear_issue_url TEXT,
    pr_repo TEXT,
    pr_number INTEGER,
    pr_url TEXT,
    volume_id TEXT,
    status TEXT NOT NULL DEFAULT 'active',
    debounce_until TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now(),
    UNIQUE (project_id, linear_issue_id)
);

CREATE INDEX idx_tickets_project_id ON tickets(project_id);
CREATE INDEX idx_tickets_status ON tickets(status) WHERE status = 'active';
CREATE INDEX idx_tickets_pr ON tickets(pr_repo, pr_number) WHERE pr_repo IS NOT NULL;

CREATE TABLE runs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    ticket_id UUID NOT NULL REFERENCES tickets(id) ON DELETE CASCADE,
    kind TEXT NOT NULL DEFAULT 'initial',
    sandbox_id TEXT,
    callback_token TEXT,
    status TEXT NOT NULL DEFAULT 'pending',
    error TEXT,
    created_at TIMESTAMPTZ DEFAULT now(),
    finished_at TIMESTAMPTZ
);

CREATE INDEX idx_runs_ticket_id ON runs(ticket_id);
CREATE INDEX idx_runs_status ON runs(status) WHERE status IN ('pending', 'launching', 'running');
CREATE INDEX idx_runs_callback_token ON runs(callback_token) WHERE callback_token IS NOT NULL;

CREATE TABLE review_comments (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    ticket_id UUID NOT NULL REFERENCES tickets(id) ON DELETE CASCADE,
    github_comment_id BIGINT NOT NULL UNIQUE,
    author TEXT NOT NULL,
    body TEXT NOT NULL,
    path TEXT,
    position INTEGER,
    addressed BOOLEAN NOT NULL DEFAULT false,
    created_at TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX idx_review_comments_ticket ON review_comments(ticket_id) WHERE addressed = false;
