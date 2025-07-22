"use strict";
var __importDefault = (this && this.__importDefault) || function (mod) {
    return (mod && mod.__esModule) ? mod : { "default": mod };
};
Object.defineProperty(exports, "__esModule", { value: true });
exports.GitHubClient = void 0;
const axios_1 = __importDefault(require("axios"));
const api_1 = require("@opentelemetry/api");
const tracer = api_1.trace.getTracer('github-client');
class GitHubClient {
    constructor(token) {
        this.client = axios_1.default.create({
            baseURL: 'https://api.github.com',
            headers: {
                'Accept': 'application/vnd.github.v3+json',
                'User-Agent': 'github-release-crawler/1.0.0',
                ...(token && { 'Authorization': `token ${token}` })
            }
        });
    }
    static parseRepositoryUrl(url) {
        const match = url.match(/github\.com\/([^/]+)\/([^/]+)/);
        if (!match) {
            throw new Error(`Invalid GitHub repository URL: ${url}`);
        }
        return {
            owner: match[1],
            repo: match[2].replace(/\.git$/, '')
        };
    }
    async getAllReleases(owner, repo) {
        return tracer.startActiveSpan('github.getAllReleases', async (span) => {
            try {
                span.setAttributes({
                    'github.owner': owner,
                    'github.repo': repo
                });
                const releases = [];
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
                    const pageReleases = response.data;
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
    async getReleasesAfterVersion(owner, repo, baseVersion) {
        return tracer.startActiveSpan('github.getReleasesAfterVersion', async (span) => {
            try {
                span.setAttributes({
                    'github.owner': owner,
                    'github.repo': repo,
                    'github.baseVersion': baseVersion
                });
                const allReleases = await this.getAllReleases(owner, repo);
                const baseReleaseIndex = allReleases.findIndex(release => release.tag_name === baseVersion ||
                    release.tag_name === `v${baseVersion}`);
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
}
exports.GitHubClient = GitHubClient;
//# sourceMappingURL=github-client.js.map