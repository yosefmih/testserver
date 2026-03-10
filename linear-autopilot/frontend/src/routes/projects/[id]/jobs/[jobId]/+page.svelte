<script lang="ts">
	import { onMount } from 'svelte';
	import { page } from '$app/state';
	import { getJob, getJobLogs, deleteJob } from '$lib/api';

	type LogEntry =
		| { kind: 'text'; text: string }
		| { kind: 'tool_use'; tool: string; input: string }
		| { kind: 'tool_result'; content: string }
		| { kind: 'system'; text: string }
		| { kind: 'result'; cost: string; duration: string; error: boolean; message: string }
		| { kind: 'error'; text: string; code: string }
		| { kind: 'raw'; text: string };

	let job = $state<any>(null);
	let logs = $state<string[]>([]);
	let entries = $derived(parseLogs(logs));
	let logsError = $state('');
	let loadingLogs = $state(false);
	let autoRefresh = $state<ReturnType<typeof setInterval> | null>(null);
	let deleting = $state(false);
	let showRaw = $state(false);

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

		if (ACTIVE_STATUSES.includes(job.status)) {
			autoRefresh = setInterval(async () => {
				job = await getJob(projectId, jobId);
				await loadLogs();
				if (!ACTIVE_STATUSES.includes(job.status)) {
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

	function parseLogs(lines: string[]): LogEntry[] {
		const result: LogEntry[] = [];
		for (const line of lines) {
			const trimmed = line.trim();
			if (!trimmed) continue;

			let parsed: any;
			try {
				parsed = JSON.parse(trimmed);
			} catch {
				result.push({ kind: 'raw', text: trimmed });
				continue;
			}

			if (parsed.type === 'assistant') {
				if (parsed.error) {
					const text = parsed.message?.content?.[0]?.text || parsed.error;
					result.push({ kind: 'error', text, code: parsed.error });
				} else {
					const content = parsed.message?.content;
					if (Array.isArray(content)) {
						for (const block of content) {
							if (block.type === 'text' && block.text) {
								result.push({ kind: 'text', text: block.text });
							} else if (block.type === 'tool_use') {
								const input = typeof block.input === 'string'
									? block.input
									: JSON.stringify(block.input, null, 2);
								result.push({ kind: 'tool_use', tool: block.name, input });
							}
						}
					}
				}
			} else if (parsed.type === 'tool_use' || parsed.type === 'content_block_start') {
				const tool = parsed.tool || parsed.content_block;
				if (tool?.type === 'tool_use') {
					const input = typeof tool.input === 'string'
						? tool.input
						: JSON.stringify(tool.input, null, 2);
					result.push({ kind: 'tool_use', tool: tool.name, input });
				}
			} else if (parsed.type === 'tool_result') {
				const content = typeof parsed.tool_result?.content === 'string'
					? parsed.tool_result.content
					: JSON.stringify(parsed.tool_result?.content, null, 2);
				if (content && content !== '{}' && content !== 'null') {
					result.push({ kind: 'tool_result', content });
				}
			} else if (parsed.type === 'system' || parsed.type === 'init') {
				const text = parsed.message || parsed.session_id
					? `Session: ${parsed.session_id || 'unknown'}`
					: JSON.stringify(parsed);
				result.push({ kind: 'system', text });
			} else if (parsed.type === 'result') {
				const cost = parsed.total_cost_usd != null ? `$${parsed.total_cost_usd.toFixed(4)}` : '';
				const duration = parsed.duration_ms != null ? `${(parsed.duration_ms / 1000).toFixed(1)}s` : '';
				const isError = parsed.is_error === true;
				const message = parsed.result || '';
				result.push({ kind: 'result', cost, duration, error: isError, message });
			} else {
				result.push({ kind: 'raw', text: trimmed });
			}
		}
		return result;
	}

	const ACTIVE_STATUSES = ['pending', 'launching', 'running'];

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
						{#if job.status === 'running' || job.status === 'launching'}
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
				{#if ACTIVE_STATUSES.includes(job.status)}
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
				<div class="flex items-center gap-4">
					<button
						class="text-xs transition-colors duration-200 {showRaw ? 'text-cream' : 'text-warm-500 hover:text-cream'}"
						onclick={() => showRaw = !showRaw}
					>
						{showRaw ? 'Parsed' : 'Raw'}
					</button>
					<button
						class="text-xs text-warm-500 hover:text-cream transition-colors duration-200"
						onclick={loadLogs}
						disabled={loadingLogs}
					>
						{loadingLogs ? 'Loading...' : 'Refresh'}
					</button>
				</div>
			</div>

			{#if logsError}
				<div class="border border-warm-700/50 px-5 py-4 mb-4">
					<p class="text-warm-500 text-sm">{logsError}</p>
				</div>
			{/if}

			<div class="border border-warm-700/50 bg-surface-base overflow-hidden">
				{#if logs.length > 0}
					{#if showRaw}
						<div class="overflow-x-auto max-h-[70vh] overflow-y-auto">
							<pre class="px-5 py-4 text-xs font-mono text-cream-dim leading-relaxed">{logs.join('\n')}</pre>
						</div>
					{:else}
						<div class="max-h-[70vh] overflow-y-auto divide-y divide-warm-700/30">
							{#each entries as entry}
								{#if entry.kind === 'text'}
									<div class="px-5 py-3">
										<pre class="text-sm text-cream whitespace-pre-wrap font-sans leading-relaxed">{entry.text}</pre>
									</div>
								{:else if entry.kind === 'tool_use'}
									<div class="px-5 py-3 bg-warm-900/20">
										<div class="flex items-center gap-2 mb-1.5">
											<span class="text-[10px] font-mono uppercase tracking-wider text-accent/80 bg-accent/10 px-1.5 py-0.5">tool</span>
											<span class="text-xs font-mono text-accent">{entry.tool}</span>
										</div>
										{#if entry.input && entry.input !== '{}'}
											<pre class="text-xs font-mono text-warm-400 whitespace-pre-wrap overflow-x-auto max-h-48 overflow-y-auto">{entry.input}</pre>
										{/if}
									</div>
								{:else if entry.kind === 'tool_result'}
									<div class="px-5 py-3 bg-warm-900/10">
										<span class="text-[10px] font-mono uppercase tracking-wider text-warm-500 mb-1.5 block">result</span>
										<pre class="text-xs font-mono text-warm-400 whitespace-pre-wrap overflow-x-auto max-h-48 overflow-y-auto">{entry.content}</pre>
									</div>
								{:else if entry.kind === 'system'}
									<div class="px-5 py-2">
										<span class="text-xs font-mono text-warm-600">{entry.text}</span>
									</div>
								{:else if entry.kind === 'error'}
									<div class="px-5 py-3 bg-danger/10 border-t border-danger/30">
										<div class="flex items-center gap-2 mb-1.5">
											<span class="text-[10px] font-mono uppercase tracking-wider text-danger/80 bg-danger/10 px-1.5 py-0.5">error</span>
											<span class="text-xs font-mono text-danger/70">{entry.code}</span>
										</div>
										<pre class="text-sm font-mono text-danger whitespace-pre-wrap">{entry.text}</pre>
									</div>
								{:else if entry.kind === 'result'}
									<div class="px-5 py-3 {entry.error ? 'bg-danger/5 border-t border-danger/20' : 'bg-success/5 border-t border-success/20'}">
										<div class="flex items-center gap-4 text-xs">
											<span class="text-[10px] font-mono uppercase tracking-wider {entry.error ? 'text-danger/80' : 'text-success/80'}">{entry.error ? 'failed' : 'completed'}</span>
											{#if entry.duration}
												<span class="font-mono text-warm-400">{entry.duration}</span>
											{/if}
											{#if entry.cost}
												<span class="font-mono text-warm-400">{entry.cost}</span>
											{/if}
										</div>
										{#if entry.message}
											<pre class="text-xs font-mono {entry.error ? 'text-danger' : 'text-warm-400'} whitespace-pre-wrap mt-1.5">{entry.message}</pre>
										{/if}
									</div>
								{:else}
									<div class="px-5 py-2">
										<pre class="text-xs font-mono text-warm-500 whitespace-pre-wrap">{entry.text}</pre>
									</div>
								{/if}
							{/each}
						</div>
					{/if}
				{:else if !logsError}
					<div class="px-5 py-12 text-center">
						<p class="text-warm-500 text-sm">
							{#if job.status === 'pending'}
								Queued, waiting for next sync cycle...
							{:else if job.status === 'launching'}
								Launching sandbox...
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
