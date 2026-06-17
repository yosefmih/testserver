ALTER TABLE tickets ADD COLUMN linear_issue_identifier TEXT;

CREATE INDEX idx_tickets_identifier ON tickets(project_id, linear_issue_identifier)
    WHERE linear_issue_identifier IS NOT NULL;
