import axios from 'axios';
import { trace, SpanStatusCode } from '@opentelemetry/api';

export interface NotificationRequest {
  trace_id: string;
  repository_url: string;
  from_version?: string;
  to_version: string;
  analysis_summary?: string;
  breaking_changes?: any;
  severity: 'low' | 'medium' | 'high' | 'critical';
  channels?: string[];
}

export interface NotificationResponse {
  success: boolean;
  analysis_id?: number;
  notifications?: Array<{
    integration: string;
    channel: string;
    success: boolean;
    message_ts?: string;
    error?: string;
  }>;
  error?: string;
}

export class NotificationClient {
  private baseUrl: string;
  private timeout: number;

  constructor(baseUrl?: string, timeout = 10000) {
    this.baseUrl = baseUrl || process.env.NOTIFICATION_SERVICE_URL || 'http://slack-notification-service:3001';
    this.timeout = timeout;
    console.log('🔧 Notification client initialized:', this.baseUrl);
  }

  async sendAnalysisNotification(notification: NotificationRequest): Promise<NotificationResponse> {
    const tracer = trace.getTracer(process.env.OTEL_SERVICE_NAME || 'porter', '1.0.0');
    
    return tracer.startActiveSpan('notification.sendAnalysis', async (span) => {
      try {
        console.log('📧 Sending analysis notification to service:', {
          repository: notification.repository_url,
          version: notification.to_version,
          severity: notification.severity,
          trace_id: notification.trace_id
        });

        span.setAttributes({
          'notification.repository': notification.repository_url,
          'notification.version': notification.to_version,
          'notification.severity': notification.severity,
          'notification.trace_id': notification.trace_id,
          'http.url': `${this.baseUrl}/api/notify`,
          'http.method': 'POST'
        });

        const response = await axios.post(
          `${this.baseUrl}/api/notify`,
          notification,
          {
            timeout: this.timeout,
            headers: {
              'Content-Type': 'application/json',
              'x-request-id': notification.trace_id,
              // Propagate trace context
              'traceparent': this.getTraceParent(span),
            }
          }
        );

        span.setAttributes({
          'http.status_code': response.status,
          'notification.success': response.data.success
        });

        if (response.data.success) {
          console.log('✅ Analysis notification sent successfully:', {
            analysis_id: response.data.analysis_id,
            notifications_sent: response.data.notifications?.filter((n: any) => n.success).length || 0,
            notifications_failed: response.data.notifications?.filter((n: any) => !n.success).length || 0
          });
        } else {
          console.error('❌ Analysis notification failed:', response.data.error);
        }

        span.setStatus({ code: SpanStatusCode.OK });
        return response.data;

      } catch (error) {
        console.error('❌ Failed to send analysis notification:', error);
        
        span.recordException(error as Error);
        span.setStatus({ 
          code: SpanStatusCode.ERROR, 
          message: (error as Error).message 
        });

        if (axios.isAxiosError(error)) {
          span.setAttributes({
            'http.status_code': error.response?.status || 0,
            'error.type': 'http_error'
          });
          
          return {
            success: false,
            error: `HTTP ${error.response?.status || 'unknown'}: ${error.message}`
          };
        }

        return {
          success: false,
          error: (error as Error).message
        };
      } finally {
        span.end();
      }
    });
  }

  async testConnection(): Promise<boolean> {
    const tracer = trace.getTracer(process.env.OTEL_SERVICE_NAME || 'porter', '1.0.0');
    
    return tracer.startActiveSpan('notification.testConnection', async (span) => {
      try {
        console.log('🧪 Testing notification service connection...');
        
        const response = await axios.get(`${this.baseUrl}/health`, {
          timeout: 5000
        });

        const isHealthy = response.status === 200 && response.data.status === 'healthy';
        
        span.setAttributes({
          'test.success': isHealthy,
          'http.status_code': response.status
        });

        if (isHealthy) {
          console.log('✅ Notification service is healthy');
        } else {
          console.log('⚠️  Notification service health check failed');
        }

        span.setStatus({ code: SpanStatusCode.OK });
        return isHealthy;

      } catch (error) {
        console.error('❌ Notification service connection test failed:', error);
        
        span.recordException(error as Error);
        span.setStatus({ 
          code: SpanStatusCode.ERROR, 
          message: (error as Error).message 
        });

        return false;
      } finally {
        span.end();
      }
    });
  }

  private getTraceParent(span: any): string {
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

  // Helper method to determine severity from analysis content
  static determineSeverity(analysis: any): 'low' | 'medium' | 'high' | 'critical' {
    if (!analysis || typeof analysis !== 'object') {
      return 'medium';
    }

    const content = JSON.stringify(analysis).toLowerCase();
    
    // Critical indicators
    if (content.includes('breaking change') || 
        content.includes('major version') || 
        content.includes('incompatible') ||
        content.includes('critical')) {
      return 'critical';
    }
    
    // High severity indicators
    if (content.includes('deprecated') || 
        content.includes('removed') || 
        content.includes('security') ||
        content.includes('vulnerability')) {
      return 'high';
    }
    
    // Low severity indicators
    if (content.includes('minor') || 
        content.includes('patch') || 
        content.includes('bug fix') ||
        content.includes('documentation')) {
      return 'low';
    }

    // Default to medium
    return 'medium';
  }
}