<script lang="ts">
	import { onMount } from 'svelte';
	import { page } from '$app/state';
	import { getProject, updateProjectSettings, listGithubRepos, listLinearTeams, setLinearTeam } from '$lib/api';

	let project = $state<any>(null);
	let repos = $state<Array<any>>([]);
	let teams = $state<Array<any>>([]);
	let selectedRepo = $state('');
	let selectedTeam = $state('');
	let autopilotLabel = $state('');
	let saving = $state(false);
	let message = $state('');

	const projectId = page.params.id;

	onMount(async () => {
		project = await getProject(projectId);
		selectedRepo = project.github_repo || '';
		autopilotLabel = project.autopilot_label || 'autopilot';

		if (project.github_connected) {
			try { repos = await listGithubRepos(projectId); } catch {}
		}
		if (project.linear_connected) {
			try { teams = await listLinearTeams(projectId); } catch {}
		}
	});

	async function saveSettings() {
		saving = true;
		message = '';
		try {
			await updateProjectSettings(projectId, {
				github_repo: selectedRepo || undefined,
				autopilot_label: autopilotLabel || undefined,
			});
			message = 'Settings saved';
		} catch (e: any) {
			message = e.message;
		}
		saving = false;
	}

	async function handleSetTeam() {
		if (!selectedTeam) return;
		await setLinearTeam(projectId, selectedTeam);
		project = await getProject(projectId);
		message = 'Linear team set';
	}
</script>

{#if project}
<div class="container">
	<div class="header">
		<div>
			<a href="/projects/{projectId}" style="color: #666; font-size: 0.875rem;">&larr; Back to project</a>
			<h1 style="margin-top: 0.25rem;">{project.name} &mdash; Settings</h1>
		</div>
	</div>

	<!-- GitHub Integration -->
	<div class="card">
		<h2 style="font-size: 1rem; margin-bottom: 1rem;">GitHub Integration</h2>
		{#if project.github_connected}
			<p style="color: #4ade80; margin-bottom: 1rem;">Connected</p>
			<div class="form-group">
				<label>Target Repository</label>
				{#if repos.length > 0}
					<select bind:value={selectedRepo}>
						<option value="">Select a repo</option>
						{#each repos as repo}
							<option value={repo.full_name}>{repo.full_name}</option>
						{/each}
					</select>
				{:else}
					<input bind:value={selectedRepo} placeholder="org/repo" />
				{/if}
			</div>
		{:else}
			<p style="color: #999; margin-bottom: 1rem;">Connect your GitHub account to enable auto-PRs.</p>
			<a href="/api/v1/projects/{projectId}/integrations/github/install" class="btn btn-primary">
				Install GitHub App
			</a>
		{/if}
	</div>

	<!-- Linear Integration -->
	<div class="card">
		<h2 style="font-size: 1rem; margin-bottom: 1rem;">Linear Integration</h2>
		{#if project.linear_connected}
			<p style="color: #4ade80; margin-bottom: 1rem;">Connected</p>
			{#if teams.length > 0}
				<div class="form-group">
					<label>Linear Team</label>
					<div style="display: flex; gap: 0.5rem;">
						<select bind:value={selectedTeam}>
							<option value="">Select a team</option>
							{#each teams as team}
								<option value={team.id}>{team.name} ({team.key})</option>
							{/each}
						</select>
						<button class="btn btn-secondary" onclick={handleSetTeam}>Set</button>
					</div>
				</div>
			{/if}
		{:else}
			<p style="color: #999; margin-bottom: 1rem;">Connect Linear to listen for issues.</p>
			<a href="/api/v1/projects/{projectId}/integrations/linear/connect" class="btn btn-primary">
				Connect Linear
			</a>
		{/if}
	</div>

	<!-- Autopilot Settings -->
	<div class="card">
		<h2 style="font-size: 1rem; margin-bottom: 1rem;">Autopilot Settings</h2>
		<div class="form-group">
			<label>Trigger Label</label>
			<input bind:value={autopilotLabel} placeholder="autopilot" />
			<p style="color: #666; font-size: 0.75rem; margin-top: 0.25rem;">
				Issues with this label will trigger Claude Code to create a fix PR.
			</p>
		</div>
	</div>

	<div style="display: flex; gap: 0.75rem; align-items: center;">
		<button class="btn btn-primary" onclick={saveSettings} disabled={saving}>
			{saving ? 'Saving...' : 'Save Settings'}
		</button>
		{#if message}
			<span style="color: #4ade80; font-size: 0.875rem;">{message}</span>
		{/if}
	</div>
</div>
{/if}
