ALTER TABLE projects ADD COLUMN IF NOT EXISTS linear_organization_id TEXT;
CREATE UNIQUE INDEX IF NOT EXISTS idx_projects_linear_org_id ON projects(linear_organization_id) WHERE linear_organization_id IS NOT NULL;
ALTER TABLE projects DROP COLUMN IF EXISTS linear_team_id;
