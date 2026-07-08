<script lang="ts">
	import { api, fmtShowtime, amcBookingURL } from '$lib/api';
	import type { Watch } from '$lib/api';

	let email = $state(localStorage.getItem('seatwatch-email') ?? '');
	let watches = $state<Watch[] | null>(null);
	let error = $state('');
	let loading = $state(false);
	let alertsEnabled = $state(true);

	$effect(() => {
		api.config().then((c) => (alertsEnabled = c.alertsEnabled)).catch(() => {});
	});

	async function load() {
		if (!email) return;
		loading = true;
		error = '';
		localStorage.setItem('seatwatch-email', email);
		try {
			watches = await api.listWatches(email);
		} catch (e) {
			error = (e as Error).message;
		} finally {
			loading = false;
		}
	}

	async function remove(id: number) {
		await api.deleteWatch(id);
		watches = watches?.filter((w) => w.id !== id) ?? null;
	}

	if (email) load();
</script>

<h1 class="mb-6 font-display text-3xl tracking-wide">MY WATCHES</h1>

{#if !alertsEnabled}
	<p class="mb-6 max-w-lg rounded-lg border border-line bg-panel px-4 py-3 text-sm text-dim">
		Email alerts are not enabled on this deployment yet — existing watches are listed below but new
		ones can't be created and no emails are sent.
	</p>
{/if}

<form
	class="mb-8 flex max-w-md gap-3"
	onsubmit={(e) => {
		e.preventDefault();
		load();
	}}
>
	<input
		type="email"
		required
		placeholder="you@example.com"
		bind:value={email}
		class="min-w-0 flex-1 rounded-lg border border-line bg-panel px-4 py-2.5 placeholder:text-dim/50 focus:border-marquee focus:outline-none"
	/>
	<button
		type="submit"
		class="rounded-lg border border-marquee px-5 py-2.5 font-semibold text-marquee hover:bg-marquee-soft"
		>{loading ? '…' : 'Look up'}</button
	>
</form>

{#if error}
	<p class="text-red-400">{error}</p>
{:else if watches !== null}
	{#if watches.length === 0}
		<p class="text-dim">No active watches for {email}. <a href="/" class="text-marquee">Create one →</a></p>
	{:else}
		<ul class="space-y-4">
			{#each watches as watch (watch.id)}
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
							onclick={() => remove(watch.id)}
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
{/if}
