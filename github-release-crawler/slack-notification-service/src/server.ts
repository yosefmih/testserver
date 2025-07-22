#!/usr/bin/env node

import express, { Request, Response, NextFunction } from 'express';
import cors from 'cors';
import * as dotenv from 'dotenv';
import { v4 as uuidv4 } from 'uuid';
import { trace, context } from '@opentelemetry/api';
import { z } from 'zod';

import { initializeTelemetry, extractTraceContext } from './telemetry';
import { initializeDatabase, getSlackIntegrations, createAnalysisResult, createNotification, updateNotificationStatus, createSlackIntegration } from './database';
import { SlackNotifier } from './slack';

// Initialize telemetry first
dotenv.config();
initializeTelemetry();

const app = express();
const port = process.env.PORT || 3001;
const tracer = trace.getTracer(process.env.OTEL_SERVICE_NAME || 'porter');

// Initialize services
let slackNotifier: SlackNotifier;

// Middleware
app.use(cors());
app.use(express.json({ limit: '10mb' }));

// Request ID and tracing middleware
app.use((req: Request, res: Response, next: NextFunction) => {
  // Use incoming request ID if present, otherwise generate new one
  const incomingRequestId = req.headers['x-request-id'] as string;
  const requestId = incomingRequestId || uuidv4();
  
  // Only log if we're generating a new ID vs using an existing one
  if (incomingRequestId) {
    console.log(`🔗 Using incoming request ID: ${requestId}`);
  } else {
    console.log(`🆕 Generated new request ID: ${requestId}`);
  }
  
  req.headers['x-request-id'] = requestId;
  res.setHeader('X-Request-ID', requestId);
  
  // Extract trace context from headers
  extractTraceContext(req.headers);
  
  const spanName = `${req.method} ${req.path}`;
  const span = tracer.startSpan(spanName, {
    attributes: {
      'http.method': req.method,
      'http.url': req.url,
      'http.route': req.path,
      'request.id': requestId,
      'user_agent': req.get('User-Agent') || 'unknown',
      'service.name': 'slack-notification-service'
    }
  });
  
  console.log(`🔍 Started trace span: ${spanName} [${requestId}]`);

  context.with(trace.setSpan(context.active(), span), () => {
    res.on('finish', () => {
      span.setAttributes({
        'http.status_code': res.statusCode,
        'http.response.size': res.get('Content-Length') || 0
      });
      
      if (res.statusCode >= 400) {
        span.recordException(new Error(`HTTP ${res.statusCode} error`));
      }
      
      span.end();
      console.log(`✅ Finished trace span: ${spanName} [${requestId}] - Status: ${res.statusCode}`);
    });

    next();
  });
});

// Validation schemas
const AnalysisNotificationSchema = z.object({
  trace_id: z.string().min(1),
  repository_url: z.string().url(),
  from_version: z.string().optional(),
  to_version: z.string().min(1),
  analysis_summary: z.string().optional(),
  breaking_changes: z.any().optional(),
  severity: z.enum(['low', 'medium', 'high', 'critical']).default('medium'),
  channels: z.array(z.string()).optional()
});

const SlackIntegrationSchema = z.object({
  workspace_id: z.string().min(1),
  workspace_name: z.string().min(1),
  bot_token: z.string().min(1),
  default_channel: z.string().min(1).default('#general')
});

const TestMessageSchema = z.object({
  channel: z.string().min(1),
  workspace_id: z.string().min(1).optional()
});

// Routes

// Health check
app.get('/', (req: Request, res: Response) => {
  res.json({
    service: 'slack-notification-service',
    status: 'healthy',
    version: '1.0.0',
    timestamp: new Date().toISOString()
  });
});

app.get('/health', (req: Request, res: Response) => {
  res.json({ status: 'healthy' });
});

// Get all Slack integrations
app.get('/api/integrations', async (req: Request, res: Response) => {
  const span = tracer.startSpan('get-integrations');
  
  try {
    console.log('📋 Fetching Slack integrations');
    const integrations = await getSlackIntegrations();
    
    // Don't expose bot tokens in response
    const safeIntegrations = integrations.map(integration => ({
      ...integration,
      bot_token: '***hidden***'
    }));
    
    span.setAttributes({
      'integrations.count': integrations.length
    });
    
    res.json({
      success: true,
      integrations: safeIntegrations
    });
    
  } catch (error) {
    span.recordException(error as Error);
    console.error('❌ Failed to fetch integrations:', error);
    res.status(500).json({
      success: false,
      error: 'Failed to fetch integrations'
    });
  } finally {
    span.end();
  }
});

// Create or update Slack integration
app.post('/api/integrations', async (req: Request, res: Response) => {
  const span = tracer.startSpan('create-integration');
  
  try {
    const validatedData = SlackIntegrationSchema.parse(req.body);
    
    console.log('📝 Creating/updating Slack integration:', validatedData.workspace_name);
    
    const integration = await createSlackIntegration({
      ...validatedData,
      is_active: true
    });
    
    // Test the connection
    const testResult = await slackNotifier.testConnection(integration);
    
    span.setAttributes({
      'integration.workspace_id': integration.workspace_id,
      'integration.test_success': testResult
    });
    
    res.json({
      success: true,
      integration: {
        ...integration,
        bot_token: '***hidden***'
      },
      connection_test: testResult
    });
    
  } catch (error) {
    span.recordException(error as Error);
    console.error('❌ Failed to create integration:', error);
    
    if (error instanceof z.ZodError) {
      res.status(400).json({
        success: false,
        error: 'Invalid request data',
        details: error.errors
      });
    } else {
      res.status(500).json({
        success: false,
        error: 'Failed to create integration'
      });
    }
  } finally {
    span.end();
  }
});

