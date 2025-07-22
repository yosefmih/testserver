import { Pool, PoolClient } from 'pg';
import { createTracedOperation } from './telemetry';

let pool: Pool;

export async function initializeDatabase(): Promise<void> {
  const dbHost = process.env.DB_HOST || 'localhost';
  const dbPort = parseInt(process.env.DB_PORT || '5432');
  const dbName = process.env.DB_NAME;
  const dbUser = process.env.DB_USER;
  const dbPassword = process.env.DB_PASSWORD;

  if (!dbName || !dbUser || !dbPassword) {
    throw new Error('Missing required database environment variables: DB_NAME, DB_USER, DB_PASSWORD');
  }

  pool = new Pool({
    host: dbHost,
    port: dbPort,
    database: dbName,
    user: dbUser,
    password: dbPassword,
    max: 20,
    idleTimeoutMillis: 30000,
    connectionTimeoutMillis: 2000,
  });

  pool.on('error', (err) => {
    console.error('Unexpected error on idle client', err);
  });

  console.log('🗄️  Database initialized:', {
    host: dbHost,
    port: dbPort,
    database: dbName,
    user: dbUser
  });

  // Create tables if they don't exist
  await createTables();
}

export async function getClient(): Promise<PoolClient> {
  if (!pool) {
    throw new Error('Database not initialized. Call initializeDatabase() first.');
  }
  
  return createTracedOperation('database.getClient', async () => {
    const client = await pool.connect();
    console.log('📊 Database connection acquired');
    return client;
  });
}

export async function query(text: string, params?: any[]): Promise<any> {
  return createTracedOperation('database.query', async () => {
    const client = await getClient();
    try {
      console.log('🔍 Executing query:', text.slice(0, 100) + (text.length > 100 ? '...' : ''));
      const result = await client.query(text, params);
      console.log(`✅ Query completed, returned ${result.rows.length} rows`);
      return result;
    } finally {
      client.release();
    }
  }, {
    'db.statement': text.slice(0, 200),
    'db.operation': text.split(' ')[0].toLowerCase()
  });
}

// Specific database operations for our services

export interface SlackIntegration {
  id: number;
  workspace_id: string;
  workspace_name: string;
  bot_token: string;
  default_channel: string;
  is_active: boolean;
  created_at: Date;
  updated_at: Date;
}

export interface AnalysisResult {
  id: number;
  trace_id: string;
  repository_url: string;
  from_version?: string;
  to_version: string;
  analysis_summary?: string;
  breaking_changes?: any;
  severity: 'low' | 'medium' | 'high' | 'critical';
  status: 'pending' | 'notified' | 'failed';
  created_at: Date;
  updated_at: Date;
}

export interface Notification {
  id: number;
  analysis_result_id: number;
  slack_integration_id: number;
  trace_id: string;
  channel: string;
  message_ts?: string;
  status: 'pending' | 'sent' | 'failed' | 'retrying';
  error_message?: string;
  attempts: number;
  sent_at?: Date;
  created_at: Date;
  updated_at: Date;
}

export async function getSlackIntegrations(): Promise<SlackIntegration[]> {
  const result = await query(`
    SELECT * FROM integrations_slack_gh 
    WHERE is_active = true 
    ORDER BY created_at DESC
  `);
  return result.rows;
}

export async function createAnalysisResult(data: Omit<AnalysisResult, 'id' | 'created_at' | 'updated_at'>): Promise<AnalysisResult> {
  const result = await query(`
    INSERT INTO analysis_results_gh 
    (trace_id, repository_url, from_version, to_version, analysis_summary, breaking_changes, severity, status)
    VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
    RETURNING *
  `, [
    data.trace_id,
    data.repository_url,
    data.from_version,
    data.to_version,
    data.analysis_summary,
    JSON.stringify(data.breaking_changes),
    data.severity,
    data.status
  ]);
  return result.rows[0];
}

