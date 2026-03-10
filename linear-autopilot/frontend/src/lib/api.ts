async function apiFetch<T>(path: string, options: RequestInit = {}): Promise<T> {
	const res = await fetch(path, {
		...options,
		headers: {
			'Content-Type': 'application/json',
			...options.headers,
		},
		credentials: 'same-origin',
	});

	if (res.status === 401) {
		window.location.href = '/';
		throw new Error('Unauthorized');
	}

	if (!res.ok) {
		const body = await res.json().catch(() => ({}));
		throw new Error(body.detail || `Request failed: ${res.status}`);
	}

	return res.json();
}

export function getMe() {
	return apiFetch<{ id: string; email: string; name: string; avatar_url: string }>('/auth/me');
}

export function listProjects() {
	return apiFetch<Array<{
		id: string;
		name: string;
		github_connected: boolean;
		github_repo: string | null;
		linear_connected: boolean;
		autopilot_label: string;
		created_at: string;
	}>>('/api/v1/projects');
}

export function createProject(name: string) {
	return apiFetch<{ id: string; name: string; created_at: string }>('/api/v1/projects', {
		method: 'POST',
		body: JSON.stringify({ name }),
	});
}

export function getProject(id: string) {
	return apiFetch<{
		id: string;
		name: string;
		github_connected: boolean;
		github_repo: string | null;
		linear_connected: boolean;
		autopilot_label: string;
		created_at: string;
		jobs: Array<{
			id: string;
			linear_issue_id: string;
			linear_issue_title: string;
			status: string;
			pr_url: string | null;
			error: string | null;
			created_at: string;
			finished_at: string | null;
		}>;
	}>(`/api/v1/projects/${id}`);
}

export function updateProjectSettings(id: string, settings: { autopilot_label?: string }) {
	return apiFetch(`/api/v1/projects/${id}/settings`, {
		method: 'PATCH',
		body: JSON.stringify(settings),
	});
}

export function listGithubRepos(projectId: string) {
	return apiFetch<Array<{ full_name: string; private: boolean }>>(`/api/v1/projects/${projectId}/integrations/github/repos`);
}

export function listLinearTeams(projectId: string) {
	return apiFetch<Array<{ id: string; name: string; key: string }>>(`/api/v1/projects/${projectId}/integrations/linear/teams`);
}

export function setLinearTeam(projectId: string, teamId: string) {
	return apiFetch(`/api/v1/projects/${projectId}/integrations/linear/team`, {
		method: 'POST',
		body: JSON.stringify({ team_id: teamId }),
	});
}

export function getJob(projectId: string, jobId: string) {
	return apiFetch<{
		id: string;
		linear_issue_id: string;
		linear_issue_title: string;
		linear_issue_url: string | null;
		status: string;
		pr_url: string | null;
		error: string | null;
		sandbox_id: string | null;
		created_at: string;
		finished_at: string | null;
	}>(`/api/v1/projects/${projectId}/jobs/${jobId}`);
}

export function getJobLogs(projectId: string, jobId: string) {
	return apiFetch<{ logs: string[]; error?: string }>(`/api/v1/projects/${projectId}/jobs/${jobId}/logs`);
}

export function deleteProject(id: string) {
	return apiFetch<{ status: string }>(`/api/v1/projects/${id}`, {
		method: 'DELETE',
	});
}

export function deleteJob(projectId: string, jobId: string) {
	return apiFetch<{ status: string }>(`/api/v1/projects/${projectId}/jobs/${jobId}`, {
		method: 'DELETE',
	});
}

export function logout() {
	return apiFetch('/auth/logout', { method: 'POST' });
}
