<script lang="ts">
	import { onMount } from 'svelte';
	import { page } from '$app/state';
	import { goto } from '$app/navigation';
	import { getProject, createTicket } from '$lib/api';

	let project = $state<any>(null);

	let title = $state('');
	let description = $state('');
	let launching = $state(false);
	let launchError = $state('');

	let canLaunch = $derived(!!project && project.github_connected && project.claude_connected);

	onMount(async () => {
		project = await getProject(page.params.id);
	});

	async function launchRun() {
		if (!title.trim() || launching) return;
		launching = true;
		launchError = '';
		try {
			const { id } = await createTicket(page.params.id, { title: title.trim(), description });
			await goto(`/projects/${page.params.id}/tickets/${id}`);
		} catch (e: any) {
			launchError = e.message;
			launching = false;
		}
	}

	function statusColor(status: string) {
		if (status === 'active') return 'text-accent';
		if (status === 'merged') return 'text-success';
		if (status === 'closed') return 'text-warm-500';
		if (status === 'failed') return 'text-danger';
		if (status === 'cancelled') return 'text-danger';
		return 'text-warm-500';
	}

	function dotColor(status: string) {
		if (status === 'active') return 'bg-accent';
		if (status === 'merged') return 'bg-success';
		if (status === 'closed') return 'bg-warm-500';
		if (status === 'failed') return 'bg-danger';
		if (status === 'cancelled') return 'bg-danger';
		return 'bg-warm-500';
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
			<div class="flex items-center gap-3">
				<a
					href="/projects/{project.id}/members"
					class="border border-warm-600 text-cream-dim px-4 py-2 text-sm hover:bg-surface-raised hover:border-warm-400 transition-all duration-200 no-underline"
				>
					Members
				</a>
				<a
					href="/projects/{project.id}/settings"
					class="border border-warm-600 text-cream-dim px-4 py-2 text-sm hover:bg-surface-raised hover:border-warm-400 transition-all duration-200 no-underline"
				>
					Settings
				</a>
			</div>
		</div>

		<div class="flex items-center gap-8 mb-12 pb-6 border-b border-warm-700/50">
			<div class="flex items-center gap-2 text-sm">
				<span class="w-2 h-2 rounded-full {project.github_connected ? 'bg-success' : 'bg-warm-600'}"></span>
				<span class="text-warm-500">GitHub:</span>
				<span class="text-cream-dim">{project.github_connected ? 'Connected' : 'Not configured'}</span>
			</div>
			<div class="flex items-center gap-2 text-sm">
				<span class="w-2 h-2 rounded-full {project.linear_connected ? 'bg-success' : 'bg-warm-600'}"></span>
				<span class="text-warm-500">Linear:</span>
				<span class="text-cream-dim">{project.linear_connected ? 'Connected' : 'Not connected'}</span>
			</div>
			<div class="flex items-center gap-2 text-sm">
				<span class="text-warm-500">Label:</span>
				<span class="font-mono text-xs bg-surface-raised border border-warm-700 px-2 py-0.5 text-cream-dim">{project.autopilot_label}</span>
			</div>
		</div>

		<section class="mb-12">
			<h2 class="text-xs text-warm-500 uppercase tracking-wider mb-4">Launch a run</h2>
			<div class="border border-warm-700/50 p-5 space-y-3">
				<input
					bind:value={title}
					placeholder="Issue title"
					disabled={!canLaunch}
					class="w-full bg-transparent border border-warm-600 px-4 py-2.5 text-sm text-cream focus:outline-none focus:border-accent transition-colors duration-200 disabled:opacity-50"
				/>
				<textarea
					bind:value={description}
					placeholder="Describe what you want Claude to do — the issue, repo hints, acceptance criteria…"
					rows="5"
					disabled={!canLaunch}
					class="w-full bg-transparent border border-warm-600 px-4 py-2.5 text-sm text-cream focus:outline-none focus:border-accent transition-colors duration-200 resize-y disabled:opacity-50"
				></textarea>
				{#if launchError}
					<p class="text-danger text-sm">{launchError}</p>
				{/if}
				<div class="flex items-center justify-between gap-4">
					<p class="text-warm-500 text-xs">
						{#if canLaunch}
							Spins up a sandbox against this project's connected GitHub repos. No Linear issue required.
						{:else}
							Connect GitHub and Claude in <a href="/projects/{project.id}/settings" class="text-cream-dim hover:text-cream underline">Settings</a> to launch a run.
						{/if}
					</p>
					<button
						onclick={launchRun}
						disabled={launching || !title.trim() || !canLaunch}
						class="bg-accent/10 border border-accent text-accent px-5 py-2.5 text-sm hover:bg-accent/20 transition-all duration-200 disabled:opacity-50 whitespace-nowrap"
					>
						{launching ? 'Launching…' : 'Launch run'}
					</button>
				</div>
			</div>
		</section>

		<h2 class="text-xs text-warm-500 uppercase tracking-wider mb-4">Tickets</h2>

		{#if project.tickets.length > 0}
			<div class="space-y-1">
				{#each project.tickets as ticket}
					<a href="/projects/{project.id}/tickets/{ticket.linear_issue_identifier || ticket.id}" class="flex items-center justify-between px-5 py-3 border border-warm-700/50 hover:bg-surface-raised/50 transition-all duration-200 no-underline group">
						<div class="flex items-center gap-4">
							<span class="flex items-center gap-1.5 {statusColor(ticket.status)}">
								<span class="w-1.5 h-1.5 rounded-full {dotColor(ticket.status)}"></span>
							</span>
							<span class="font-mono text-xs text-warm-500">{ticket.linear_issue_identifier || '—'}</span>
							<span class="text-sm text-cream truncate max-w-[300px]">{ticket.linear_issue_title}</span>
							{#if ticket.pr_url}
								<span class="text-[10px] font-mono uppercase tracking-wider text-accent/80 bg-accent/10 px-1.5 py-0.5">PR</span>
							{/if}
						</div>
						<div class="flex items-center gap-4 text-xs text-warm-500">
							<span class={statusColor(ticket.status)}>{ticket.status}</span>
							<span class="font-mono">{new Date(ticket.created_at).toLocaleDateString()}</span>
						</div>
					</a>
				{/each}
			</div>
		{:else}
			<div class="border border-warm-700/50 px-6 py-12 text-center">
				<p class="text-warm-500 text-sm">No tickets yet. Launch a run above, or tag a Linear issue with "{project.autopilot_label}".</p>
			</div>
		{/if}
	</main>
</div>
{/if}
