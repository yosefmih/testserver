<script lang="ts">
	import { onMount } from 'svelte';
	import { page } from '$app/state';
	import { getTicket, getRunLogs } from '$lib/api';
	import type { Run } from '$lib/api';

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
	const ACTIVE_STATUSES = ['pending', 'launching', 'running'];

	let ticket = $state<any>(null);
	let expandedRun = $state<string | null>(null);
	let runLogs = $state<Record<string, string[]>>({});
	let runEntries = $derived.by(() => {
		const result: Record<string, LogEntry[]> = {};
		for (const [id, logs] of Object.entries(runLogs)) {
			result[id] = parseLogs(logs);
		}
		return result;
	});
	let logsError = $state('');
	let loadingLogs = $state(false);
	let showRaw = $state(false);
	let expandedEntries = $state<Set<number>>(new Set());
	let autoRefresh = $state<ReturnType<typeof setInterval> | null>(null);

	const projectId = page.params.id;
	const ticketId = page.params.ticketId;

	onMount(() => {
		loadTicket();
		return () => {
			if (autoRefresh) clearInterval(autoRefresh);
		};
	});

	async function loadTicket() {
		ticket = await getTicket(projectId, ticketId);

		const hasActiveRun = ticket.runs.some((r: Run) => ACTIVE_STATUSES.includes(r.status));
		if (hasActiveRun && !autoRefresh) {
			autoRefresh = setInterval(async () => {
				ticket = await getTicket(projectId, ticketId);
				if (expandedRun) await loadRunLogs(expandedRun);
				const stillActive = ticket.runs.some((r: Run) => ACTIVE_STATUSES.includes(r.status));
				if (!stillActive && autoRefresh) {
					clearInterval(autoRefresh);
					autoRefresh = null;
				}
			}, 5000);
		}
	}

	async function loadRunLogs(runId: string) {
		loadingLogs = true;
		try {
			const result = await getRunLogs(projectId, ticketId, runId);
			runLogs = { ...runLogs, [runId]: result.logs };
			logsError = result.error || '';
		} catch (e: any) {
			logsError = e.message;
		}
		loadingLogs = false;
	}

	async function toggleRun(runId: string) {
		if (expandedRun === runId) {
			expandedRun = null;
			expandedEntries = new Set();
		} else {
			expandedRun = runId;
			expandedEntries = new Set();
			if (!runLogs[runId]) {
				await loadRunLogs(runId);
			}
		}
	}

	function toggleExpand(idx: number) {
		const next = new Set(expandedEntries);
		if (next.has(idx)) next.delete(idx);
		else next.add(idx);
		expandedEntries = next;
	}

	function runStatusColor(status: string) {
		if (status === 'success') return 'text-success';
		if (status === 'running' || status === 'launching') return 'text-accent';
		if (status === 'pending') return 'text-warm-500';
		return 'text-danger';
	}

	function runDotColor(status: string) {
		if (status === 'success') return 'bg-success';
		if (status === 'running' || status === 'launching') return 'bg-accent';
		if (status === 'pending') return 'bg-warm-500';
		return 'bg-danger';
	}

	function ticketStatusColor(status: string) {
		if (status === 'active') return 'text-accent';
		if (status === 'merged') return 'text-success';
		if (status === 'failed') return 'text-danger';
		return 'text-warm-500';
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
		}
		return result;
	}
</script>

