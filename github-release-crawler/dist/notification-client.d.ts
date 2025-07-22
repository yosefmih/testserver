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
export declare class NotificationClient {
    private baseUrl;
    private timeout;
    constructor(baseUrl?: string, timeout?: number);
    sendAnalysisNotification(notification: NotificationRequest): Promise<NotificationResponse>;
    testConnection(): Promise<boolean>;
    private getTraceParent;
    static determineSeverity(analysis: any): 'low' | 'medium' | 'high' | 'critical';
}
//# sourceMappingURL=notification-client.d.ts.map