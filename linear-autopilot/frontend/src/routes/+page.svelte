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

<div class="container" style="text-align: center; padding-top: 8rem;">
	<h1 style="font-size: 2rem; margin-bottom: 0.5rem;">Linear Autopilot</h1>
	<p style="color: #999; margin-bottom: 2rem;">
		Tag a Linear issue, get a PR. Powered by Claude Code.
	</p>

	{#if !loading}
		<a href="/auth/google/login" class="btn btn-primary" style="padding: 0.75rem 2rem; font-size: 1rem;">
			Sign in with Google
		</a>
	{/if}
</div>
