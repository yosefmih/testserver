<script lang="ts">
	import { onMount } from 'svelte';
	import { getMe } from '$lib/api';

	let loading = $state(true);

	onMount(async () => {
		try {
			await getMe();
			window.location.href = '/projects';
		} catch {
			// not logged in
		}
		loading = false;
	});
</script>

<div class="min-h-screen flex flex-col items-center justify-center px-8">
	<h1 class="font-serif text-5xl tracking-tight text-cream mb-4">Linear Autopilot</h1>
	<p class="text-warm-500 text-lg mb-12">
		Tag a Linear issue, get a PR. Powered by Claude Code.
	</p>

	{#if !loading}
		<a
			href="/auth/google/login"
			class="border border-accent text-accent px-8 py-3.5 text-sm hover:bg-accent/20 transition-all duration-200"
		>
			Sign in with Google
		</a>
	{/if}
</div>
