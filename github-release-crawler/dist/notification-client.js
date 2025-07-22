"use strict";
var __importDefault = (this && this.__importDefault) || function (mod) {
    return (mod && mod.__esModule) ? mod : { "default": mod };
};
Object.defineProperty(exports, "__esModule", { value: true });
exports.NotificationClient = void 0;
const axios_1 = __importDefault(require("axios"));
const api_1 = require("@opentelemetry/api");
class NotificationClient {
    constructor(baseUrl, timeout = 10000) {
        this.baseUrl = baseUrl || process.env.NOTIFICATION_SERVICE_URL || 'http://slack-notification-service:3001';
        this.timeout = timeout;
        console.log('🔧 Notification client initialized:', this.baseUrl);
    }
    async sendAnalysisNotification(notification) {
        const tracer = api_1.trace.getTracer('github-release-crawler', '1.0.0');
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
                const response = await axios_1.default.post(`${this.baseUrl}/api/notify`, notification, {
                    timeout: this.timeout,
                    headers: {
                        'Content-Type': 'application/json',
                        'x-request-id': notification.trace_id,
                        // Propagate trace context
                        'traceparent': this.getTraceParent(span),
                    }
                });
                span.setAttributes({
                    'http.status_code': response.status,
                    'notification.success': response.data.success
                });
                if (response.data.success) {
                    console.log('✅ Analysis notification sent successfully:', {
                        analysis_id: response.data.analysis_id,
                        notifications_sent: response.data.notifications?.filter((n) => n.success).length || 0,
                        notifications_failed: response.data.notifications?.filter((n) => !n.success).length || 0
                    });
                }
                else {
                    console.error('❌ Analysis notification failed:', response.data.error);
                }
                span.setStatus({ code: api_1.SpanStatusCode.OK });
                return response.data;
            }
            catch (error) {
                console.error('❌ Failed to send analysis notification:', error);
                span.recordException(error);
                span.setStatus({
                    code: api_1.SpanStatusCode.ERROR,
                    message: error.message
                });
                if (axios_1.default.isAxiosError(error)) {
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
                    error: error.message
                };
            }
            finally {
                span.end();
            }
        });
    }
    async testConnection() {
        const tracer = api_1.trace.getTracer('github-release-crawler', '1.0.0');
        return tracer.startActiveSpan('notification.testConnection', async (span) => {
            try {
                console.log('🧪 Testing notification service connection...');
                const response = await axios_1.default.get(`${this.baseUrl}/health`, {
                    timeout: 5000
                });
                const isHealthy = response.status === 200 && response.data.status === 'healthy';
                span.setAttributes({
                    'test.success': isHealthy,
                    'http.status_code': response.status
                });
                if (isHealthy) {
                    console.log('✅ Notification service is healthy');
                }
                else {
                    console.log('⚠️  Notification service health check failed');
                }
                span.setStatus({ code: api_1.SpanStatusCode.OK });
                return isHealthy;
            }
            catch (error) {
                console.error('❌ Notification service connection test failed:', error);
                span.recordException(error);
                span.setStatus({
                    code: api_1.SpanStatusCode.ERROR,
                    message: error.message
                });
                return false;
            }
            finally {
                span.end();
            }
        });
    }
    getTraceParent(span) {
        try {
            const spanContext = span.spanContext();
            const traceId = spanContext.traceId;
            const spanId = spanContext.spanId;
            const flags = spanContext.traceFlags || 1;
            return `00-${traceId}-${spanId}-0${flags}`;
        }
        catch (error) {
            console.warn('Failed to generate traceparent header:', error);
            return '';
        }
    }
    // Helper method to determine severity from analysis content
    static determineSeverity(analysis) {
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
exports.NotificationClient = NotificationClient;
//# sourceMappingURL=notification-client.js.map