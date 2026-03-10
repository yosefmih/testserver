<script lang="ts">
	import { onMount } from 'svelte';
	import { page } from '$app/state';
	import { getProject, updateProjectSettings, listLinearTeams, setLinearTeam } from '$lib/api';

	let project = $state<any>(null);
	let teams = $state<Array<any>>([]);
	let selectedTeam = $state('');
	let autopilotLabel = $state('');
	let saving = $state(false);
	let message = $state('');

	const projectId = page.params.id;

	onMount(async () => {
		project = await getProject(projectId);
		autopilotLabel = project.autopilot_label || 'autopilot';
		selectedTeam = project.linear_team_id || '';

		if (project.linear_has_token) {
			try { teams = await listLinearTeams(projectId); } catch {}
		}
	});

	async function saveSettings() {
		saving = true;
		message = '';
		try {
			if (selectedTeam && selectedTeam !== project.linear_team_id) {
				await setLinearTeam(projectId, selectedTeam);
			}
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
					<div class="flex items-center gap-2">
						<span class="w-2 h-2 rounded-full bg-success"></span>
						<span class="text-success text-sm">Connected</span>
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
				{#if project.linear_has_token}
					<div class="flex items-center gap-2 mb-4">
						<span class="w-2 h-2 rounded-full bg-success"></span>
						<span class="text-success text-sm">Connected{#if project.linear_connected} &middot; Team configured{/if}</span>
					</div>
					{#if teams.length > 0}
						<label class="text-warm-500 text-xs uppercase tracking-wider block mb-2">Linear Team</label>
						<select
							bind:value={selectedTeam}
							class="w-full bg-transparent border border-warm-600 px-4 py-2.5 text-sm text-cream focus:outline-none focus:border-accent transition-colors duration-200"
						>
							<option value="">Select a team</option>
							{#each teams as team}
								<option value={team.id}>{team.name} ({team.key})</option>
							{/each}
						</select>
					{/if}
				{:else}
					<p class="text-warm-500 text-sm mb-4">Connect Linear to listen for issues.</p>
					<a
						href="/api/v1/projects/{projectId}/integrations/linear/connect"
						class="inline-block bg-accent/10 border border-accent text-accent px-5 py-2.5 text-sm hover:bg-accent/20 transition-all duration-200 no-underline"
					>
						Connect Linear
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
	</main>
</div>
{/if}
