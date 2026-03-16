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
		if (window.location.pathname !== '/') {
			window.location.href = '/';
		}
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
	linear_issue_identifier: string | null;
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
		role: string;
		tickets: Ticket[];
	}>(`/api/v1/projects/${id}`);
}

export function updateProjectSettings(id: string, settings: {
	autopilot_label?: string;
	custom_tools?: string;
	system_prompt?: string;
	anthropic_api_key?: string;
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
		linear_issue_identifier: string | null;
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

export function logout() {
	return apiFetch('/auth/logout', { method: 'POST' });
}

// --- Members ---

export type Member = {
	id: string;
	user_id: string;
	email: string;
	name: string;
	avatar_url: string | null;
	role: string;
	created_at: string;
};

export function listMembers(projectId: string) {
	return apiFetch<Member[]>(`/api/v1/projects/${projectId}/members`);
}

export function addMember(projectId: string, email: string, role: string = 'developer') {
	return apiFetch<Member & { status?: string; invite_url?: string; expires_at?: string }>(`/api/v1/projects/${projectId}/members`, {
		method: 'POST',
		body: JSON.stringify({ email, role }),
	});
}

export function updateMemberRole(projectId: string, memberId: string, role: string) {
	return apiFetch<{ status: string }>(`/api/v1/projects/${projectId}/members/${memberId}`, {
		method: 'PATCH',
		body: JSON.stringify({ role }),
	});
}

export function removeMember(projectId: string, memberId: string) {
	return apiFetch<{ status: string }>(`/api/v1/projects/${projectId}/members/${memberId}`, {
		method: 'DELETE',
	});
}

// --- Invites ---

export type Invite = {
	id: string;
	email: string;
	role: string;
	invited_by: string;
	created_at: string;
	expires_at: string;
	invite_url: string;
};

export function listInvites(projectId: string) {
	return apiFetch<Invite[]>(`/api/v1/projects/${projectId}/invites`);
}

export function revokeInvite(projectId: string, inviteId: string) {
	return apiFetch<{ status: string }>(`/api/v1/projects/${projectId}/invites/${inviteId}`, {
		method: 'DELETE',
	});
}

export function getInvite(token: string) {
	return apiFetch<{
		status: string;
		email?: string;
		role?: string;
		project_id?: string;
		project_name?: string;
	}>(`/api/v1/invites/${token}`);
}

export function acceptInvite(token: string) {
	return apiFetch<{ status: string; project_id?: string }>(`/api/v1/invites/${token}/accept`, {
		method: 'POST',
	});
}
