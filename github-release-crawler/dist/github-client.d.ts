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
export declare class GitHubClient {
    private client;
    constructor(token?: string);
    static parseRepositoryUrl(url: string): GitHubRepository;
    getAllReleases(owner: string, repo: string): Promise<GitHubRelease[]>;
    getReleasesAfterVersion(owner: string, repo: string, baseVersion: string): Promise<GitHubRelease[]>;
}
//# sourceMappingURL=github-client.d.ts.map