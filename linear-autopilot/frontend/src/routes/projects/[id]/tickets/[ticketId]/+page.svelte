<script lang="ts">
	import { onMount } from 'svelte';
	import { page } from '$app/state';
	import { getTicket, getRunLogs, triggerReviewNow, cancelTicket } from '$lib/api';
	import type { Run } from '$lib/api';

	type ActionEntry = {
		kind: 'action';
		tool: string;
		summary: string;
		input: string;
		output: string;
	};

	type LogEntry =
		| { kind: 'message'; text: string }
		| ActionEntry
		| { kind: 'command'; command: string; description: string; output: string }
		| { kind: 'result'; cost: string; duration: string; turns: number; error: boolean; message: string }
		| { kind: 'error'; text: string; code: string }
		| { kind: 'system'; text: string }
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
	let logSocket = $state<WebSocket | null>(null);
	let streaming = $state(false);
	let logContainer = $state<HTMLElement | null>(null);

	$effect(() => {
		if (streaming && expandedRun && runLogs[expandedRun]) {
			runLogs[expandedRun].length;
			requestAnimationFrame(() => {
				if (logContainer) logContainer.scrollTop = logContainer.scrollHeight;
			});
		}
	});
	let triggering = $state(false);
	let cancelling = $state(false);
	let hasActiveRun = $derived(ticket?.runs?.some((r: Run) => ACTIVE_STATUSES.includes(r.status)) ?? false);

	const projectId = page.params.id;
	const ticketId = page.params.ticketId;

	async function handleTriggerReview() {
		triggering = true;
		try {
			await triggerReviewNow(projectId, ticketId);
			ticket = await getTicket(projectId, ticketId);
		} catch (e: any) {
			alert(e.message);
		}
		triggering = false;
	}

	async function handleCancelTicket() {
		if (!confirm('Cancel this ticket? This will delete the sandbox and volume, and cannot be undone.')) return;
		cancelling = true;
		try {
			await cancelTicket(projectId, ticketId);
			ticket = await getTicket(projectId, ticketId);
			if (autoRefresh) {
				clearInterval(autoRefresh);
				autoRefresh = null;
			}
		} catch (e: any) {
			alert(e.message);
		}
		cancelling = false;
	}

	onMount(() => {
		loadTicket();
		return () => {
			if (autoRefresh) clearInterval(autoRefresh);
			closeLogStream();
		};
	});

	async function loadTicket() {
		ticket = await getTicket(projectId, ticketId);

		const hasActiveRun = ticket.runs.some((r: Run) => ACTIVE_STATUSES.includes(r.status));
		if (hasActiveRun && !autoRefresh) {
			autoRefresh = setInterval(async () => {
				ticket = await getTicket(projectId, ticketId);
				const stillActive = ticket.runs.some((r: Run) => ACTIVE_STATUSES.includes(r.status));
				if (!stillActive) {
					if (autoRefresh) {
						clearInterval(autoRefresh);
						autoRefresh = null;
					}
					if (expandedRun) {
						closeLogStream();
						await loadRunLogs(expandedRun);
					}
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

	function closeLogStream() {
		if (logSocket) {
			logSocket.close();
			logSocket = null;
		}
		streaming = false;
	}

	function connectLogStream(runId: string) {
		closeLogStream();
		const proto = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
		const url = `${proto}//${window.location.host}/api/v1/projects/${projectId}/tickets/${ticketId}/runs/${runId}/logs/stream`;
		const ws = new WebSocket(url);
		streaming = true;

		if (!runLogs[runId]) {
			runLogs = { ...runLogs, [runId]: [] };
		}

		ws.onmessage = (event) => {
			const current = runLogs[runId] || [];
			runLogs = { ...runLogs, [runId]: [...current, event.data] };
		};

		ws.onerror = () => {
			streaming = false;
		};

		ws.onclose = () => {
			streaming = false;
			logSocket = null;
		};

		logSocket = ws;
	}

	function isRunActive(runId: string): boolean {
		const run = ticket?.runs?.find((r: Run) => r.id === runId);
		return run ? ACTIVE_STATUSES.includes(run.status) : false;
	}

	async function toggleRun(runId: string) {
		if (expandedRun === runId) {
			expandedRun = null;
			expandedEntries = new Set();
			closeLogStream();
		} else {
			expandedRun = runId;
			expandedEntries = new Set();
			closeLogStream();

			if (isRunActive(runId)) {
				await loadRunLogs(runId);
				connectLogStream(runId);
			} else if (!runLogs[runId]) {
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
		if (status === 'cancelled') return 'text-danger';
		return 'text-warm-500';
	}

	// --- Smart summaries for tool calls ---

	function summarizeTool(name: string, rawInput: any): string {
		const input = typeof rawInput === 'string' ? safeJsonParse(rawInput) : rawInput || {};

		if (name === 'Read') return input.file_path ? shortPath(input.file_path) : 'file';
		if (name === 'Write') return input.file_path ? shortPath(input.file_path) : 'file';
		if (name === 'Edit') return input.file_path ? shortPath(input.file_path) : 'file';
		if (name === 'Glob') return input.pattern ? `\`${input.pattern}\`` : 'files';
		if (name === 'Grep') return input.pattern ? `\`${input.pattern}\`` : 'content';
		if (name === 'Agent') return input.description || input.prompt?.slice(0, 60) || 'subtask';
		if (name === 'Bash') return input.description || truncate(input.command || '', 80);

		if (name.startsWith('mcp__github__')) return formatMcpName(name);
		if (name.startsWith('mcp__linear__')) return formatMcpName(name);

		return '';
	}

	function formatMcpName(name: string): string {
		const parts = name.split('__');
		if (parts.length >= 3) {
			const action = parts.slice(2).join(' ').replace(/_/g, ' ');
			return action;
		}
		return name;
	}

	function toolDisplayName(name: string): string {
		if (name === 'Bash') return 'Terminal';
		if (name === 'Read') return 'Read';
		if (name === 'Write') return 'Write';
		if (name === 'Edit') return 'Edit';
		if (name === 'Glob') return 'Find';
		if (name === 'Grep') return 'Search';
		if (name === 'Agent') return 'Agent';
		if (name.startsWith('mcp__github__')) return 'GitHub';
		if (name.startsWith('mcp__linear__')) return 'Linear';
		return name;
	}

	function toolColor(name: string): string {
		if (name === 'Bash') return 'text-warm-400 bg-warm-800/60';
		if (name === 'Read') return 'text-blue-400 bg-blue-900/30';
		if (name === 'Write' || name === 'Edit') return 'text-amber-400 bg-amber-900/30';
		if (name === 'Glob' || name === 'Grep') return 'text-violet-400 bg-violet-900/30';
		if (name === 'Agent') return 'text-accent bg-accent/10';
		if (name.startsWith('mcp__github__')) return 'text-green-400 bg-green-900/30';
		if (name.startsWith('mcp__linear__')) return 'text-indigo-400 bg-indigo-900/30';
		return 'text-warm-400 bg-warm-800/40';
	}

	function shortPath(fullPath: string): string {
		const parts = fullPath.replace(/^\/+/, '').split('/');
		if (parts.length <= 3) return fullPath;
		return '.../' + parts.slice(-3).join('/');
	}

	function truncate(s: string, max: number): string {
		if (s.length <= max) return s;
		return s.slice(0, max) + '...';
	}

	function safeJsonParse(s: string): any {
		try { return JSON.parse(s); } catch { return {}; }
	}

	function cleanToolResult(raw: any, toolName: string): string {
		if (!raw) return '';
		if (typeof raw === 'string') {
			if (raw.length > 3000) return raw.slice(0, 3000) + '\n... (truncated)';
			return raw;
		}
		if (typeof raw === 'object') {
			const cleaned = { ...raw };
			delete cleaned.originalFile;
			delete cleaned.structuredPatch;
			const s = JSON.stringify(cleaned, null, 2);
			if (s.length > 3000) return s.slice(0, 3000) + '\n... (truncated)';
			return s;
		}
		return String(raw);
	}

	// --- Log parsing ---

	function parseLogs(lines: string[]): LogEntry[] {
		const result: LogEntry[] = [];
		const seenToolIds = new Set<string>();
		const pendingActions = new Map<string, ActionEntry>();

		for (const line of lines) {
			const trimmed = line.trim();
			if (!trimmed) continue;

			let parsed: any;
			try {
				parsed = JSON.parse(trimmed);
			} catch {
				if (trimmed.length > 5 && !trimmed.startsWith('{') && !trimmed.startsWith('"')) {
					result.push({ kind: 'raw', text: truncate(trimmed, 500) });
				}
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
					if (block.type === 'text' && block.text?.trim()) {
						result.push({ kind: 'message', text: block.text });
					} else if (block.type === 'tool_use') {
						if (block.id) seenToolIds.add(block.id);
						const entry = buildAction(block.name, block.input, block.id);
						if (entry) {
							if (block.id) pendingActions.set(block.id, entry);
							result.push(entry);
						}
					}
				}
			} else if (parsed.type === 'user') {
				continue;
			} else if (parsed.type === 'tool_use' || parsed.type === 'content_block_start') {
				const tool = parsed.tool || parsed.content_block;
				if (tool?.id && seenToolIds.has(tool.id)) continue;
				if (tool?.id) seenToolIds.add(tool.id);
				if (tool?.type === 'tool_use') {
					const entry = buildAction(tool.name, tool.input, tool.id);
					if (entry) {
						if (tool.id) pendingActions.set(tool.id, entry);
						result.push(entry);
					}
				}
			} else if (parsed.type === 'tool_result') {
				const toolName = parsed.tool_name || '';
				if (NOISE_TOOLS.has(toolName)) continue;
				const toolId = parsed.tool_use_id || '';
				const content = cleanToolResult(parsed.tool_result?.content, toolName);

				if (toolId && pendingActions.has(toolId)) {
					const action = pendingActions.get(toolId)!;
					action.output = content || '';
					pendingActions.delete(toolId);
				} else if (content && content !== '{}' && content !== 'null') {
					result.push({
						kind: 'action',
						tool: toolName || 'unknown',
						summary: '',
						input: '',
						output: content,
					});
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

	function buildAction(name: string, rawInput: any, id?: string): ActionEntry | null {
		if (!name || NOISE_TOOLS.has(name)) return null;

		const input = typeof rawInput === 'string' ? rawInput : JSON.stringify(rawInput, null, 2);
		const summary = summarizeTool(name, rawInput);

		if (name === 'Bash') {
			const parsed = typeof rawInput === 'string' ? safeJsonParse(rawInput) : rawInput || {};
			return {
				kind: 'action',
				tool: name,
				summary: parsed.description || '',
				input: parsed.command || '',
				output: '',
			};
		}

		return {
			kind: 'action',
			tool: name,
			summary,
			input: input || '',
			output: '',
		};
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
				<div class="flex items-center gap-3 mb-2">
					{#if ticket.linear_issue_identifier}
						<span class="font-mono text-sm text-warm-500">{ticket.linear_issue_identifier}</span>
					{/if}
					<span class={ticketStatusColor(ticket.status) + ' text-sm'}>{ticket.status}</span>
				</div>
				<h1 class="font-serif text-2xl tracking-tight">{ticket.linear_issue_title}</h1>
			</div>
			<div class="flex gap-3">
				{#if ticket.pr_url && ticket.status === 'active'}
					<button
						class="border border-warm-600 text-cream-dim px-4 py-2 text-sm hover:bg-surface-raised hover:border-warm-400 transition-all duration-200 disabled:opacity-40 disabled:cursor-not-allowed"
						onclick={handleTriggerReview}
						disabled={triggering || hasActiveRun}
					>
						{triggering ? 'Triggering...' : 'Run review'}
					</button>
				{/if}
				{#if ticket.status !== 'cancelled' && ticket.status !== 'merged'}
					<button
						class="border border-danger/60 text-danger px-4 py-2 text-sm hover:bg-danger/10 hover:border-danger transition-all duration-200 disabled:opacity-40 disabled:cursor-not-allowed"
						onclick={handleCancelTicket}
						disabled={cancelling}
					>
						{cancelling ? 'Cancelling...' : 'Cancel ticket'}
					</button>
				{/if}
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
									<div class="flex items-center gap-3">
										<span class="text-[10px] text-warm-500 uppercase tracking-wider">Activity</span>
										{#if streaming}
											<span class="flex items-center gap-1.5">
												<span class="w-1.5 h-1.5 rounded-full bg-accent animate-pulse"></span>
												<span class="text-[10px] text-accent uppercase tracking-wider">Live</span>
											</span>
										{/if}
									</div>
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
											<div class="overflow-x-auto max-h-[70vh] overflow-y-auto" bind:this={logContainer}>
												<pre class="px-5 py-4 text-xs font-mono text-cream-dim leading-relaxed">{runLogs[run.id].join('\n')}</pre>
											</div>
										{:else if runEntries[run.id]?.length}
											<div class="max-h-[70vh] overflow-y-auto" bind:this={logContainer}>
												{#each runEntries[run.id] as entry, idx}

													{#if entry.kind === 'message'}
														<div class="px-5 py-3 border-b border-warm-700/15">
															<pre class="text-[13px] text-cream whitespace-pre-wrap font-sans leading-relaxed">{entry.text}</pre>
														</div>

													{:else if entry.kind === 'action' && entry.tool === 'Bash'}
														<div class="group px-5 py-2 border-b border-warm-700/10 hover:bg-warm-900/20 transition-colors">
															<button class="flex items-center gap-2.5 w-full text-left" onclick={() => toggleExpand(idx)}>
																<span class="text-[10px] font-mono px-1.5 py-0.5 rounded {toolColor(entry.tool)}">{toolDisplayName(entry.tool)}</span>
																<span class="text-xs text-cream-dim truncate flex-1">{entry.summary || truncate(entry.input, 100)}</span>
																<span class="text-[10px] text-warm-600 opacity-0 group-hover:opacity-100 transition-opacity">{expandedEntries.has(idx) ? '▾' : '▸'}</span>
															</button>
															{#if expandedEntries.has(idx)}
																<div class="mt-2 ml-8 space-y-2">
																	{#if entry.input}
																		<pre class="text-xs font-mono text-warm-400 whitespace-pre-wrap bg-warm-900/40 rounded px-3 py-2 overflow-x-auto max-h-48 overflow-y-auto">{entry.input}</pre>
																	{/if}
																	{#if entry.output}
																		<pre class="text-xs font-mono text-warm-500 whitespace-pre-wrap bg-warm-900/20 rounded px-3 py-2 overflow-x-auto max-h-48 overflow-y-auto">{entry.output}</pre>
																	{/if}
																</div>
															{/if}
														</div>

													{:else if entry.kind === 'action'}
														<div class="group px-5 py-2 border-b border-warm-700/10 hover:bg-warm-900/20 transition-colors">
															<button class="flex items-center gap-2.5 w-full text-left" onclick={() => toggleExpand(idx)}>
																<span class="text-[10px] font-mono px-1.5 py-0.5 rounded {toolColor(entry.tool)}">{toolDisplayName(entry.tool)}</span>
																<span class="text-xs text-cream-dim truncate flex-1">{entry.summary}</span>
																{#if entry.output}
																	<span class="text-[10px] text-warm-600 opacity-0 group-hover:opacity-100 transition-opacity">{expandedEntries.has(idx) ? '▾' : '▸'}</span>
																{/if}
															</button>
															{#if expandedEntries.has(idx)}
																<div class="mt-2 ml-8 space-y-2">
																	{#if entry.input && entry.input !== '{}'}
																		<details class="text-xs">
																			<summary class="text-warm-600 cursor-pointer hover:text-warm-400 transition-colors">input</summary>
																			<pre class="font-mono text-warm-400 whitespace-pre-wrap bg-warm-900/40 rounded px-3 py-2 overflow-x-auto max-h-48 overflow-y-auto mt-1">{entry.input}</pre>
																		</details>
																	{/if}
																	{#if entry.output}
																		<pre class="text-xs font-mono text-warm-500 whitespace-pre-wrap bg-warm-900/20 rounded px-3 py-2 overflow-x-auto max-h-48 overflow-y-auto">{entry.output}</pre>
																	{/if}
																</div>
															{/if}
														</div>

													{:else if entry.kind === 'error'}
														<div class="px-5 py-3 bg-danger/8 border-b border-danger/15">
															<div class="flex items-center gap-2 mb-1">
																<span class="text-[10px] font-mono uppercase tracking-wider text-danger/80 bg-danger/10 px-1.5 py-0.5 rounded">error</span>
																{#if entry.code}
																	<span class="text-xs font-mono text-danger/60">{entry.code}</span>
																{/if}
															</div>
															<pre class="text-sm font-mono text-danger whitespace-pre-wrap">{entry.text}</pre>
														</div>

													{:else if entry.kind === 'result'}
														<div class="px-5 py-3 {entry.error ? 'bg-danger/5' : 'bg-success/5'} border-b border-warm-700/10">
															<div class="flex items-center gap-4 text-xs">
																<span class="text-[10px] font-mono uppercase tracking-wider px-1.5 py-0.5 rounded {entry.error ? 'text-danger/80 bg-danger/10' : 'text-success/80 bg-success/10'}">{entry.error ? 'failed' : 'completed'}</span>
																{#if entry.turns}<span class="font-mono text-warm-400">{entry.turns} turn{entry.turns === 1 ? '' : 's'}</span>{/if}
																{#if entry.duration}<span class="font-mono text-warm-400">{entry.duration}</span>{/if}
																{#if entry.cost}<span class="font-mono text-warm-400">{entry.cost}</span>{/if}
															</div>
															{#if entry.message}
																<pre class="text-xs font-mono {entry.error ? 'text-danger' : 'text-warm-400'} whitespace-pre-wrap mt-1.5">{entry.message}</pre>
															{/if}
														</div>

													{:else if entry.kind === 'system'}
														<div class="px-5 py-1 border-b border-warm-700/10">
															<span class="text-[10px] font-mono text-warm-600">{entry.text}</span>
														</div>

													{:else if entry.kind === 'raw'}
														<div class="px-5 py-1.5 border-b border-warm-700/10">
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