{#if ticket}
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
				<h1 class="font-serif text-2xl tracking-tight mb-2">{ticket.linear_issue_title}</h1>
				<div class="flex items-center gap-4 text-sm">
					<span class="font-mono text-warm-500">{ticket.linear_issue_id}</span>
					<span class={ticketStatusColor(ticket.status)}>{ticket.status}</span>
				</div>
			</div>
			<div class="flex gap-3">
				{#if ticket.linear_issue_url}
					<a href={ticket.linear_issue_url} target="_blank" class="border border-warm-600 text-cream-dim px-4 py-2 text-sm hover:bg-surface-raised hover:border-warm-400 transition-all duration-200 no-underline">Linear &rarr;</a>
				{/if}
				{#if ticket.pr_url}
					<a href={ticket.pr_url} target="_blank" class="border border-accent/60 text-accent px-4 py-2 text-sm hover:bg-accent/10 hover:border-accent transition-all duration-200 no-underline">PR &rarr;</a>
				{/if}
			</div>
		</div>

		<div class="flex items-center gap-6 mb-8 pb-6 border-b border-warm-700/50 text-xs text-warm-500">
			<span>Created: <span class="text-cream-dim font-mono">{new Date(ticket.created_at).toLocaleString()}</span></span>
			{#if ticket.pr_repo}
				<span>Repo: <span class="text-cream-dim font-mono">{ticket.pr_repo}</span></span>
			{/if}
			{#if ticket.volume_id}
				<span>Volume: <span class="text-cream-dim font-mono">{ticket.volume_id.slice(0, 12)}</span></span>
			{/if}
		</div>

		<h2 class="text-xs text-warm-500 uppercase tracking-wider mb-4">Runs ({ticket.runs.length})</h2>

		{#if ticket.runs.length > 0}
			<div class="space-y-2">
				{#each ticket.runs as run, runIdx}
					<div class="border border-warm-700/50">
						<button
							class="w-full flex items-center justify-between px-5 py-3 hover:bg-surface-raised/50 transition-all duration-200"
							onclick={() => toggleRun(run.id)}
						>
							<div class="flex items-center gap-4">
								<span class="text-xs text-warm-500">{expandedRun === run.id ? '▾' : '▸'}</span>
								<span class="text-[10px] font-mono uppercase tracking-wider text-accent/80 bg-accent/10 px-1.5 py-0.5">{run.kind}</span>
								<span class="flex items-center gap-1.5 {runStatusColor(run.status)}">
									<span class="w-1.5 h-1.5 rounded-full {runDotColor(run.status)}"></span>
									<span class="text-xs">{run.status}</span>
									{#if ACTIVE_STATUSES.includes(run.status)}
										<span class="animate-pulse">&hellip;</span>
									{/if}
								</span>
								{#if run.sandbox_id}
									<span class="text-[10px] font-mono text-warm-600">{run.sandbox_id}</span>
								{/if}
							</div>
							<div class="flex items-center gap-4 text-xs text-warm-500 font-mono">
								<span>{new Date(run.created_at).toLocaleString()}</span>
								{#if run.finished_at}
									<span class="text-warm-600">&rarr;</span>
									<span>{new Date(run.finished_at).toLocaleString()}</span>
								{/if}
							</div>
						</button>

						{#if expandedRun === run.id}
							<div class="border-t border-warm-700/30">
								{#if run.error}
									<div class="px-5 py-3 bg-danger/5">
										<pre class="text-sm text-danger whitespace-pre-wrap font-mono">{run.error}</pre>
									</div>
								{/if}

								<div class="px-5 py-2 flex items-center justify-between border-b border-warm-700/20">
									<span class="text-[10px] text-warm-500 uppercase tracking-wider">Sandbox Logs</span>
									<div class="flex items-center gap-4">
										<button
											class="text-xs transition-colors duration-200 {showRaw ? 'text-cream' : 'text-warm-500 hover:text-cream'}"
											onclick={() => showRaw = !showRaw}
										>
											{showRaw ? 'Parsed' : 'Raw'}
										</button>
										<button
											class="text-xs text-warm-500 hover:text-cream transition-colors duration-200"
											onclick={() => loadRunLogs(run.id)}
											disabled={loadingLogs}
										>
											{loadingLogs ? 'Loading...' : 'Refresh'}
										</button>
									</div>
								</div>

								{#if logsError}
									<div class="px-5 py-3">
										<p class="text-warm-500 text-sm">{logsError}</p>
									</div>
								{/if}

								<div class="bg-surface-base overflow-hidden">
									{#if runLogs[run.id]?.length}
										{#if showRaw}
											<div class="overflow-x-auto max-h-[70vh] overflow-y-auto">
												<pre class="px-5 py-4 text-xs font-mono text-cream-dim leading-relaxed">{runLogs[run.id].join('\n')}</pre>
											</div>
										{:else if runEntries[run.id]?.length}
											<div class="max-h-[70vh] overflow-y-auto divide-y divide-warm-700/30">
												{#each runEntries[run.id] as entry, idx}
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
															<button class="flex items-center gap-2 w-full text-left" onclick={() => toggleExpand(idx)}>
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
															<button class="flex items-center gap-2 w-full text-left" onclick={() => toggleExpand(idx)}>
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
																{#if entry.turns}<span class="font-mono text-warm-400">{entry.turns} turn{entry.turns === 1 ? '' : 's'}</span>{/if}
																{#if entry.duration}<span class="font-mono text-warm-400">{entry.duration}</span>{/if}
																{#if entry.cost}<span class="font-mono text-warm-400">{entry.cost}</span>{/if}
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
										<div class="px-5 py-8 text-center">
											<p class="text-warm-500 text-sm">
												{#if run.status === 'pending'}
													Queued, waiting for next sync cycle...
												{:else if run.status === 'launching'}
													Launching sandbox...
												{:else if run.status === 'running'}
													Sandbox is running, logs will appear shortly...
												{:else}
													No logs available.
												{/if}
											</p>
										</div>
									{/if}
								</div>
							</div>
						{/if}
					</div>
				{/each}
			</div>
		{:else}
			<div class="border border-warm-700/50 px-6 py-8 text-center">
				<p class="text-warm-500 text-sm">No runs yet.</p>
			</div>
		{/if}
	</main>
</div>
{/if}
