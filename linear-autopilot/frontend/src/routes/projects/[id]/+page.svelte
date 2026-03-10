<script lang="ts">
	import { onMount } from 'svelte';
	import { page } from '$app/state';
	import { getProject } from '$lib/api';

	let project = $state<any>(null);

	onMount(async () => {
		project = await getProject(page.params.id);
	});

	function statusColor(status: string) {
		if (status === 'success') return 'text-success';
		if (status === 'running') return 'text-accent';
		if (status === 'launching') return 'text-accent';
		if (status === 'pending') return 'text-warm-500';
		return 'text-danger';
	}

	function dotColor(status: string) {
		if (status === 'success') return 'bg-success';
		if (status === 'running') return 'bg-accent';
		if (status === 'launching') return 'bg-accent';
		if (status === 'pending') return 'bg-warm-500';
		return 'bg-danger';
	}
</script>

{#if project}
<div class="min-h-screen">
	<header class="border-b border-warm-700/50 px-8 py-4">
		<div class="max-w-5xl mx-auto flex items-center justify-between">
			<a href="/" class="font-serif text-2xl text-cream hover:text-cream no-underline">Autopilot</a>
		</div>
	</header>

	<main class="max-w-5xl mx-auto px-8 py-12">
		<div class="mb-8">
			<a href="/projects" class="text-warm-500 text-sm hover:text-cream transition-colors duration-200 no-underline">&larr; Projects</a>
		</div>

		<div class="flex items-start justify-between mb-12">
			<h1 class="font-serif text-3xl tracking-tight">{project.name}</h1>
			<a
				href="/projects/{project.id}/settings"
				class="border border-warm-600 text-cream-dim px-4 py-2 text-sm hover:bg-surface-raised hover:border-warm-400 transition-all duration-200 no-underline"
			>
				Settings
			</a>
		</div>

		<div class="flex items-center gap-8 mb-12 pb-6 border-b border-warm-700/50">
			<div class="flex items-center gap-2 text-sm">
				<span class="w-2 h-2 rounded-full {project.github_connected ? 'bg-success' : 'bg-warm-600'}"></span>
				<span class="text-warm-500">GitHub:</span>
				<span class="text-cream-dim">{project.github_connected ? 'Connected' : 'Not configured'}</span>
			</div>
			<div class="flex items-center gap-2 text-sm">
				<span class="w-2 h-2 rounded-full {project.linear_has_token ? 'bg-success' : 'bg-warm-600'}"></span>
				<span class="text-warm-500">Linear:</span>
				<span class="text-cream-dim">{project.linear_connected ? 'Connected' : project.linear_has_token ? 'Token only — select team' : 'Not connected'}</span>
			</div>
			<div class="flex items-center gap-2 text-sm">
				<span class="text-warm-500">Label:</span>
				<span class="font-mono text-xs bg-surface-raised border border-warm-700 px-2 py-0.5 text-cream-dim">{project.autopilot_label}</span>
			</div>
		</div>

		<h2 class="text-xs text-warm-500 uppercase tracking-wider mb-4">Recent Jobs</h2>

		{#if project.jobs.length > 0}
			<div class="border border-warm-700/50">
				<div class="grid grid-cols-[1fr_auto_auto] gap-4 px-6 py-3 text-xs text-warm-500 uppercase tracking-wider border-b border-warm-700/30">
					<span>Issue</span>
					<span>Status</span>
					<span>Created</span>
				</div>
				{#each project.jobs as job}
					<a href="/projects/{project.id}/jobs/{job.id}" class="grid grid-cols-[1fr_auto_auto] gap-4 items-center px-6 py-4 border-t border-warm-700/30 first:border-t-0 hover:bg-surface-raised/50 transition-all duration-200 no-underline block">
						<div>
							<span class="text-sm text-cream">{job.linear_issue_title}</span>
							<span class="text-xs text-warm-500 ml-2 font-mono">{job.linear_issue_id}</span>
							{#if job.error}
								<p class="text-danger text-xs mt-1 truncate max-w-lg">{job.error}</p>
							{/if}
						</div>
						<span class="flex items-center gap-1.5 {statusColor(job.status)}">
							<span class="w-1.5 h-1.5 rounded-full {dotColor(job.status)}"></span>
							<span class="text-xs">{job.status}</span>
						</span>
						<span class="text-xs text-warm-500 font-mono">{new Date(job.created_at).toLocaleDateString()}</span>
					</a>
				{/each}
			</div>
		{:else}
			<div class="border border-warm-700/50 px-6 py-12 text-center">
				<p class="text-warm-500 text-sm">No jobs yet. Tag a Linear issue with "{project.autopilot_label}" to get started.</p>
			</div>
		{/if}
	</main>
</div>
{/if}