export async function createNotification(data: Omit<Notification, 'id' | 'created_at' | 'updated_at'>): Promise<Notification> {
  const result = await query(`
    INSERT INTO notifications_gh 
    (analysis_result_id, slack_integration_id, trace_id, channel, status, attempts)
    VALUES ($1, $2, $3, $4, $5, $6)
    RETURNING *
  `, [
    data.analysis_result_id,
    data.slack_integration_id,
    data.trace_id,
    data.channel,
    data.status,
    data.attempts
  ]);
  return result.rows[0];
}

export async function updateNotificationStatus(
  id: number, 
  status: Notification['status'], 
  messageTs?: string, 
  errorMessage?: string
): Promise<void> {
  await query(`
    UPDATE notifications_gh 
    SET status = $2, message_ts = $3, error_message = $4, 
        sent_at = CASE WHEN $2 = 'sent' THEN CURRENT_TIMESTAMP ELSE sent_at END,
        attempts = attempts + 1,
        updated_at = CURRENT_TIMESTAMP
    WHERE id = $1
  `, [id, status, messageTs || null, errorMessage || null]);
}

export async function createSlackIntegration(data: Omit<SlackIntegration, 'id' | 'created_at' | 'updated_at'>): Promise<SlackIntegration> {
  const result = await query(`
    INSERT INTO integrations_slack_gh 
    (workspace_id, workspace_name, bot_token, default_channel, is_active)
    VALUES ($1, $2, $3, $4, $5)
    ON CONFLICT (workspace_id) 
    DO UPDATE SET 
      workspace_name = EXCLUDED.workspace_name,
      bot_token = EXCLUDED.bot_token,
      default_channel = EXCLUDED.default_channel,
      is_active = EXCLUDED.is_active,
      updated_at = CURRENT_TIMESTAMP
    RETURNING *
  `, [data.workspace_id, data.workspace_name, data.bot_token, data.default_channel, data.is_active]);
  return result.rows[0];
}

