import { AnalysisResult } from './anthropic-client';
export interface AnalyzeOptions {
    githubUrl: string;
    currentVersion: string;
    githubToken?: string;
    anthropicApiKey: string;
}
export declare class BreakingChangesAnalyzer {
    private githubClient;
    private anthropicClient?;
    constructor(githubToken?: string, anthropicApiKey?: string);
    analyze(options: AnalyzeOptions): Promise<AnalysisResult>;
    getAvailableReleases(githubUrl: string): Promise<Array<{
        version: string;
        publishedAt: string;
        prerelease: boolean;
    }>>;
}
//# sourceMappingURL=analyzer.d.ts.map