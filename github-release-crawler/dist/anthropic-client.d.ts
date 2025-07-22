export interface BreakingChange {
    version: string;
    severity: 'low' | 'medium' | 'high' | 'critical';
    description: string;
    category: string;
    mitigation?: string;
}
export interface AnalysisResult {
    breakingChanges: BreakingChange[];
    summary: string;
    riskLevel: 'low' | 'medium' | 'high' | 'critical';
    recommendedActions: string[];
}
export declare class AnthropicClient {
    private client;
    constructor(apiKey: string);
    analyzeReleaseNotes(releaseNotes: Array<{
        version: string;
        notes: string;
        publishedAt: string;
    }>): Promise<AnalysisResult>;
    private buildAnalysisPrompt;
    private parseAnalysisResponse;
}
//# sourceMappingURL=anthropic-client.d.ts.map