<script lang="ts">
	import { onMount } from 'svelte';
	import { page } from '$app/state';
	import { getMe, getInvite, acceptInvite } from '$lib/api';

	let loading = $state(true);
	let loggedIn = $state(false);
	let accepting = $state(false);
	let invite = $state<any>(null);
	let error = $state('');

	const token = page.params.token;

	onMount(async () => {
		try {
			invite = await getInvite(token);
		} catch (e: any) {
			error = 'This invite link is invalid or has been revoked.';
			loading = false;
			return;
		}

		if (invite.status === 'expired') {
			error = `This invite to ${invite.project_name} has expired. Ask the project admin to send a new one.`;
			loading = false;
			return;
		}

		if (invite.status === 'already_accepted') {
			window.location.href = `/projects/${invite.project_id}`;
			return;
		}

		try {
			await getMe();
			loggedIn = true;
		} catch {
			loggedIn = false;
		}

		loading = false;
	});

	async function handleAccept() {
		accepting = true;
		error = '';
		try {
			const result = await acceptInvite(token);
			if (result.status === 'accepted' || result.status === 'already_member') {
				window.location.href = `/projects/${result.project_id}`;
			}
		} catch (e: any) {
			error = e.message;
			accepting = false;
		}
	}
</script>

<div class="min-h-screen flex flex-col items-center justify-center px-8">
	{#if loading}
		<p class="text-warm-500 text-sm">Loading...</p>
	{:else if error}
		<h1 class="font-serif text-3xl tracking-tight text-cream mb-4">Invite</h1>
		<p class="text-red-400 text-sm mb-8">{error}</p>
		<a
			href="/"
			class="text-warm-500 text-sm hover:text-cream transition-colors duration-200 no-underline"
		>
			Go to home
		</a>
	{:else if invite}
		<h1 class="font-serif text-3xl tracking-tight text-cream mb-2">You've been invited</h1>
		<p class="text-warm-500 text-lg mb-2">
			Join <span class="text-cream">{invite.project_name}</span> as a <span class="text-cream capitalize">{invite.role}</span>
		</p>
		<p class="text-warm-500 text-sm mb-10">
			Invited as {invite.email}
		</p>

		{#if loggedIn}
			<button
				class="border border-accent text-accent px-8 py-3.5 text-sm hover:bg-accent/20 transition-all duration-200 disabled:opacity-50"
				onclick={handleAccept}
				disabled={accepting}
			>
				{accepting ? 'Joining...' : 'Accept Invite'}
			</button>
		{:else}
			<a
				href="/auth/google/login?next=/invite/{token}"
				class="border border-accent text-accent px-8 py-3.5 text-sm hover:bg-accent/20 transition-all duration-200 no-underline"
			>
				Sign in with Google to join
			</a>
		{/if}
	{/if}
</div>
