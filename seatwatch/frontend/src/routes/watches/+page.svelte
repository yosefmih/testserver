<script lang="ts">
	import {
		api,
		fmtShowtime,
		amcBookingURL,
		getStoredWatchTokens,
		addStoredWatchToken,
		removeStoredWatchToken
	} from '$lib/api';
	import type { Watch } from '$lib/api';

	// Watches are shown by private token only — remembered locally on this
	// browser, or supplied via ?token= from an alert email. There is no
	// email-based lookup: that would let anyone view someone else's watch
	// just by knowing or guessing their address.
	let watches = $state<Watch[]>([]);
	let loading = $state(true);
	let error = $state('');
	let alertsEnabled = $state(true);

	$effect(() => {
		api
			.config()
			.then((c) => (alertsEnabled = c.alertsEnabled))
			.catch(() => {});
	});

	async function loadAll() {
		loading = true;
		error = '';
		const linkToken = new URLSearchParams(location.search).get('token');
		if (linkToken) {
			addStoredWatchToken(linkToken);
			history.replaceState(null, '', '/watches');
		}
		const tokens = getStoredWatchTokens();
		const results = await Promise.all(
			tokens.map((t) =>
				api.getWatch(t).catch(() => {
					removeStoredWatchToken(t);
					return null;
				})
			)
		);
		watches = results.filter((w): w is Watch => w !== null);
		loading = false;
	}

	async function remove(token: string) {
		await api.deleteWatch(token);
		removeStoredWatchToken(token);
		watches = watches.filter((w) => w.token !== token);
	}

	loadAll();
</script>

<h1 class="mb-6 font-display text-3xl tracking-wide">MY WATCHES</h1>

{#if !alertsEnabled}
	<p class="mb-6 max-w-lg rounded-lg border border-line bg-panel px-4 py-3 text-sm text-dim">
		Email alerts are not enabled on this deployment yet — existing watches are listed below but new
		ones can't be created and no emails are sent.
	</p>
{/if}

{#if loading}
	<p class="animate-pulse text-dim">Loading your watches…</p>
{:else if error}
	<p class="text-red-400">{error}</p>
{:else if watches.length === 0}
	<p class="text-dim">
		No watches remembered on this browser yet. <a href="/" class="text-marquee">Create one →</a> or open
		the link from an alert email to add it here.
	</p>
{:else}
	<ul class="space-y-4">
		{#each watches as watch (watch.token)}
			<li class="rounded-xl border border-line bg-panel p-5">
				<div class="mb-2 flex items-start justify-between gap-4">
					<div>
						<div class="font-display text-xl tracking-wide">{watch.movieTitle}</div>
						<div class="text-xs text-dim">
							{#if watch.format}{watch.format} · {/if}{watch.numSeats} ticket{watch.numSeats === 1
								? ''
								: 's'}{#if watch.dateFrom || watch.dateTo}
								· {watch.dateFrom || 'any'} → {watch.dateTo || 'any'}{/if}
							· watching {watch.seats.length} seats ({watch.seats.slice(0, 8).join(', ')}{watch
								.seats.length > 8
								? '…'
								: ''})
						</div>
					</div>
					<button
						type="button"
						onclick={() => remove(watch.token)}
						class="text-xs text-dim underline-offset-4 hover:text-red-400 hover:underline">stop watching</button
					>
				</div>

				{#if watch.matches && watch.matches.length > 0}
					<ul class="mt-3 space-y-2">
						{#each watch.matches as match (match.showtimeId)}
							<li class="flex flex-wrap items-center justify-between gap-2 rounded-lg bg-panel-2 px-4 py-2.5">
								<div class="text-sm">
									<span class="font-semibold text-marquee">● {fmtShowtime(match.showAt)}</span>
									<span class="ml-2 text-xs text-dim">best: {match.seatGroups[0].join(', ')}</span>
								</div>
								<a
									href={amcBookingURL(match.showtimeId)}
									target="_blank"
									rel="noreferrer"
									class="text-sm font-semibold text-marquee underline-offset-4 hover:underline"
									>book ↗</a
								>
							</li>
						{/each}
					</ul>
				{:else}
					<p class="mt-2 text-sm text-dim">no matching screenings yet — we're checking every few minutes</p>
				{/if}
			</li>
		{/each}
	</ul>
{/if}
