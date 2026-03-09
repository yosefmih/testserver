<script lang="ts">
	import { onMount } from 'svelte';
	import { page } from '$app/state';
	import { getProject } from '$lib/api';

	let project = $state<any>(null);

	onMount(async () => {
		project = await getProject(page.params.id);
	});

	function badgeClass(status: string) {
		if (status === 'success') return 'badge-success';
		if (status === 'running') return 'badge-running';
		if (status === 'pending') return 'badge-pending';
		return 'badge-failed';
	}
</script>

{#if project}
<div class="container">
	<div class="header">
		<div>
			<a href="/projects" style="color: #666; font-size: 0.875rem;">&larr; Projects</a>
			<h1 style="margin-top: 0.25rem;">{project.name}</h1>
		</div>
		<a href="/projects/{project.id}/settings" class="btn btn-secondary">Settings</a>
	</div>

	<div class="card" style="display: flex; gap: 1.5rem;">
		<div>
			<span class="status-dot" class:connected={project.github_connected} class:disconnected={!project.github_connected}></span>
			GitHub: {project.github_repo || 'Not configured'}
		</div>
		<div>
			<span class="status-dot" class:connected={project.linear_connected} class:disconnected={!project.linear_connected}></span>
			Linear: {project.linear_connected ? 'Connected' : 'Not connected'}
		</div>
		<div>
			Label: <code style="background: #2a2a2a; padding: 0.1rem 0.4rem; border-radius: 3px;">{project.autopilot_label}</code>
		</div>
	</div>

	<h2 style="font-size: 1rem; margin-bottom: 0.75rem;">Recent Jobs</h2>

	{#each project.jobs as job}
		<div class="card">
			<div style="display: flex; justify-content: space-between; align-items: center;">
				<div>
					<strong>{job.linear_issue_title}</strong>
					<span style="color: #666; font-size: 0.875rem; margin-left: 0.5rem;">{job.linear_issue_id}</span>
				</div>
				<span class="badge {badgeClass(job.status)}">{job.status}</span>
			</div>
			{#if job.pr_url}
				<a href={job.pr_url} target="_blank" style="font-size: 0.875rem; margin-top: 0.25rem; display: block;">
					View PR &rarr;
				</a>
			{/if}
			{#if job.error}
				<p style="color: #f87171; font-size: 0.875rem; margin-top: 0.25rem;">{job.error}</p>
			{/if}
			<p style="color: #666; font-size: 0.75rem; margin-top: 0.25rem;">
				{new Date(job.created_at).toLocaleString()}
			</p>
		</div>
	{/each}

	{#if project.jobs.length === 0}
		<div class="card" style="text-align: center; color: #666;">
			No jobs yet. Tag a Linear issue with "{project.autopilot_label}" to get started.
		</div>
	{/if}
</div>
{/if}
