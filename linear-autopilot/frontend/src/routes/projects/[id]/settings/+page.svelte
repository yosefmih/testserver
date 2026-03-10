<script lang="ts">
	import { onMount } from 'svelte';
	import { page } from '$app/state';
	import { getProject, updateProjectSettings, deleteProject, listGithubRepos, selectGithubRepo, disconnectGithub, disconnectLinear } from '$lib/api';

	let project = $state<any>(null);
	let autopilotLabel = $state('');
	let saving = $state(false);
	let message = $state('');
	let deleting = $state(false);

	let githubRepos = $state<Array<{ full_name: string; private: boolean }>>([]);
	let selectedRepo = $state('');
	let loadingRepos = $state(false);
	let reposLoaded = $state(false);
	let savingRepo = $state(false);
	let disconnectingGithub = $state(false);
	let disconnectingLinear = $state(false);

	const projectId = page.params.id;

	onMount(async () => {
		project = await getProject(projectId);
		autopilotLabel = project.autopilot_label || 'autopilot';
		selectedRepo = project.github_repo || '';
	});

	async function loadRepos() {
		loadingRepos = true;
		try {
			githubRepos = await listGithubRepos(projectId);
			reposLoaded = true;
		} catch (e: any) {
			message = e.message;
		}
		loadingRepos = false;
	}

	async function saveRepo() {
		if (!selectedRepo) return;
		savingRepo = true;
		message = '';
		try {
			await selectGithubRepo(projectId, selectedRepo);
			project = await getProject(projectId);
			message = 'Repository updated';
		} catch (e: any) {
			message = e.message;
		}
		savingRepo = false;
	}

	async function handleDisconnectGithub() {
		if (!confirm('Disconnect GitHub? Autopilot will no longer be able to create pull requests.')) return;
		disconnectingGithub = true;
		message = '';
		try {
			await disconnectGithub(projectId);
			project = await getProject(projectId);
			githubRepos = [];
			reposLoaded = false;
			selectedRepo = '';
			message = 'GitHub disconnected';
		} catch (e: any) {
			message = e.message;
		}
		disconnectingGithub = false;
	}

	async function handleDisconnectLinear() {
		if (!confirm('Disconnect Linear? Autopilot will stop listening for new issues.')) return;
		disconnectingLinear = true;
		message = '';
		try {
			await disconnectLinear(projectId);
			project = await getProject(projectId);
			message = 'Linear disconnected';
		} catch (e: any) {
			message = e.message;
		}
		disconnectingLinear = false;
	}

	async function handleDelete() {
		if (!confirm(`Delete project "${project.name}"? All jobs will be permanently removed. This cannot be undone.`)) return;
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

		<h1 class="font-serif text-3xl tracking-tight mb-12">{project.name} <span class="text-warm-500">&mdash;</span> Settings</h1>

		<!-- GitHub Integration -->
		<section class="mb-8">
			<h2 class="text-xs text-warm-500 uppercase tracking-wider mb-4">GitHub Integration</h2>
			<div class="border border-warm-700/50 px-6 py-5">
				{#if project.github_connected}
					<div class="flex items-center justify-between mb-4">
						<div class="flex items-center gap-2">
							<span class="w-2 h-2 rounded-full bg-success"></span>
							<span class="text-success text-sm">Connected</span>
						</div>
						<div class="flex items-center gap-4">
							<a
								href="/api/v1/projects/{projectId}/integrations/github/install"
								class="text-warm-500 text-xs hover:text-cream transition-colors duration-200 no-underline"
							>
								Reinstall
							</a>
							<button
								class="text-red-400 text-xs hover:text-red-300 transition-colors duration-200 disabled:opacity-50"
								onclick={handleDisconnectGithub}
								disabled={disconnectingGithub}
							>
								{disconnectingGithub ? 'Disconnecting...' : 'Disconnect'}
							</button>
						</div>
					</div>

					<div>
						<label class="text-warm-500 text-xs uppercase tracking-wider block mb-2">Repository</label>
						{#if project.github_repo}
							<p class="text-cream text-sm mb-3">{project.github_repo}</p>
						{/if}
						{#if !reposLoaded}
							<button
								class="text-warm-500 text-xs hover:text-cream transition-colors duration-200 disabled:opacity-50"
								onclick={loadRepos}
								disabled={loadingRepos}
							>
								{loadingRepos ? 'Loading repos...' : project.github_repo ? 'Change repository' : 'Select a repository'}
							</button>
						{:else}
							<div class="flex items-center gap-3">
								<select
									bind:value={selectedRepo}
									class="flex-1 bg-transparent border border-warm-600 px-4 py-2.5 text-sm text-cream focus:outline-none focus:border-accent transition-colors duration-200"
								>
									<option value="">-- Select a repository --</option>
									{#each githubRepos as repo}
										<option value={repo.full_name}>{repo.full_name}{repo.private ? ' (private)' : ''}</option>
									{/each}
								</select>
								<button
									class="bg-accent/10 border border-accent text-accent px-4 py-2.5 text-sm hover:bg-accent/20 transition-all duration-200 disabled:opacity-50"
									onclick={saveRepo}
									disabled={savingRepo || !selectedRepo}
								>
									{savingRepo ? 'Saving...' : 'Save'}
								</button>
							</div>
						{/if}
					</div>
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
							{#if project.linear_organization_id}
								<span class="text-warm-500 text-xs">({project.linear_organization_id})</span>
							{/if}
						</div>
						<div class="flex items-center gap-4">
							<a
								href="/api/v1/projects/{projectId}/integrations/linear/connect"
								class="text-warm-500 text-xs hover:text-cream transition-colors duration-200 no-underline"
							>
								Reconnect
							</a>
							<button
								class="text-red-400 text-xs hover:text-red-300 transition-colors duration-200 disabled:opacity-50"
								onclick={handleDisconnectLinear}
								disabled={disconnectingLinear}
							>
								{disconnectingLinear ? 'Disconnecting...' : 'Disconnect'}
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
			<div class="border border-warm-700/50 px-6 py-5">
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
						<p class="text-warm-500 text-xs mt-1">Permanently remove this project and all its jobs. This cannot be undone.</p>
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
