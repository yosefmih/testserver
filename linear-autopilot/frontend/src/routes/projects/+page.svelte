<script lang="ts">
	import { onMount } from 'svelte';
	import { listProjects, createProject, getMe, logout } from '$lib/api';

	let projects = $state<Array<any>>([]);
	let user = $state<any>(null);
	let newName = $state('');
	let creating = $state(false);

	onMount(async () => {
		user = await getMe();
		projects = await listProjects();
	});

	async function handleCreate() {
		if (!newName.trim()) return;
		creating = true;
		await createProject(newName.trim());
		newName = '';
		projects = await listProjects();
		creating = false;
	}

	async function handleLogout() {
		await logout();
		window.location.href = '/';
	}
</script>

<div class="container">
	<div class="header">
		<h1>Projects</h1>
		{#if user}
			<div style="display: flex; align-items: center; gap: 0.75rem;">
				<span style="color: #999; font-size: 0.875rem;">{user.email}</span>
				<button class="btn btn-secondary" onclick={handleLogout}>Logout</button>
			</div>
		{/if}
	</div>

	<div class="card" style="display: flex; gap: 0.5rem;">
		<input bind:value={newName} placeholder="New project name" onkeydown={(e) => e.key === 'Enter' && handleCreate()} />
		<button class="btn btn-primary" onclick={handleCreate} disabled={creating}>Create</button>
	</div>

	{#each projects as project}
		<a href="/projects/{project.id}" class="card" style="display: block;">
			<div style="display: flex; justify-content: space-between; align-items: center;">
				<strong>{project.name}</strong>
				<div style="display: flex; gap: 0.5rem;">
					<span class="badge" class:badge-success={project.github_connected} class:badge-pending={!project.github_connected}>
						GitHub {project.github_connected ? 'connected' : 'not connected'}
					</span>
					<span class="badge" class:badge-success={project.linear_connected} class:badge-pending={!project.linear_connected}>
						Linear {project.linear_connected ? 'connected' : 'not connected'}
					</span>
				</div>
			</div>
			{#if project.github_repo}
				<p style="color: #999; font-size: 0.875rem; margin-top: 0.25rem;">{project.github_repo}</p>
			{/if}
		</a>
	{/each}

	{#if projects.length === 0}
		<p style="color: #666; text-align: center; padding: 2rem;">No projects yet. Create one above.</p>
	{/if}
</div>
