-- Slack Notification Service Database Schema

-- Table for storing Slack workspace configurations
CREATE TABLE IF NOT EXISTS integrations_slack_gh (
    id SERIAL PRIMARY KEY,
    workspace_id VARCHAR(255) UNIQUE NOT NULL,
    workspace_name VARCHAR(255) NOT NULL,
    bot_token VARCHAR(512) NOT NULL, -- encrypted in production
    default_channel VARCHAR(255) NOT NULL DEFAULT '#general',
    is_active BOOLEAN NOT NULL DEFAULT true,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Table for storing analysis results from the crawler
CREATE TABLE IF NOT EXISTS analysis_results_gh (
    id SERIAL PRIMARY KEY,
    trace_id VARCHAR(255) NOT NULL, -- for distributed tracing correlation
    repository_url VARCHAR(512) NOT NULL,
    from_version VARCHAR(100),
    to_version VARCHAR(100) NOT NULL,
    analysis_summary TEXT,
    breaking_changes JSONB, -- store detailed breaking changes
    severity VARCHAR(20) NOT NULL DEFAULT 'medium', -- low, medium, high, critical
    status VARCHAR(20) NOT NULL DEFAULT 'pending', -- pending, notified, failed
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Table for tracking notification delivery
CREATE TABLE IF NOT EXISTS notifications_gh (
    id SERIAL PRIMARY KEY,
    analysis_result_id INTEGER NOT NULL REFERENCES analysis_results_gh(id),
    slack_integration_id INTEGER NOT NULL REFERENCES integrations_slack_gh(id),
    trace_id VARCHAR(255) NOT NULL, -- for distributed tracing
    channel VARCHAR(255) NOT NULL,
    message_ts VARCHAR(255), -- Slack message timestamp for updates
    status VARCHAR(20) NOT NULL DEFAULT 'pending', -- pending, sent, failed, retrying
    error_message TEXT,
    attempts INTEGER NOT NULL DEFAULT 0,
    sent_at TIMESTAMP WITH TIME ZONE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Table for notification preferences/rules
CREATE TABLE IF NOT EXISTS notification_rules_gh (
    id SERIAL PRIMARY KEY,
    slack_integration_id INTEGER NOT NULL REFERENCES integrations_slack_gh(id),
    repository_pattern VARCHAR(512), -- regex pattern for repo matching
    severity_threshold VARCHAR(20) NOT NULL DEFAULT 'medium', -- minimum severity to notify
    channels JSONB NOT NULL DEFAULT '[]', -- array of channels to notify
    mention_users JSONB DEFAULT '[]', -- array of user IDs to mention
    is_active BOOLEAN NOT NULL DEFAULT true,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Indexes for performance
CREATE INDEX IF NOT EXISTS idx_analysis_results_gh_trace_id ON analysis_results_gh(trace_id);
CREATE INDEX IF NOT EXISTS idx_analysis_results_gh_status ON analysis_results_gh(status);
CREATE INDEX IF NOT EXISTS idx_analysis_results_gh_created_at ON analysis_results_gh(created_at);
CREATE INDEX IF NOT EXISTS idx_notifications_gh_trace_id ON notifications_gh(trace_id);
CREATE INDEX IF NOT EXISTS idx_notifications_gh_status ON notifications_gh(status);
CREATE INDEX IF NOT EXISTS idx_integrations_slack_gh_workspace_id ON integrations_slack_gh(workspace_id);

-- Update triggers for updated_at timestamps
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ language 'plpgsql';

CREATE TRIGGER update_integrations_slack_gh_updated_at BEFORE UPDATE ON integrations_slack_gh FOR EACH ROW EXECUTE PROCEDURE update_updated_at_column();
CREATE TRIGGER update_analysis_results_gh_updated_at BEFORE UPDATE ON analysis_results_gh FOR EACH ROW EXECUTE PROCEDURE update_updated_at_column();
CREATE TRIGGER update_notifications_gh_updated_at BEFORE UPDATE ON notifications_gh FOR EACH ROW EXECUTE PROCEDURE update_updated_at_column();
CREATE TRIGGER update_notification_rules_gh_updated_at BEFORE UPDATE ON notification_rules_gh FOR EACH ROW EXECUTE PROCEDURE update_updated_at_column();