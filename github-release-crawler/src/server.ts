#!/usr/bin/env node

import express, { Request, Response, NextFunction } from 'express';
import cors from 'cors';
import * as dotenv from 'dotenv';
import { v4 as uuidv4 } from 'uuid';
import { trace, context } from '@opentelemetry/api';
import path from 'path';
import axios from 'axios';
import { BreakingChangesAnalyzer } from './analyzer';
import { initializeTelemetry } from './telemetry';
import { NotificationClient, NotificationRequest } from './notification-client';

dotenv.config();
initializeTelemetry();
  
const app = express();
const port = process.env.PORT || 3000;
const tracer = trace.getTracer(process.env.OTEL_SERVICE_NAME || 'porter');

// Initialize notification client
const notificationClient = new NotificationClient();

// Helper function to generate traceparent header for distributed tracing
function getTraceParent(span: any): string {
  try {
    const spanContext = span.spanContext();
    const traceId = spanContext.traceId;
    const spanId = spanContext.spanId;
    const flags = spanContext.traceFlags || 1;
    return `00-${traceId}-${spanId}-0${flags}`;
  } catch (error) {
    console.warn('Failed to generate traceparent header:', error);
    return '';
  }
}

// Middleware
app.use(cors());
app.use(express.json());

// Serve the frontend SPA
const spaPath = path.join(__dirname, './frontend-app/dist');
app.use(express.static(spaPath));

// Extend Request interface to include requestId
declare module 'express-serve-static-core' {
  interface Request {
    requestId: string;
  }
}

// Request ID middleware with tracing
app.use((req: Request, res: Response, next: NextFunction) => {
  req.requestId = uuidv4();
  res.setHeader('X-Request-ID', req.requestId);
  
  // Start a trace span for the entire request
  const spanName = `${req.method} ${req.path}`;
  const span = tracer.startSpan(spanName, {
    attributes: {
      'http.method': req.method,
      'http.url': req.url,
      'http.route': req.path,
      'request.id': req.requestId,
      'user_agent': req.get('User-Agent') || 'unknown'
    }
  });
  
  console.log(`🔍 Started trace span: ${spanName} [${req.requestId}]`);

  // Store span in context for this request
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
      console.log(`✅ Finished trace span: ${spanName} [${req.requestId}] - Status: ${res.statusCode}`);
    });

    next();
  });
});

// Health check endpoint
app.get('/api/health', (req: Request, res: Response) => {
  res.json({ 
    status: 'healthy',
    requestId: req.requestId,
    timestamp: new Date().toISOString()
  });
});

// API documentation endpoint
app.get('/api', (req: Request, res: Response) => {
  res.json({
    service: 'GitHub Release Crawler',
    version: '1.0.0',
    requestId: req.requestId,
    endpoints: {
      'POST /api/analyze': {
        description: 'Analyze GitHub repository releases for breaking changes',
        body: {
          githubUrl: 'https://github.com/owner/repo',
          currentVersion: 'v1.0.0'
        },
        optional: {
          githubToken: 'GitHub API token (for higher rate limits)'
        }
      },
      'GET /api/health': 'Health check endpoint'
    },
    tracing: {
      enabled: true,
      exportEndpoint: process.env.OTEL_EXPORTER_OTLP_ENDPOINT || 'http://localhost:4318/v1/traces'
    }
  });
});

