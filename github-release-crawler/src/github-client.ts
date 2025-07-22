import axios, { AxiosInstance } from 'axios';
import { trace } from '@opentelemetry/api';

const tracer = trace.getTracer(process.env.OTEL_SERVICE_NAME || 'porter');

export interface GitHubRelease {
  id: number;
  tag_name: string;
  name: string | null;
  body: string | null;
  published_at: string;
  prerelease: boolean;
  draft: boolean;
  html_url: string;
}

export interface GitHubRepository {
  owner: string;
  repo: string;
}

export class GitHubClient {
  private client: AxiosInstance;

  constructor(token?: string) {
    this.client = axios.create({
      baseURL: 'https://api.github.com',
      headers: {
        'Accept': 'application/vnd.github.v3+json',
        'User-Agent': 'github-release-crawler/1.0.0',
        ...(token && { 'Authorization': `token ${token}` })
      }
    });
  }

  static parseRepositoryUrl(url: string): GitHubRepository {
    const match = url.match(/github\.com\/([^/]+)\/([^/]+)/);
    if (!match) {
      throw new Error(`Invalid GitHub repository URL: ${url}`);
    }
    return {
      owner: match[1],
      repo: match[2].replace(/\.git$/, '')
    };
  }

  async getAllReleases(owner: string, repo: string): Promise<GitHubRelease[]> {
    return tracer.startActiveSpan('github.getAllReleases', async (span) => {
      try {
        span.setAttributes({
          'github.owner': owner,
          'github.repo': repo
        });

        const releases: GitHubRelease[] = [];
        let page = 1;
        const perPage = 100;

        // eslint-disable-next-line no-constant-condition
        while (true) {
          const response = await this.client.get(`/repos/${owner}/${repo}/releases`, {
            params: {
              page,
              per_page: perPage
            }
          });

          const pageReleases = response.data as GitHubRelease[];
          releases.push(...pageReleases);

          if (pageReleases.length < perPage) {
            break;
          }
          page++;
        }

        span.setAttributes({
          'github.releases.count': releases.length
        });

        return releases;
      } catch (error) {
        span.recordException(error as Error);
        throw error;
      } finally {
        span.end();
      }
    });
  }

  async getReleasesAfterVersion(owner: string, repo: string, baseVersion: string): Promise<GitHubRelease[]> {
    return tracer.startActiveSpan('github.getReleasesAfterVersion', async (span) => {
      try {
        span.setAttributes({
          'github.owner': owner,
          'github.repo': repo,
          'github.baseVersion': baseVersion
        });

        const allReleases = await this.getAllReleases(owner, repo);
        
        const baseReleaseIndex = allReleases.findIndex(release => 
          release.tag_name === baseVersion || 
          release.tag_name === `v${baseVersion}`
        );

        if (baseReleaseIndex === -1) {
          throw new Error(`Base version ${baseVersion} not found in releases`);
        }

        const releasesAfter = allReleases
          .slice(0, baseReleaseIndex)
          .filter(release => !release.draft && !release.prerelease)
          .sort((a, b) => new Date(a.published_at).getTime() - new Date(b.published_at).getTime());

        span.setAttributes({
          'github.releases.after.count': releasesAfter.length
        });

        return releasesAfter;
      } catch (error) {
        span.recordException(error as Error);
        throw error;
      } finally {
        span.end();
      }
    });
  }
}