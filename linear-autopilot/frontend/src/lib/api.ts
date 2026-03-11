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

export type Ticket = {
	id: string;
	linear_issue_id: string;
	linear_issue_title: string;
	linear_issue_url: string | null;
	pr_url: string | null;
	status: string;
	created_at: string;
	updated_at: string;
};

export type Run = {
	id: string;
	kind: string;
	sandbox_id: string | null;
	status: string;
	error: string | null;
	created_at: string;
	finished_at: string | null;
};

export function getProject(id: string) {
	return apiFetch<{
		id: string;
		name: string;
		github_connected: boolean;
		linear_connected: boolean;
		claude_connected: boolean;
		autopilot_label: string;
		custom_tools: string;
		system_prompt: string;
		created_at: string;
		tickets: Ticket[];
	}>(`/api/v1/projects/${id}`);
}

export function updateProjectSettings(id: string, settings: {
	autopilot_label?: string;
	custom_tools?: string;
	system_prompt?: string;
}) {
	return apiFetch(`/api/v1/projects/${id}/settings`, {
		method: 'PATCH',
		body: JSON.stringify(settings),
	});
}

export function listGithubRepos(projectId: string) {
	return apiFetch<Array<{ full_name: string; private: boolean }>>(`/api/v1/projects/${projectId}/integrations/github/repos`);
}

export function getTicket(projectId: string, ticketId: string) {
	return apiFetch<{
		id: string;
		linear_issue_id: string;
		linear_issue_title: string;
		linear_issue_url: string | null;
		pr_repo: string | null;
		pr_number: number | null;
		pr_url: string | null;
		volume_id: string | null;
		status: string;
		created_at: string;
		updated_at: string;
		runs: Run[];
	}>(`/api/v1/projects/${projectId}/tickets/${ticketId}`);
}

export function triggerReviewNow(projectId: string, ticketId: string) {
	return apiFetch<{ status: string }>(`/api/v1/projects/${projectId}/tickets/${ticketId}/trigger-review`, {
		method: 'POST',
	});
}

export function cancelTicket(projectId: string, ticketId: string) {
	return apiFetch<{ status: string }>(`/api/v1/projects/${projectId}/tickets/${ticketId}`, {
		method: 'DELETE',
	});
}

export function getRunLogs(projectId: string, ticketId: string, runId: string) {
	return apiFetch<{ logs: string[]; error?: string }>(`/api/v1/projects/${projectId}/tickets/${ticketId}/runs/${runId}/logs`);
}

export function deleteProject(id: string) {
	return apiFetch<{ status: string }>(`/api/v1/projects/${id}`, {
		method: 'DELETE',
	});
}

export function disconnectGithub(projectId: string) {
	return apiFetch<{ status: string }>(`/api/v1/projects/${projectId}/integrations/github`, {
		method: 'DELETE',
	});
}

export function disconnectLinear(projectId: string) {
	return apiFetch<{ status: string }>(`/api/v1/projects/${projectId}/integrations/linear`, {
		method: 'DELETE',
	});
}

export function disconnectClaude(projectId: string) {
	return apiFetch<{ status: string }>(`/api/v1/projects/${projectId}/integrations/claude`, {
		method: 'DELETE',
	});
}

export function logout() {
	return apiFetch('/auth/logout', { method: 'POST' });
}
