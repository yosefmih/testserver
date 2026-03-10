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

<div class="min-h-screen">
	<header class="border-b border-warm-700/50 px-8 py-4">
		<div class="max-w-5xl mx-auto flex items-center justify-between">
			<a href="/" class="font-serif text-2xl text-cream hover:text-cream no-underline">Autopilot</a>
			{#if user}
				<div class="flex items-center gap-5">
					<span class="text-warm-500 text-sm">{user.email}</span>
					<button
						class="text-warm-500 text-sm hover:text-cream transition-colors duration-200"
						onclick={handleLogout}
					>
						Logout
					</button>
				</div>
			{/if}
		</div>
	</header>

	<main class="max-w-5xl mx-auto px-8 py-12">
		<h1 class="font-serif text-3xl tracking-tight mb-8">Projects</h1>

		<div class="flex gap-3 mb-8">
			<input
				bind:value={newName}
				placeholder="New project name"
				class="flex-1 bg-transparent border border-warm-600 px-4 py-2.5 text-sm text-cream focus:outline-none focus:border-accent transition-colors duration-200"
				onkeydown={(e) => e.key === 'Enter' && handleCreate()}
			/>
			<button
				class="bg-accent/10 border border-accent text-accent px-5 py-2.5 text-sm hover:bg-accent/20 transition-all duration-200 disabled:opacity-50"
				onclick={handleCreate}
				disabled={creating}
			>
				Create
			</button>
		</div>

		<div class="space-y-0">
			{#each projects as project}
				<a
					href="/projects/{project.id}"
					class="block border border-warm-700/50 px-6 py-5 hover:border-warm-600 hover:bg-surface-raised/50 transition-all duration-200 no-underline -mt-px first:mt-0"
				>
					<div class="flex items-center justify-between">
						<span class="text-cream text-sm">{project.name}</span>
						<div class="flex items-center gap-3">
							<span class="flex items-center gap-1.5 text-xs {project.github_connected ? 'text-success' : 'text-warm-500'}">
								<span class="w-1.5 h-1.5 rounded-full {project.github_connected ? 'bg-success' : 'bg-warm-600'}"></span>
								GitHub
							</span>
							<span class="flex items-center gap-1.5 text-xs {project.linear_connected ? 'text-success' : 'text-warm-500'}">
								<span class="w-1.5 h-1.5 rounded-full {project.linear_connected ? 'bg-success' : 'bg-warm-600'}"></span>
								Linear
							</span>
						</div>
					</div>
					</a>
			{/each}
		</div>

		{#if projects.length === 0}
			<p class="text-warm-500 text-sm text-center py-16">No projects yet. Create one above.</p>
		{/if}
	</main>
</div>