// Main analysis endpoint
app.post('/api/analyze', async (req: Request, res: Response) => {
  return tracer.startActiveSpan('analyze-releases', async (span) => {
    try {
      const { githubUrl, currentVersion, githubToken } = req.body;

      // Validation
      if (!githubUrl || !currentVersion) {
        span.setAttributes({
          'error': true,
          'error.type': 'validation_error'
        });
        return res.status(400).json({
          error: 'Missing required fields',
          required: ['githubUrl', 'currentVersion'],
          requestId: req.requestId
        });
      }

      // Validate GitHub URL format
      if (!githubUrl.match(/^https:\/\/github\.com\/[^\/]+\/[^\/]+/)) {
        span.setAttributes({
          'error': true,
          'error.type': 'invalid_github_url'
        });
        return res.status(400).json({
          error: 'Invalid GitHub URL format',
          expected: 'https://github.com/owner/repo',
          requestId: req.requestId
        });
      }

      span.setAttributes({
        'github.url': githubUrl,
        'github.currentVersion': currentVersion,
        'github.hasToken': !!githubToken,
        'request.id': req.requestId
      });

      const anthropicApiKey = process.env.ANTHROPIC_API_KEY;
      if (!anthropicApiKey) {
        span.setAttributes({
          'error': true,
          'error.type': 'missing_anthropic_key'
        });
        return res.status(500).json({
          error: 'Anthropic API key not configured',
          requestId: req.requestId
        });
      }

      const analyzer = new BreakingChangesAnalyzer(
        githubToken || process.env.GITHUB_TOKEN,
        anthropicApiKey
      );

      console.log(`[${req.requestId}] Starting analysis for ${githubUrl} after version ${currentVersion}`);
      
      const result = await analyzer.analyze({
        githubUrl,
        currentVersion,
        githubToken: githubToken || process.env.GITHUB_TOKEN,
        anthropicApiKey
      });

      // Get the latest version from breaking changes or use current version
      const latestVersion = result.breakingChanges.length > 0 
        ? result.breakingChanges[result.breakingChanges.length - 1].version 
        : currentVersion;

      span.setAttributes({
        'analysis.breakingChanges.count': result.breakingChanges.length,
        'analysis.riskLevel': result.riskLevel,
        'success': true
      });

      console.log(`[${req.requestId}] Analysis completed: ${result.breakingChanges.length} breaking changes found, risk level: ${result.riskLevel}`);

      // Send notification to Slack notification service
      // try {
      //   const severity = NotificationClient.determineSeverity(result);
      //   // Use the same request ID throughout the entire flow for proper tracing
      //   const traceId = req.requestId;
        
      //   const notificationRequest: NotificationRequest = {
      //     trace_id: traceId,
      //     repository_url: githubUrl,
      //     from_version: currentVersion,
      //     to_version: latestVersion,
      //     analysis_summary: `Found ${result.breakingChanges.length} breaking changes with ${result.riskLevel} risk level`,
      //     breaking_changes: {
      //       summary: result.summary || 'Analysis completed',
      //       changes: result.breakingChanges,
      //       risk_level: result.riskLevel,
      //       latest_version: latestVersion
      //     },
      //     severity: severity
      //   };

      //   console.log(`[${req.requestId}] Sending notification with severity: ${severity}`);
        
      //   // Send notification asynchronously (don't block response)
      //   notificationClient.sendAnalysisNotification(notificationRequest)
      //     .then((notificationResult) => {
      //       if (notificationResult.success) {
      //         console.log(`[${req.requestId}] ✅ Notification sent successfully`);
      //       } else {
      //         console.log(`[${req.requestId}] ⚠️  Notification failed: ${notificationResult.error}`);
      //       }
      //     })
      //     .catch((error) => {
      //       console.error(`[${req.requestId}] ❌ Notification error:`, error);
      //     });

      // } catch (notificationError) {
      //   // Don't fail the main response if notification fails
      //   console.error(`[${req.requestId}] ⚠️  Failed to send notification:`, notificationError);
      // }

      res.json({
        requestId: req.requestId,
        timestamp: new Date().toISOString(),
        input: {
          githubUrl,
          currentVersion
        },
        analysis: result
      });

    } catch (error) {
      const errorMessage = error instanceof Error ? error.message : 'Unknown error';
      
      span.recordException(error as Error);
      span.setAttributes({
        'error': true,
        'error.message': errorMessage
      });

      console.error(`[${req.requestId}] Analysis failed:`, error);
      
      res.status(500).json({
        error: 'Analysis failed',
        message: errorMessage,
        requestId: req.requestId
      });
    } finally {
      span.end();
    }
  });
});

