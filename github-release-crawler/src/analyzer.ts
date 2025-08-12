import { GitHubClient } from './github-client';
import { AnthropicClient, AnalysisResult } from './anthropic-client';
import { trace } from '@opentelemetry/api';
import { Langfuse } from 'langfuse';
import { v4 as uuidv4 } from 'uuid';

const tracer = trace.getTracer(process.env.OTEL_SERVICE_NAME || 'porter');

// Initialize Langfuse client
const langfuse = new Langfuse({
  secretKey: process.env.LANGFUSE_SECRET_KEY || '',
  publicKey: process.env.LANGFUSE_PUBLIC_KEY || '',
  baseUrl: process.env.LANGFUSE_BASE_URL || 'http://localhost:8080'
});

export interface AnalyzeOptions {
  githubUrl: string;
  currentVersion: string;
  githubToken?: string;
  anthropicApiKey: string;
}

export class BreakingChangesAnalyzer {
  private githubClient: GitHubClient;
  private anthropicClient?: AnthropicClient;

  constructor(githubToken?: string, anthropicApiKey?: string) {
    this.githubClient = new GitHubClient(githubToken);
    if (anthropicApiKey) {
      this.anthropicClient = new AnthropicClient(anthropicApiKey);
    }
  }

  async analyze(options: AnalyzeOptions): Promise<AnalysisResult> {
    return tracer.startActiveSpan('analyzer.analyze', async (span) => {
      // Create Langfuse trace (following official pattern)
      const traceId = uuidv4();
      const langfuseTrace = langfuse.trace({
        id: traceId,
        name: "github-release-analysis",
        metadata: {
          githubUrl: options.githubUrl,
          currentVersion: options.currentVersion
        }
      });

      try {
        span.setAttributes({
          'analyzer.githubUrl': options.githubUrl,
          'analyzer.currentVersion': options.currentVersion,
          'langfuse.trace.id': traceId
        });

        if (!this.anthropicClient) {
          this.anthropicClient = new AnthropicClient(options.anthropicApiKey);
        }

        const repository = GitHubClient.parseRepositoryUrl(options.githubUrl);
        span.setAttributes({
          'analyzer.owner': repository.owner,
          'analyzer.repo': repository.repo
        });

        const releases = await this.githubClient.getReleasesAfterVersion(
          repository.owner,
          repository.repo,
          options.currentVersion
        );

        if (releases.length === 0) {
          return {
            breakingChanges: [],
            summary: `No releases found after version ${options.currentVersion}`,
            riskLevel: 'low' as const,
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

        // Add metadata to Langfuse trace
        langfuseTrace.update({
          metadata: {
            releaseCount: releases.length,
            versions: releaseNotes.map(r => r.version)
          }
        });

        const analysis = await this.anthropicClient.analyzeReleaseNotes(releaseNotes, langfuseTrace);
        
        // Add score to trace
        langfuseTrace.score({
          name: 'breaking-changes-found',
          value: analysis.breakingChanges.length,
          comment: `Found ${analysis.breakingChanges.length} breaking changes with ${analysis.riskLevel} risk level`
        });

        span.setAttributes({
          'analyzer.result.breakingChanges': analysis.breakingChanges.length,
          'analyzer.result.riskLevel': analysis.riskLevel
        });

        return analysis;
      } catch (error) {
        span.recordException(error as Error);
        throw error;
      } finally {
        span.end();
      }
    });
  }

  async getAvailableReleases(githubUrl: string): Promise<Array<{ version: string; publishedAt: string; prerelease: boolean }>> {
    return tracer.startActiveSpan('analyzer.getAvailableReleases', async (span) => {
      try {
        const repository = GitHubClient.parseRepositoryUrl(githubUrl);
        const releases = await this.githubClient.getAllReleases(repository.owner, repository.repo);
        
        return releases
          .filter(release => !release.draft)
          .map(release => ({
            version: release.tag_name,
            publishedAt: release.published_at,
            prerelease: release.prerelease
          }))
          .sort((a, b) => new Date(b.publishedAt).getTime() - new Date(a.publishedAt).getTime());
      } catch (error) {
        span.recordException(error as Error);
        throw error;
      } finally {
        span.end();
      }
    });
  }
}