<script lang="ts">
	import { onMount } from 'svelte';
	import { page } from '$app/state';
	import { getJob, getJobLogs, deleteJob } from '$lib/api';

	let job = $state<any>(null);
	let logs = $state<string[]>([]);
	let logsError = $state('');
	let loadingLogs = $state(false);
	let autoRefresh = $state<ReturnType<typeof setInterval> | null>(null);
	let deleting = $state(false);

	const projectId = page.params.id;
	const jobId = page.params.jobId;

	onMount(() => {
		loadJob();
		return () => {
			if (autoRefresh) clearInterval(autoRefresh);
		};
	});

	async function loadJob() {
		job = await getJob(projectId, jobId);
		await loadLogs();

		if (job.status === 'pending' || job.status === 'running') {
			autoRefresh = setInterval(async () => {
				job = await getJob(projectId, jobId);
				await loadLogs();
				if (job.status !== 'pending' && job.status !== 'running') {
					if (autoRefresh) clearInterval(autoRefresh);
				}
			}, 5000);
		}
	}

	async function loadLogs() {
		loadingLogs = true;
		try {
			const result = await getJobLogs(projectId, jobId);
			logs = result.logs;
			logsError = result.error || '';
		} catch (e: any) {
			logsError = e.message;
		}
		loadingLogs = false;
	}

	function statusColor(status: string) {
		if (status === 'success') return 'text-success';
		if (status === 'running') return 'text-accent';
		if (status === 'pending') return 'text-warm-500';
		return 'text-danger';
	}

	function dotColor(status: string) {
		if (status === 'success') return 'bg-success';
		if (status === 'running') return 'bg-accent';
		if (status === 'pending') return 'bg-warm-500';
		return 'bg-danger';
	}

	async function forceClose() {
		if (!confirm('Are you sure you want to force close this job? The sandbox will be deleted.')) return;
		deleting = true;
		try {
			await deleteJob(projectId, jobId);
			if (autoRefresh) clearInterval(autoRefresh);
			job = await getJob(projectId, jobId);
		} catch (e: any) {
			alert(`Failed to force close job: ${e.message}`);
		} finally {
			deleting = false;
		}
	}
</script>

{#if job}
<div class="min-h-screen">
	<header class="border-b border-warm-700/50 px-8 py-4">
		<div class="max-w-5xl mx-auto flex items-center justify-between">
			<a href="/" class="font-serif text-2xl text-cream hover:text-cream no-underline">Autopilot</a>
		</div>
	</header>

	<main class="max-w-5xl mx-auto px-8 py-12">
		<div class="mb-8">
			<a href="/projects/{projectId}" class="text-warm-500 text-sm hover:text-cream transition-colors duration-200 no-underline">&larr; Back to project</a>
		</div>

		<div class="flex items-start justify-between mb-8">
			<div>
				<h1 class="font-serif text-2xl tracking-tight mb-2">{job.linear_issue_title}</h1>
				<div class="flex items-center gap-4 text-sm">
					<span class="font-mono text-warm-500">{job.linear_issue_id}</span>
					<span class="flex items-center gap-1.5 {statusColor(job.status)}">
						<span class="w-1.5 h-1.5 rounded-full {dotColor(job.status)}"></span>
						{job.status}
						{#if job.status === 'running'}
							<span class="animate-pulse">&hellip;</span>
						{/if}
					</span>
				</div>
			</div>
			<div class="flex gap-3">
				{#if job.linear_issue_url}
					<a href={job.linear_issue_url} target="_blank" class="border border-warm-600 text-cream-dim px-4 py-2 text-sm hover:bg-surface-raised hover:border-warm-400 transition-all duration-200 no-underline">Linear Issue &rarr;</a>
				{/if}
				{#if job.pr_url}
					<a href={job.pr_url} target="_blank" class="bg-accent/10 border border-accent text-accent px-4 py-2 text-sm hover:bg-accent/20 transition-all duration-200 no-underline">View PR &rarr;</a>
				{/if}
				{#if job.status === 'pending' || job.status === 'running'}
					<button
						onclick={forceClose}
						disabled={deleting}
						class="border border-danger/60 text-danger px-4 py-2 text-sm hover:bg-danger/10 hover:border-danger transition-all duration-200 disabled:opacity-50 disabled:cursor-not-allowed"
					>
						{deleting ? 'Closing...' : 'Force Close'}
					</button>
				{/if}
			</div>
		</div>

		<div class="flex items-center gap-6 mb-8 pb-6 border-b border-warm-700/50 text-xs text-warm-500">
			<span>Created: <span class="text-cream-dim font-mono">{new Date(job.created_at).toLocaleString()}</span></span>
			{#if job.finished_at}
				<span>Finished: <span class="text-cream-dim font-mono">{new Date(job.finished_at).toLocaleString()}</span></span>
			{/if}
			{#if job.sandbox_id}
				<span>Sandbox: <span class="text-cream-dim font-mono">{job.sandbox_id}</span></span>
			{/if}
		</div>

		{#if job.error}
			<section class="mb-8">
				<h2 class="text-xs text-danger uppercase tracking-wider mb-3">Error</h2>
				<div class="border border-danger/30 bg-danger/5 px-5 py-4">
					<pre class="text-sm text-danger whitespace-pre-wrap font-mono">{job.error}</pre>
				</div>
			</section>
		{/if}

		<section>
			<div class="flex items-center justify-between mb-3">
				<h2 class="text-xs text-warm-500 uppercase tracking-wider">Sandbox Logs</h2>
				<button
					class="text-xs text-warm-500 hover:text-cream transition-colors duration-200"
					onclick={loadLogs}
					disabled={loadingLogs}
				>
					{loadingLogs ? 'Loading...' : 'Refresh'}
				</button>
			</div>

			{#if logsError}
				<div class="border border-warm-700/50 px-5 py-4 mb-4">
					<p class="text-warm-500 text-sm">{logsError}</p>
				</div>
			{/if}

			<div class="border border-warm-700/50 bg-surface-base overflow-hidden">
				{#if logs.length > 0}
					<div class="overflow-x-auto max-h-[70vh] overflow-y-auto">
						<pre class="px-5 py-4 text-xs font-mono text-cream-dim leading-relaxed">{logs.join('\n')}</pre>
					</div>
				{:else if !logsError}
					<div class="px-5 py-12 text-center">
						<p class="text-warm-500 text-sm">
							{#if job.status === 'pending'}
								Waiting for sandbox to start...
							{:else if job.status === 'running'}
								Sandbox is running, logs will appear shortly...
							{:else}
								No logs available.
							{/if}
						</p>
					</div>
				{/if}
			</div>
		</section>
	</main>
</div>
{/if}