// Proxy endpoints for Slack notification service with distributed tracing
app.get('/api/notifications/*', async (req: Request, res: Response) => {
  return tracer.startActiveSpan(`proxy-${req.method} ${req.path}`, async (span) => {
    try {
      const notificationServiceUrl = process.env.NOTIFICATION_SERVICE_URL || 'http://slack-notification-service:80';
      const targetPath = req.path.replace('/api/notifications', '/api');
      const targetUrl = `${notificationServiceUrl}${targetPath}`;
      
      span.setAttributes({
        'proxy.method': req.method,
        'proxy.originalPath': req.path,
        'proxy.targetPath': targetPath,
        'proxy.targetUrl': targetUrl,
        'request.id': req.requestId
      });

      console.log(`🔄 [${req.requestId}] Proxying GET ${req.path} to ${targetUrl}`);

      // Generate traceparent header for distributed tracing
      const traceparent = getTraceParent(span);
      
      const response = await axios.get(targetUrl, {
        params: req.query,
        headers: {
          'x-request-id': req.requestId,
          'traceparent': traceparent,
          'Content-Type': 'application/json'
        },
        timeout: 30000
      });

      span.setAttributes({
        'proxy.response.status': response.status,
        'proxy.success': true
      });

      console.log(`✅ [${req.requestId}] Proxy GET successful: ${response.status}`);
      res.status(response.status).json(response.data);

    } catch (error) {
      const errorMessage = error instanceof Error ? error.message : 'Unknown proxy error';
      span.recordException(error as Error);
      span.setAttributes({
        'proxy.error': true,
        'proxy.errorMessage': errorMessage
      });

      console.error(`❌ [${req.requestId}] Proxy GET failed:`, error);
      
      if (axios.isAxiosError(error) && error.response) {
        res.status(error.response.status).json(error.response.data);
      } else {
        res.status(500).json({ error: 'Proxy request failed', message: errorMessage });
      }
    } finally {
      span.end();
    }
  });
});

app.post('/api/notifications/*', async (req: Request, res: Response) => {
  return tracer.startActiveSpan(`proxy-${req.method} ${req.path}`, async (span) => {
    try {
      const notificationServiceUrl = process.env.NOTIFICATION_SERVICE_URL || 'http://slack-notification-service:80';
      const targetPath = req.path.replace('/api/notifications', '/api');
      const targetUrl = `${notificationServiceUrl}${targetPath}`;
      
      span.setAttributes({
        'proxy.method': req.method,
        'proxy.originalPath': req.path,
        'proxy.targetPath': targetPath,
        'proxy.targetUrl': targetUrl,
        'request.id': req.requestId,
        'proxy.bodySize': JSON.stringify(req.body).length
      });

      console.log(`🔄 [${req.requestId}] Proxying POST ${req.path} to ${targetUrl}`);

      // Generate traceparent header for distributed tracing
      const traceparent = getTraceParent(span);
      
      const response = await axios.post(targetUrl, req.body, {
        headers: {
          'x-request-id': req.requestId,
          'traceparent': traceparent,
          'Content-Type': 'application/json'
        },
        timeout: 30000
      });

      span.setAttributes({
        'proxy.response.status': response.status,
        'proxy.success': true
      });

      console.log(`✅ [${req.requestId}] Proxy POST successful: ${response.status}`);
      res.status(response.status).json(response.data);

    } catch (error) {
      const errorMessage = error instanceof Error ? error.message : 'Unknown proxy error';
      span.recordException(error as Error);
      span.setAttributes({
        'proxy.error': true,
        'proxy.errorMessage': errorMessage
      });

      console.error(`❌ [${req.requestId}] Proxy POST failed:`, error);
      
      if (axios.isAxiosError(error) && error.response) {
        res.status(error.response.status).json(error.response.data);
      } else {
        res.status(500).json({ error: 'Proxy request failed', message: errorMessage });
      }
    } finally {
      span.end();
    }
  });
});

// All other GET requests not handled before will return the SPA's index.html
app.get('*', (req: Request, res: Response) => {
  // Skip API routes that haven't been handled yet (will result in 404)
  if (req.path.startsWith('/api/')) {
    return res.status(404).json({
      error: 'API endpoint not found',
      path: req.path,
      requestId: req.requestId
    });
  }
  res.sendFile(path.join(spaPath, 'index.html'));
});


// Error handling middleware
app.use((error: Error, req: Request, res: Response) => {
  console.error(`[${req.requestId}] Unhandled error:`, error);
  
  res.status(500).json({
    error: 'Internal server error',
    message: error.message,
    requestId: req.requestId
  });
});

// 404 handler
app.use((req: Request, res: Response) => {
  res.status(404).json({
    error: 'Endpoint not found',
    path: req.path,
    requestId: req.requestId
  });
});

app.listen(port, () => {
  console.log(`🚀 GitHub Release Crawler server running on port ${port}`);
  console.log(`📊 OpenTelemetry traces exported to: ${process.env.OTEL_EXPORTER_OTLP_ENDPOINT || 'http://localhost:4318/v1/traces'}`);
  console.log(`🏥 Health check: http://localhost:${port}/health`);
  console.log(`📖 API docs: http://localhost:${port}/`);
});

export default app;