// Send test message
app.post('/api/test-message', async (req: Request, res: Response) => {
  const span = tracer.startSpan('send-test-message');
  
  try {
    const { channel, workspace_id } = TestMessageSchema.parse(req.body);
    
    console.log('🧪 Sending test message to channel:', channel);
    
    const integrations = await getSlackIntegrations();
    let targetIntegration = integrations.find(i => i.workspace_id === workspace_id);
    
    if (!targetIntegration && integrations.length > 0) {
      targetIntegration = integrations[0]; // Use first integration if none specified
    }
    
    if (!targetIntegration) {
      return res.status(400).json({
        success: false,
        error: 'No Slack integrations found'
      });
    }
    
    const result = await slackNotifier.sendTestMessage(targetIntegration, channel);
    
    span.setAttributes({
      'test.channel': channel,
      'test.success': result.success,
      'integration.workspace_id': targetIntegration.workspace_id
    });
    
    res.json({
      success: result.success,
      message_ts: result.messageTs,
      error: result.error
    });
    
  } catch (error) {
    span.recordException(error as Error);
    console.error('❌ Failed to send test message:', error);
    
    if (error instanceof z.ZodError) {
      res.status(400).json({
        success: false,
        error: 'Invalid request data',
        details: error.errors
      });
    } else {
      res.status(500).json({
        success: false,
        error: 'Failed to send test message'
      });
    }
  } finally {
    span.end();
  }
});

// Main notification endpoint - called by the GitHub Release Crawler
app.post('/api/notify', async (req: Request, res: Response) => {
  const span = tracer.startSpan('process-analysis-notification');
  
  try {
    const validatedData = AnalysisNotificationSchema.parse(req.body);
    
    console.log('📧 Processing analysis notification:', {
      repository: validatedData.repository_url,
      version: validatedData.to_version,
      severity: validatedData.severity,
      trace_id: validatedData.trace_id
    });
    
    // Store analysis result in database
    const analysisResult = await createAnalysisResult({
      trace_id: validatedData.trace_id,
      repository_url: validatedData.repository_url,
      from_version: validatedData.from_version,
      to_version: validatedData.to_version,
      analysis_summary: validatedData.analysis_summary,
      breaking_changes: validatedData.breaking_changes,
      severity: validatedData.severity,
      status: 'pending'
    });
    
    // Get active Slack integrations
    const integrations = await getSlackIntegrations();
    
    if (integrations.length === 0) {
      console.log('⚠️  No active Slack integrations found');
      return res.json({
        success: true,
        message: 'Analysis stored but no Slack integrations configured',
        analysis_id: analysisResult.id
      });
    }
    
    const results = [];
    
    // Send notifications to all integrations
    for (const integration of integrations) {
      const channels = validatedData.channels || [integration.default_channel];
      
      for (const channel of channels) {
        try {
          // Create notification record
          const notification = await createNotification({
            analysis_result_id: analysisResult.id,
            slack_integration_id: integration.id,
            trace_id: validatedData.trace_id,
            channel: channel,
            status: 'pending',
            attempts: 0
          });
          
          // Send Slack message
          const slackResult = await slackNotifier.sendAnalysisNotification(
            integration, 
            analysisResult, 
            channel
          );
          
          // Update notification status
          await updateNotificationStatus(
            notification.id,
            slackResult.success ? 'sent' : 'failed',
            slackResult.messageTs,
            slackResult.error
          );
          
          results.push({
            integration: integration.workspace_name,
            channel,
            success: slackResult.success,
            message_ts: slackResult.messageTs,
            error: slackResult.error
          });
          
        } catch (error) {
          console.error('❌ Failed to process notification:', error);
          results.push({
            integration: integration.workspace_name,
            channel,
            success: false,
            error: (error as Error).message
          });
        }
      }
    }
    
    span.setAttributes({
      'analysis.repository': validatedData.repository_url,
      'analysis.severity': validatedData.severity,
      'analysis.trace_id': validatedData.trace_id,
      'notifications.sent': results.filter(r => r.success).length,
      'notifications.failed': results.filter(r => !r.success).length
    });
    
    res.json({
      success: true,
      analysis_id: analysisResult.id,
      notifications: results
    });
    
  } catch (error) {
    span.recordException(error as Error);
    console.error('❌ Failed to process notification:', error);
    
    if (error instanceof z.ZodError) {
      res.status(400).json({
        success: false,
        error: 'Invalid notification data',
        details: error.errors
      });
    } else {
      res.status(500).json({
        success: false,
        error: 'Failed to process notification'
      });
    }
  } finally {
    span.end();
  }
});

// Error handling middleware
app.use((error: Error, req: Request, res: Response, _next: NextFunction) => {
  console.error('🚨 Unhandled error:', error);
  res.status(500).json({
    success: false,
    error: 'Internal server error'
  });
});

// Initialize services and start server
async function startServer() {
  try {
    console.log('🚀 Starting Slack Notification Service...');
    
    // Initialize database
    await initializeDatabase();
    
    // Initialize Slack notifier
    slackNotifier = new SlackNotifier();
    
    app.listen(port, () => {
      console.log('🚀 Slack Notification Service running on port', port);
      console.log('📊 OpenTelemetry traces exported to:', process.env.OTEL_EXPORTER_OTLP_ENDPOINT || 'http://localhost:4318/v1/traces');
      console.log('🏥 Health check: http://localhost:' + port + '/health');
      console.log('📖 API endpoints:');
      console.log('  GET  /api/integrations - List Slack integrations');
      console.log('  POST /api/integrations - Create/update Slack integration');
      console.log('  POST /api/test-message - Send test message');
      console.log('  POST /api/notify - Process analysis notification');
    });
    
  } catch (error) {
    console.error('❌ Failed to start server:', error);
    process.exit(1);
  }
}

startServer();