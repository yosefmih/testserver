<script lang="ts">
	import { onMount } from 'svelte';
	import { page } from '$app/state';
	import { getProject, updateProjectSettings, deleteProject, disconnectGithub, disconnectLinear } from '$lib/api';

	let project = $state<any>(null);
	let autopilotLabel = $state('');
	let customTools = $state('');
	let systemPrompt = $state('');
	let anthropicApiKey = $state('');
	let saving = $state(false);
	let message = $state('');
	let deleting = $state(false);

	const projectId = page.params.id;

	onMount(async () => {
		project = await getProject(projectId);
		autopilotLabel = project.autopilot_label || 'autopilot';
		customTools = project.custom_tools || '';
		systemPrompt = project.system_prompt || '';
	});

	async function handleDisconnectGithub() {
		if (!confirm('Disconnect GitHub integration? This will stop autopilot from creating PRs.')) return;
		try {
			await disconnectGithub(projectId);
			project = await getProject(projectId);
		} catch (e: any) {
			message = e.message;
		}
	}

	async function handleDisconnectLinear() {
		if (!confirm('Disconnect Linear integration? This will stop autopilot from receiving issues.')) return;
		try {
			await disconnectLinear(projectId);
			project = await getProject(projectId);
		} catch (e: any) {
			message = e.message;
		}
	}

	async function handleDelete() {
		if (!confirm(`Delete project "${project.name}"? All tickets and runs will be permanently removed. This cannot be undone.`)) return;
		deleting = true;
		try {
			await deleteProject(projectId);
			window.location.href = '/projects';
		} catch (e: any) {
			message = e.message;
			deleting = false;
		}
	}

	async function saveSettings() {
		saving = true;
		message = '';
		try {
			await updateProjectSettings(projectId, {
				autopilot_label: autopilotLabel || undefined,
				custom_tools: customTools,
				system_prompt: systemPrompt,
				anthropic_api_key: anthropicApiKey || undefined,
			});
			project = await getProject(projectId);
			message = 'Settings saved';
		} catch (e: any) {
			message = e.message;
		}
		saving = false;
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
			<a href="/projects/{projectId}" class="text-warm-500 text-sm hover:text-cream transition-colors duration-200 no-underline">&larr; Back to project</a>
		</div>

		<div class="flex items-center gap-6 mb-12">
			<h1 class="font-serif text-3xl tracking-tight">{project.name} <span class="text-warm-500">&mdash;</span> Settings</h1>
			<a
				href="/projects/{projectId}/members"
				class="text-warm-500 text-sm hover:text-cream transition-colors duration-200 no-underline"
			>
				Manage Members
			</a>
		</div>

		<!-- Anthropic API Key -->
		<section class="mb-8">
			<h2 class="text-xs text-warm-500 uppercase tracking-wider mb-4">Anthropic API Key</h2>
			<div class="border border-warm-700/50 px-6 py-5">
				<div class="flex items-center gap-2 mb-3">
					{#if project.claude_connected}
						<span class="w-2 h-2 rounded-full bg-success"></span>
						<span class="text-success text-xs">Key configured</span>
					{:else}
						<span class="w-2 h-2 rounded-full bg-red-400"></span>
						<span class="text-red-400 text-xs">No key configured — runs will fail</span>
					{/if}
				</div>
				<input
					type="password"
					bind:value={anthropicApiKey}
					placeholder={project.claude_connected ? '••••••••••••••••••••' : 'sk-ant-...'}
					class="w-full bg-transparent border border-warm-600 px-4 py-2.5 text-sm text-cream focus:outline-none focus:border-accent transition-colors duration-200 font-mono"
				/>
				<p class="text-warm-500 text-xs mt-2">
					Your Anthropic API key. Required for autopilot to run Claude Code. Saved with the settings below.
				</p>
			</div>
		</section>

		<!-- GitHub Integration -->
		<section class="mb-8">
			<h2 class="text-xs text-warm-500 uppercase tracking-wider mb-4">GitHub Integration</h2>
			<div class="border border-warm-700/50 px-6 py-5">
				{#if project.github_connected}
					<div class="flex items-center justify-between">
						<div class="flex items-center gap-2">
							<span class="w-2 h-2 rounded-full bg-success"></span>
							<span class="text-success text-sm">Connected</span>
						</div>
						<div class="flex items-center gap-4">
							<a
								href="/api/v1/projects/{projectId}/integrations/github/install"
								class="text-warm-500 text-xs hover:text-cream transition-colors duration-200 no-underline"
							>
								Update Integration
							</a>
							<button
								class="text-warm-500 text-xs hover:text-red-400 transition-colors duration-200"
								onclick={handleDisconnectGithub}
							>
								Disconnect
							</button>
						</div>
					</div>
					<p class="text-warm-500 text-xs mt-2">
						Autopilot automatically detects the relevant repo from the issue context.
					</p>
				{:else}
					<p class="text-warm-500 text-sm mb-4">Connect your GitHub account to enable auto-PRs.</p>
					<a
						href="/api/v1/projects/{projectId}/integrations/github/install"
						class="inline-block bg-accent/10 border border-accent text-accent px-5 py-2.5 text-sm hover:bg-accent/20 transition-all duration-200 no-underline"
					>
						Install GitHub App
					</a>
				{/if}
			</div>
		</section>

		<!-- Linear Integration -->
		<section class="mb-8">
			<h2 class="text-xs text-warm-500 uppercase tracking-wider mb-4">Linear Integration</h2>
			<div class="border border-warm-700/50 px-6 py-5">
				{#if project.linear_connected}
					<div class="flex items-center justify-between">
						<div class="flex items-center gap-2">
							<span class="w-2 h-2 rounded-full bg-success"></span>
							<span class="text-success text-sm">Connected</span>
						</div>
						<div class="flex items-center gap-4">
							<a
								href="/api/v1/projects/{projectId}/integrations/linear/connect"
								class="text-warm-500 text-xs hover:text-cream transition-colors duration-200 no-underline"
							>
								Update Integration
							</a>
							<button
								class="text-warm-500 text-xs hover:text-red-400 transition-colors duration-200"
								onclick={handleDisconnectLinear}
							>
								Disconnect
							</button>
						</div>
					</div>
				{:else}
					<p class="text-warm-500 text-sm mb-4">{project.linear_has_token ? 'Linear needs to be reconnected.' : 'Connect Linear to listen for issues.'}</p>
					<a
						href="/api/v1/projects/{projectId}/integrations/linear/connect"
						class="inline-block bg-accent/10 border border-accent text-accent px-5 py-2.5 text-sm hover:bg-accent/20 transition-all duration-200 no-underline"
					>
						{project.linear_has_token ? 'Reconnect Linear' : 'Connect Linear'}
					</a>
				{/if}
			</div>
		</section>

		<!-- Autopilot Settings -->
		<section class="mb-8">
			<h2 class="text-xs text-warm-500 uppercase tracking-wider mb-4">Autopilot Settings</h2>
			<div class="border border-warm-700/50 px-6 py-5 space-y-6">
				<div>
					<label class="text-warm-500 text-xs uppercase tracking-wider block mb-2">Trigger Label</label>
					<input
						bind:value={autopilotLabel}
						placeholder="autopilot"
						class="w-full bg-transparent border border-warm-600 px-4 py-2.5 text-sm text-cream focus:outline-none focus:border-accent transition-colors duration-200"
					/>
					<p class="text-warm-500 text-xs mt-2">
						Issues with this label will trigger Claude Code to create a fix PR.
					</p>
				</div>

				<div>
					<label class="text-warm-500 text-xs uppercase tracking-wider block mb-2">System Prompt</label>
					<textarea
						bind:value={systemPrompt}
						placeholder="Additional instructions for Claude Code (e.g. repo setup steps, coding conventions, build commands)..."
						rows="6"
						class="w-full bg-transparent border border-warm-600 px-4 py-2.5 text-sm text-cream focus:outline-none focus:border-accent transition-colors duration-200 font-mono resize-y"
					></textarea>
					<p class="text-warm-500 text-xs mt-2">
						Appended to every prompt. Use this for org-wide instructions like build setup, coding style, or repo-specific context.
					</p>
				</div>

				<div>
					<label class="text-warm-500 text-xs uppercase tracking-wider block mb-2">Additional Tools</label>
					<input
						bind:value={customTools}
						placeholder="e.g. mcp__custom__*,WebSearch"
						class="w-full bg-transparent border border-warm-600 px-4 py-2.5 text-sm text-cream focus:outline-none focus:border-accent transition-colors duration-200 font-mono"
					/>
					<p class="text-warm-500 text-xs mt-2">
						Comma-separated list of additional tool patterns to allow, added to the defaults (GitHub MCP, Linear MCP, Read, Write, Edit, Bash, Glob, Grep).
					</p>
				</div>
			</div>
		</section>

		<div class="flex items-center gap-4">
			<button
				class="bg-accent/10 border border-accent text-accent px-5 py-2.5 text-sm hover:bg-accent/20 transition-all duration-200 disabled:opacity-50"
				onclick={saveSettings}
				disabled={saving}
			>
				{saving ? 'Saving...' : 'Save Settings'}
			</button>
			{#if message}
				<span class="text-success text-sm">{message}</span>
			{/if}
		</div>

		<!-- Danger Zone -->
		<section class="mt-16">
			<h2 class="text-xs text-red-400 uppercase tracking-wider mb-4">Danger Zone</h2>
			<div class="border border-red-900/50 px-6 py-5">
				<div class="flex items-center justify-between">
					<div>
						<p class="text-cream text-sm">Delete this project</p>
						<p class="text-warm-500 text-xs mt-1">Permanently remove this project and all its tickets. This cannot be undone.</p>
					</div>
					<button
						class="border border-red-700 text-red-400 px-5 py-2.5 text-sm hover:bg-red-900/20 transition-all duration-200 disabled:opacity-50"
						onclick={handleDelete}
						disabled={deleting}
					>
						{deleting ? 'Deleting...' : 'Delete Project'}
					</button>
				</div>
			</div>
		</section>
	</main>
</div>
{/if}
