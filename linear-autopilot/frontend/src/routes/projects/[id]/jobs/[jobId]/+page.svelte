<script lang="ts">
	import { onMount } from 'svelte';
	import { page } from '$app/state';
	import { getJob, getJobLogs, deleteJob } from '$lib/api';

	type LogEntry =
		| { kind: 'text'; text: string }
		| { kind: 'bash'; command: string; description: string }
		| { kind: 'tool_use'; tool: string; input: string }
		| { kind: 'tool_result'; content: string }
		| { kind: 'system'; text: string }
		| { kind: 'result'; cost: string; duration: string; turns: number; error: boolean; message: string }
		| { kind: 'error'; text: string; code: string }
		| { kind: 'raw'; text: string };

	const NOISE_TOOLS = new Set(['TodoWrite', 'TodoRead']);

	let job = $state<any>(null);
	let logs = $state<string[]>([]);
	let entries = $derived(parseLogs(logs));
	let logsError = $state('');
	let loadingLogs = $state(false);
	let autoRefresh = $state<ReturnType<typeof setInterval> | null>(null);
	let deleting = $state(false);
	let showRaw = $state(false);
	let expandedEntries = $state<Set<number>>(new Set());

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

	function toggleExpand(idx: number) {
		const next = new Set(expandedEntries);
		if (next.has(idx)) next.delete(idx);
		else next.add(idx);
		expandedEntries = next;
	}

	function parseToolUse(block: any): LogEntry | null {
		const name = block.name || block.tool?.name;
		const rawInput = block.input || block.tool?.input;
		if (!name || NOISE_TOOLS.has(name)) return null;

		if (name === 'Bash') {
			const input = typeof rawInput === 'string' ? JSON.parse(rawInput || '{}') : rawInput || {};
			return { kind: 'bash', command: input.command || '', description: input.description || '' };
		}

		const input = typeof rawInput === 'string' ? rawInput : JSON.stringify(rawInput, null, 2);
		return { kind: 'tool_use', tool: name, input };
	}

	function parseLogs(lines: string[]): LogEntry[] {
		const result: LogEntry[] = [];
		const seenToolIds = new Set<string>();

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
					continue;
				}

				const content = parsed.message?.content;
				if (!Array.isArray(content)) continue;

				for (const block of content) {
					if (block.type === 'text' && block.text) {
						result.push({ kind: 'text', text: block.text });
					} else if (block.type === 'tool_use') {
						if (block.id) seenToolIds.add(block.id);
						const entry = parseToolUse(block);
						if (entry) result.push(entry);
					}
				}
			} else if (parsed.type === 'user') {
				// Tool result echoes — skip entirely. The tool_use already shows what happened.
				continue;
			} else if (parsed.type === 'tool_use' || parsed.type === 'content_block_start') {
				const tool = parsed.tool || parsed.content_block;
				if (tool?.id && seenToolIds.has(tool.id)) continue;
				if (tool?.id) seenToolIds.add(tool.id);
				if (tool?.type === 'tool_use') {
					const entry = parseToolUse(tool);
					if (entry) result.push(entry);
				}
			} else if (parsed.type === 'tool_result') {
				// Skip noisy tool results
				const toolName = parsed.tool_name || '';
				if (NOISE_TOOLS.has(toolName)) continue;

				const raw = parsed.tool_result?.content;
				const content = typeof raw === 'string' ? raw : JSON.stringify(raw, null, 2);
				if (content && content !== '{}' && content !== 'null') {
					result.push({ kind: 'tool_result', content });
				}
			} else if (parsed.type === 'system' || parsed.type === 'init') {
				if (parsed.session_id) {
					result.push({ kind: 'system', text: `Session ${parsed.session_id.slice(0, 8)}` });
				}
			} else if (parsed.type === 'result') {
				const cost = parsed.total_cost_usd != null ? `$${parsed.total_cost_usd.toFixed(4)}` : '';
				const duration = parsed.duration_ms != null ? `${(parsed.duration_ms / 1000).toFixed(1)}s` : '';
				const turns = parsed.num_turns ?? 0;
				const isError = parsed.is_error === true;
				const message = parsed.result || '';
				result.push({ kind: 'result', cost, duration, turns, error: isError, message });
			}
			// Drop anything else (content_block_delta, content_block_stop, etc.)
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
							{#each entries as entry, idx}
								{#if entry.kind === 'text'}
									<div class="px-5 py-3">
										<pre class="text-sm text-cream whitespace-pre-wrap font-sans leading-relaxed">{entry.text}</pre>
									</div>

								{:else if entry.kind === 'bash'}
									<div class="px-5 py-3 bg-warm-900/30">
										{#if entry.description}
											<span class="text-[10px] font-mono uppercase tracking-wider text-warm-500 mb-1 block">{entry.description}</span>
										{/if}
										<div class="flex items-start gap-2">
											<span class="text-accent/60 font-mono text-xs select-none shrink-0">$</span>
											<pre class="text-xs font-mono text-cream-dim whitespace-pre-wrap">{entry.command}</pre>
										</div>
									</div>

								{:else if entry.kind === 'tool_use'}
									<div class="px-5 py-3 bg-warm-900/20">
										<button
											class="flex items-center gap-2 w-full text-left"
											onclick={() => toggleExpand(idx)}
										>
											<span class="text-[10px] font-mono uppercase tracking-wider text-accent/80 bg-accent/10 px-1.5 py-0.5">{entry.tool}</span>
											{#if entry.input && entry.input !== '{}'}
												<span class="text-[10px] text-warm-500">{expandedEntries.has(idx) ? '▾' : '▸'}</span>
											{/if}
										</button>
										{#if entry.input && entry.input !== '{}' && expandedEntries.has(idx)}
											<pre class="text-xs font-mono text-warm-400 whitespace-pre-wrap overflow-x-auto max-h-64 overflow-y-auto mt-2">{entry.input}</pre>
										{/if}
									</div>

								{:else if entry.kind === 'tool_result'}
									<div class="px-5 py-2 bg-warm-900/10">
										<button
											class="flex items-center gap-2 w-full text-left"
											onclick={() => toggleExpand(idx)}
										>
											<span class="text-[10px] font-mono uppercase tracking-wider text-warm-600">output</span>
											<span class="text-[10px] text-warm-500">{expandedEntries.has(idx) ? '▾' : '▸'}</span>
										</button>
										{#if expandedEntries.has(idx)}
											<pre class="text-xs font-mono text-warm-400 whitespace-pre-wrap overflow-x-auto max-h-64 overflow-y-auto mt-1.5">{entry.content}</pre>
										{/if}
									</div>

								{:else if entry.kind === 'system'}
									<div class="px-5 py-1.5">
										<span class="text-[10px] font-mono text-warm-600">{entry.text}</span>
									</div>

								{:else if entry.kind === 'error'}
									<div class="px-5 py-3 bg-danger/10">
										<div class="flex items-center gap-2 mb-1.5">
											<span class="text-[10px] font-mono uppercase tracking-wider text-danger/80 bg-danger/10 px-1.5 py-0.5">error</span>
											<span class="text-xs font-mono text-danger/70">{entry.code}</span>
										</div>
										<pre class="text-sm font-mono text-danger whitespace-pre-wrap">{entry.text}</pre>
									</div>

								{:else if entry.kind === 'result'}
									<div class="px-5 py-3 {entry.error ? 'bg-danger/5' : 'bg-success/5'}">
										<div class="flex items-center gap-4 text-xs">
											<span class="text-[10px] font-mono uppercase tracking-wider {entry.error ? 'text-danger/80' : 'text-success/80'}">{entry.error ? 'failed' : 'completed'}</span>
											{#if entry.turns}
												<span class="font-mono text-warm-400">{entry.turns} turn{entry.turns === 1 ? '' : 's'}</span>
											{/if}
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