async function createTables(): Promise<void> {
  console.log('🔧 Creating database tables if they don\'t exist...');
  
  try {
    // Create the update function first
    await query(`
      CREATE OR REPLACE FUNCTION update_updated_at_column()
      RETURNS TRIGGER AS $$
      BEGIN
          NEW.updated_at = CURRENT_TIMESTAMP;
          RETURN NEW;
      END;
      $$ language 'plpgsql';
    `);

    // Create integrations_slack_gh table
    await query(`
      CREATE TABLE IF NOT EXISTS integrations_slack_gh (
          id SERIAL PRIMARY KEY,
          workspace_id VARCHAR(255) UNIQUE NOT NULL,
          workspace_name VARCHAR(255) NOT NULL,
          bot_token VARCHAR(512) NOT NULL,
          default_channel VARCHAR(255) NOT NULL DEFAULT '#general',
          is_active BOOLEAN NOT NULL DEFAULT true,
          created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
          updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
      );
    `);

    // Create analysis_results_gh table
    await query(`
      CREATE TABLE IF NOT EXISTS analysis_results_gh (
          id SERIAL PRIMARY KEY,
          trace_id VARCHAR(255) NOT NULL,
          repository_url VARCHAR(512) NOT NULL,
          from_version VARCHAR(100),
          to_version VARCHAR(100) NOT NULL,
          analysis_summary TEXT,
          breaking_changes JSONB,
          severity VARCHAR(20) NOT NULL DEFAULT 'medium',
          status VARCHAR(20) NOT NULL DEFAULT 'pending',
          created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
          updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
      );
    `);

    // Create notifications_gh table
    await query(`
      CREATE TABLE IF NOT EXISTS notifications_gh (
          id SERIAL PRIMARY KEY,
          analysis_result_id INTEGER NOT NULL REFERENCES analysis_results_gh(id),
          slack_integration_id INTEGER NOT NULL REFERENCES integrations_slack_gh(id),
          trace_id VARCHAR(255) NOT NULL,
          channel VARCHAR(255) NOT NULL,
          message_ts VARCHAR(255),
          status VARCHAR(20) NOT NULL DEFAULT 'pending',
          error_message TEXT,
          attempts INTEGER NOT NULL DEFAULT 0,
          sent_at TIMESTAMP WITH TIME ZONE,
          created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
          updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
      );
    `);

    // Create notification_rules_gh table
    await query(`
      CREATE TABLE IF NOT EXISTS notification_rules_gh (
          id SERIAL PRIMARY KEY,
          slack_integration_id INTEGER NOT NULL REFERENCES integrations_slack_gh(id),
          repository_pattern VARCHAR(512),
          severity_threshold VARCHAR(20) NOT NULL DEFAULT 'medium',
          channels JSONB NOT NULL DEFAULT '[]',
          mention_users JSONB DEFAULT '[]',
          is_active BOOLEAN NOT NULL DEFAULT true,
          created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
          updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
      );
    `);

    // Create indexes
    await query('CREATE INDEX IF NOT EXISTS idx_analysis_results_gh_trace_id ON analysis_results_gh(trace_id)');
    await query('CREATE INDEX IF NOT EXISTS idx_analysis_results_gh_status ON analysis_results_gh(status)');
    await query('CREATE INDEX IF NOT EXISTS idx_analysis_results_gh_created_at ON analysis_results_gh(created_at)');
    await query('CREATE INDEX IF NOT EXISTS idx_notifications_gh_trace_id ON notifications_gh(trace_id)');
    await query('CREATE INDEX IF NOT EXISTS idx_notifications_gh_status ON notifications_gh(status)');
    await query('CREATE INDEX IF NOT EXISTS idx_integrations_slack_gh_workspace_id ON integrations_slack_gh(workspace_id)');

    // Create triggers
    await query(`
      DO $$ BEGIN
        IF NOT EXISTS (SELECT 1 FROM pg_trigger WHERE tgname = 'update_integrations_slack_gh_updated_at') THEN
          CREATE TRIGGER update_integrations_slack_gh_updated_at 
            BEFORE UPDATE ON integrations_slack_gh 
            FOR EACH ROW EXECUTE PROCEDURE update_updated_at_column();
        END IF;
      END $$;
    `);

    await query(`
      DO $$ BEGIN
        IF NOT EXISTS (SELECT 1 FROM pg_trigger WHERE tgname = 'update_analysis_results_gh_updated_at') THEN
          CREATE TRIGGER update_analysis_results_gh_updated_at 
            BEFORE UPDATE ON analysis_results_gh 
            FOR EACH ROW EXECUTE PROCEDURE update_updated_at_column();
        END IF;
      END $$;
    `);

    await query(`
      DO $$ BEGIN
        IF NOT EXISTS (SELECT 1 FROM pg_trigger WHERE tgname = 'update_notifications_gh_updated_at') THEN
          CREATE TRIGGER update_notifications_gh_updated_at 
            BEFORE UPDATE ON notifications_gh 
            FOR EACH ROW EXECUTE PROCEDURE update_updated_at_column();
        END IF;
      END $$;
    `);

    await query(`
      DO $$ BEGIN
        IF NOT EXISTS (SELECT 1 FROM pg_trigger WHERE tgname = 'update_notification_rules_gh_updated_at') THEN
          CREATE TRIGGER update_notification_rules_gh_updated_at 
            BEFORE UPDATE ON notification_rules_gh 
            FOR EACH ROW EXECUTE PROCEDURE update_updated_at_column();
        END IF;
      END $$;
    `);

    console.log('✅ Database tables created successfully');
    
  } catch (error) {
    console.error('❌ Failed to create database tables:', error);
    throw error;
  }
}

export async function closeDatabase(): Promise<void> {
  if (pool) {
    await pool.end();
    console.log('🗄️  Database connection pool closed');
  }
}