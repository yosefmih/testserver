<script lang="ts">
	import '../app.css';
	import { api } from '$lib/api';
	let { children } = $props();
	let alertsEnabled = $state(false);
	$effect(() => {
		api.config().then((c) => (alertsEnabled = c.alertsEnabled)).catch(() => {});
	});
</script>

<div class="mx-auto max-w-4xl px-4 pb-24">
	<header class="flex items-baseline justify-between py-8">
		<a href="/" class="font-display text-4xl tracking-wide text-marquee">SEATWATCH</a>
		<nav class="flex items-baseline gap-6 text-sm text-dim">
			<span class="hidden sm:inline">AMC Lincoln Square 13 · New York</span>
			{#if alertsEnabled}
				<a href="/watches" class="border-b border-dotted border-dim hover:text-marquee">my watches</a>
			{/if}
		</nav>
	</header>
	{@render children()}
</div>
