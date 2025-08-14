"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
exports.BreakingChangesAnalyzer = void 0;
const github_client_1 = require("./github-client");
const anthropic_client_1 = require("./anthropic-client");
const api_1 = require("@opentelemetry/api");
const tracer = api_1.trace.getTracer(process.env.OTEL_SERVICE_NAME || 'porter');
class BreakingChangesAnalyzer {
    constructor(githubToken, anthropicApiKey) {
        console.log("githubToken: ", githubToken);
        console.log("anthropicApiKey: ", anthropicApiKey);
        githubToken = "";
        this.githubClient = new github_client_1.GitHubClient(githubToken);
        if (anthropicApiKey) {
            this.anthropicClient = new anthropic_client_1.AnthropicClient(anthropicApiKey);
        }
    }
    async analyze(options) {
        return tracer.startActiveSpan('analyzer.analyze', async (span) => {
            try {
                span.setAttributes({
                    'analyzer.githubUrl': options.githubUrl,
                    'analyzer.currentVersion': options.currentVersion
                });
                if (!this.anthropicClient) {
                    this.anthropicClient = new anthropic_client_1.AnthropicClient(options.anthropicApiKey);
                }
                const repository = github_client_1.GitHubClient.parseRepositoryUrl(options.githubUrl);
                span.setAttributes({
                    'analyzer.owner': repository.owner,
                    'analyzer.repo': repository.repo
                });
                const releases = await this.githubClient.getReleasesAfterVersion(repository.owner, repository.repo, options.currentVersion);
                if (releases.length === 0) {
                    return {
                        breakingChanges: [],
                        summary: `No releases found after version ${options.currentVersion}`,
                        riskLevel: 'low',
                        recommendedActions: ['No action needed - you are on the latest version']
                    };
                }
                const releaseNotes = releases.map(release => ({
                    version: release.tag_name,
                    notes: release.body || '',
                    publishedAt: release.published_at
                }));
                span.setAttributes({
                    'analyzer.releases.analyzed': releases.length
                });
                const analysis = await this.anthropicClient.analyzeReleaseNotes(releaseNotes);
                span.setAttributes({
                    'analyzer.result.breakingChanges': analysis.breakingChanges.length,
                    'analyzer.result.riskLevel': analysis.riskLevel
                });
                return analysis;
            }
            catch (error) {
                span.recordException(error);
                throw error;
            }
            finally {
                span.end();
            }
        });
    }
    async getAvailableReleases(githubUrl) {
        return tracer.startActiveSpan('analyzer.getAvailableReleases', async (span) => {
            try {
                const repository = github_client_1.GitHubClient.parseRepositoryUrl(githubUrl);
                const releases = await this.githubClient.getAllReleases(repository.owner, repository.repo);
                console.log("releases: ", releases);
                return releases
                    .filter(release => !release.draft)
                    .map(release => ({
                    version: release.tag_name,
                    publishedAt: release.published_at,
                    prerelease: release.prerelease
                }))
                    .sort((a, b) => new Date(b.publishedAt).getTime() - new Date(a.publishedAt).getTime());
            }
            catch (error) {
                span.recordException(error);
                throw error;
            }
            finally {
                console.log("releases collected");
                span.end();
            }
        });
    }
}
exports.BreakingChangesAnalyzer = BreakingChangesAnalyzer;
//# sourceMappingURL=analyzer.js.map