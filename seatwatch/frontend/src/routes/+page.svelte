<script lang="ts">
	import { api, fmtShowtime, amcBookingURL, localDate } from '$lib/api';
	import type { Showtime, SeatingLayout, ScreeningResult, Watch } from '$lib/api';
	import SeatMap from '$lib/SeatMap.svelte';

	type Movie = {
		slug: string;
		title: string;
		formats: string[];
		showtimes: Showtime[];
	};

	let showtimes = $state<Showtime[]>([]);
	let loadError = $state('');
	let loading = $state(true);
	let alertsEnabled = $state(false);

	$effect(() => {
		api.config().then((c) => (alertsEnabled = c.alertsEnabled)).catch(() => {});
	});

	let selectedMovie = $state<Movie | null>(null);
	let selectedFormat = $state<string | null>(null);
	let layout = $state<SeatingLayout | null>(null);
	let layoutShowtime = $state<Showtime | null>(null);
	let layoutLoading = $state(false);
	let layoutStatus = $state('');
	let selectedSeats = $state(new Set<string>());
	let numSeats = $state(2);
	let dateFrom = $state('');
	let dateTo = $state('');

	let results = $state<ScreeningResult[] | null>(null);
	let pendingScans = $state(0);
	let evaluating = $state(false);
	let evalError = $state('');
	let evalCounter = 0;
	let debounceTimer: ReturnType<typeof setTimeout> | undefined;

	let email = $state(localStorage.getItem('seatwatch-email') ?? '');
	let submitting = $state(false);
	let submitError = $state('');
	let createdWatch = $state<Watch | null>(null);

	let expandedMatch = $state<number | null>(null);
	let matchLayouts = $state<Record<number, SeatingLayout>>({});
	let highlightedSeats = $state(new Set<string>());
	let previewSeats = $state(new Set<string>());
	let previewToken = 0;

	function highlight(seats: string[]) {
		highlightedSeats = new Set(seats);
	}

	// Hovering a match row previews, on the main map, every marked seat that
	// is open at that screening.
	async function previewScreening(showtimeId: number) {
		const token = ++previewToken;
		let screeningLayout = matchLayouts[showtimeId];
		if (!screeningLayout) {
			try {
				screeningLayout = await api.seatMap(showtimeId);
				matchLayouts = { ...matchLayouts, [showtimeId]: screeningLayout };
			} catch {
				return;
			}
		}
		if (token !== previewToken) return;
		previewSeats = new Set(
			screeningLayout.seats
				.filter((s) => s.shouldDisplay && s.available && selectedSeats.has(s.name))
				.map((s) => s.name)
		);
	}

	function clearPreview() {
		previewToken++;
		previewSeats = new Set();
	}

	async function toggleMatchMap(showtimeId: number) {
		if (expandedMatch === showtimeId) {
			expandedMatch = null;
			return;
		}
		expandedMatch = showtimeId;
		if (!matchLayouts[showtimeId]) {
			try {
				matchLayouts = { ...matchLayouts, [showtimeId]: await api.seatMap(showtimeId) };
			} catch {
				expandedMatch = null;
			}
		}
	}

	const movies = $derived.by(() => {
		const bySlug = new Map<string, Movie>();
		for (const st of showtimes) {
			let m = bySlug.get(st.movieSlug);
			if (!m) {
				m = { slug: st.movieSlug, title: st.movieTitle, formats: [], showtimes: [] };
				bySlug.set(st.movieSlug, m);
			}
			m.showtimes.push(st);
			if (st.format && !m.formats.includes(st.format)) m.formats.push(st.format);
		}
		return [...bySlug.values()].sort((a, b) => b.showtimes.length - a.showtimes.length);
	});

	function inDateRange(showAt: string): boolean {
		const d = localDate(showAt);
		if (dateFrom && d < dateFrom) return false;
		if (dateTo && d > dateTo) return false;
		return true;
	}

	const screeningCount = $derived(
		selectedMovie === null
			? 0
			: selectedMovie.showtimes.filter(
					(st) => (selectedFormat === null || st.format === selectedFormat) && inDateRange(st.showAt)
				).length
	);
	const openNow = $derived(results?.filter((r) => r.matched) ?? []);
	const checkedCount = $derived(results?.length ?? 0);

	$effect(() => {
		loadShowtimes();
	});

	async function loadShowtimes(attempt = 0) {
		try {
			showtimes = await api.showtimes();
			loading = false;
		} catch (e) {
			const msg = (e as Error).message;
			if (/warming up/.test(msg) && attempt < 60) {
				setTimeout(() => loadShowtimes(attempt + 1), 3000);
			} else {
				loadError = msg;
				loading = false;
			}
		}
	}

	// Re-check availability (debounced) whenever the selection changes.
	$effect(() => {
		const movie = selectedMovie;
		const format = selectedFormat;
		const seats = [...selectedSeats];
		const n = numSeats;
		const from = dateFrom;
		const to = dateTo;
		clearTimeout(debounceTimer);
		if (!movie || seats.length === 0) {
			results = null;
			return;
		}
		debounceTimer = setTimeout(() => runEvaluate(movie, format, seats, n, from, to), 400);
	});

	async function runEvaluate(movie: Movie, format: string | null, seats: string[], n: number, from: string, to: string) {
		const ticket = ++evalCounter;
		evaluating = true;
		evalError = '';
		try {
			const res = await api.evaluate({
				movieSlug: movie.slug,
				format: format ?? '',
				numSeats: n,
				seats,
				dateFrom: from,
				dateTo: to
			});
			if (ticket === evalCounter) {
				results = res.results;
				pendingScans = res.pending;
			}
		} catch (e) {
			if (ticket === evalCounter) evalError = (e as Error).message;
		} finally {
			if (ticket === evalCounter) evaluating = false;
		}
	}

	async function pickMovie(movie: Movie) {
		selectedMovie = movie;
		const imax70 = movie.formats.find((f) => /imax\s*70\s*mm/i.test(f));
		selectedFormat = imax70 ?? (movie.formats.length === 1 ? movie.formats[0] : null);
		createdWatch = null;
		await loadSeatMap();
		document.getElementById('step-seats')?.scrollIntoView({ behavior: 'smooth' });
	}

	async function pickFormat(format: string | null) {
		selectedFormat = format;
		await loadSeatMap();
	}

	async function loadSeatMap() {
		layout = null;
		selectedSeats = new Set();
		results = null;
		const candidates = selectedMovie?.showtimes.filter(
			(st) => selectedFormat === null || st.format === selectedFormat
		);
		if (!candidates || candidates.length === 0) return;
		layoutShowtime = candidates[0];
		layoutLoading = true;
		layoutStatus = '';
		try {
			for (let attempt = 0; ; attempt++) {
				try {
					layout = await api.seatMap(candidates[0].id);
					return;
				} catch (e) {
					if (!/warming up|not scanned yet/.test((e as Error).message) || attempt >= 100) throw e;
					layoutStatus = `The server is still scanning AMC and hasn't reached this screening's seat map yet — this takes a few minutes after a fresh deploy. Retrying automatically (${(attempt + 1) * 3}s)…`;
					await new Promise((r) => setTimeout(r, 3000));
				}
			}
		} catch (e) {
			evalError = `couldn't load the seat map: ${(e as Error).message}`;
		} finally {
			layoutLoading = false;
			layoutStatus = '';
		}
	}

	function onSeatsChange(next: Set<string>) {
		selectedSeats = next;
	}

	async function createAlert() {
		if (!selectedMovie) return;
		submitting = true;
		submitError = '';
		localStorage.setItem('seatwatch-email', email);
		try {
			const res = await api.createWatch({
				email,
				movieSlug: selectedMovie.slug,
				movieTitle: selectedMovie.title,
				format: selectedFormat ?? '',
				numSeats,
				seats: [...selectedSeats],
				dateFrom,
				dateTo
			});
			createdWatch = res.watch;
		} catch (e) {
			submitError = (e as Error).message;
		} finally {
			submitting = false;
		}
	}
</script>

<p class="mb-10 max-w-xl text-lg text-dim">
	Pick a movie, mark the seats you'd take, and instantly see which screenings have them open — or
	get emailed when they free up.
</p>

<!-- Step 1: movie -->
<section class="mb-12">
	<h2 class="mb-4 font-display text-3xl tracking-wide">
		<span class="mr-2 text-marquee">1</span> WHICH MOVIE?
	</h2>

	{#if loading}
		<p class="animate-pulse text-dim">Loading this week's screenings at Lincoln Square…</p>
	{:else if loadError}
		<p class="rounded border border-red-900 bg-red-950/40 p-4 text-red-300">
			Couldn't reach AMC: {loadError}
		</p>
	{:else}
		<div class="grid gap-2 sm:grid-cols-2">
			{#each movies as movie (movie.slug)}
				<button
					type="button"
					onclick={() => pickMovie(movie)}
					class="rounded-lg border p-4 text-left transition-colors
						{selectedMovie?.slug === movie.slug
						? 'border-marquee bg-marquee-soft'
						: 'border-line bg-panel hover:border-dim'}"
				>
					<div class="mb-1 font-semibold">{movie.title}</div>
					<div class="text-xs text-dim">
						{movie.showtimes.length} showtime{movie.showtimes.length === 1 ? '' : 's'}
						{#if movie.formats.length}· {movie.formats.join(' · ')}{/if}
					</div>
				</button>
			{/each}
		</div>

		{#if selectedMovie && selectedMovie.formats.length > 1}
			<div class="mt-4 flex flex-wrap items-center gap-2">
				<span class="text-sm text-dim">format:</span>
				<button
					type="button"
					onclick={() => pickFormat(null)}
					class="rounded-full border px-3 py-1 text-sm {selectedFormat === null
						? 'border-marquee bg-marquee text-ink'
						: 'border-line text-dim hover:border-dim'}">any</button
				>
				{#each selectedMovie.formats as format (format)}
					<button
						type="button"
						onclick={() => pickFormat(format)}
						class="rounded-full border px-3 py-1 text-sm {selectedFormat === format
							? 'border-marquee bg-marquee text-ink'
							: 'border-line text-dim hover:border-dim'}">{format}</button
					>
				{/each}
			</div>
		{/if}
	{/if}
</section>

<!-- Step 2: seats + live availability -->
{#if selectedMovie}
	<section id="step-seats" class="mb-12">
		<h2 class="mb-1 font-display text-3xl tracking-wide">
			<span class="mr-2 text-marquee">2</span> WHICH SEATS WOULD YOU TAKE?
		</h2>
		<p class="mb-6 text-sm text-dim">
			Click or drag over every seat you'd be happy with — including ones taken right now.
		</p>

		{#if layoutLoading}
			<div class="py-12 text-center">
				<p class="animate-pulse text-dim">Loading the auditorium…</p>
				{#if layoutStatus}
					<p class="mx-auto mt-3 max-w-md text-xs text-dim/80">{layoutStatus}</p>
				{/if}
			</div>
		{:else if layout}
			<div class="rounded-xl border border-line bg-panel p-6">
				<SeatMap {layout} selected={selectedSeats} onChange={onSeatsChange} highlighted={highlightedSeats} preview={previewSeats} />
				{#if layoutShowtime}
					<p class="mt-4 text-center text-xs text-dim/80">
						open/taken shown here is for the {fmtShowtime(layoutShowtime.showAt)} screening — every
						screening below is checked against its own seat map ("view seats" to see any of them)
					</p>
				{/if}
			</div>

			<div class="mt-6 flex flex-wrap items-center gap-x-8 gap-y-4">
				<div class="flex items-center gap-3">
					<span class="text-sm text-dim">tickets:</span>
					<div class="flex items-center rounded-lg border border-line">
						<button
							type="button"
							class="px-3 py-1.5 text-lg text-dim hover:text-marquee disabled:opacity-30"
							disabled={numSeats <= 1}
							onclick={() => (numSeats -= 1)}>−</button
						>
						<span class="w-8 text-center font-semibold">{numSeats}</span>
						<button
							type="button"
							class="px-3 py-1.5 text-lg text-dim hover:text-marquee disabled:opacity-30"
							disabled={numSeats >= 10}
							onclick={() => (numSeats += 1)}>+</button
						>
					</div>
					<span class="text-xs text-dim">seated together</span>
				</div>
				<div class="flex flex-wrap items-center gap-2">
					<span class="text-sm text-dim">dates:</span>
					<input
						type="date"
						bind:value={dateFrom}
						max={dateTo || undefined}
						class="w-[8.6rem] rounded-lg border border-line bg-panel px-2 py-1.5 text-sm [color-scheme:dark] focus:border-marquee focus:outline-none"
					/>
					<span class="text-dim">–</span>
					<input
						type="date"
						bind:value={dateTo}
						min={dateFrom || undefined}
						class="w-[8.6rem] rounded-lg border border-line bg-panel px-2 py-1.5 text-sm [color-scheme:dark] focus:border-marquee focus:outline-none"
					/>
					{#if dateFrom || dateTo}
						<button
							type="button"
							onclick={() => {
								dateFrom = '';
								dateTo = '';
							}}
							class="text-xs text-dim underline-offset-4 hover:text-marquee hover:underline">any date</button
						>
					{:else}
						<span class="text-xs text-dim/70">all upcoming</span>
					{/if}
				</div>
				<div class="text-sm text-dim">{selectedSeats.size} seat{selectedSeats.size === 1 ? '' : 's'} marked</div>
			</div>
		{/if}
	</section>

	<!-- Live availability -->
	{#if selectedSeats.size > 0}
		<section class="mb-12">
			<h2 class="mb-4 font-display text-3xl tracking-wide">
				<span class="mr-2 text-marquee">3</span> OPEN RIGHT NOW
				{#if evaluating}<span class="ml-3 inline-block animate-pulse align-middle text-sm font-sans normal-case text-dim">checking {screeningCount} screenings…</span>{/if}
			</h2>

			{#if evalError}
				<p class="rounded border border-red-900 bg-red-950/40 p-4 text-sm text-red-300">{evalError}</p>
			{:else if results === null && evaluating}
				<div class="space-y-2">
					{#each [0, 1, 2] as i (i)}
						<div class="h-14 animate-pulse rounded-lg bg-panel" style="animation-delay: {i * 150}ms"></div>
					{/each}
				</div>
			{:else if results !== null}
				{#if openNow.length > 0}
					<ul class="space-y-2">
						{#each openNow as r (r.showtimeId)}
							<li
								class="rounded-lg border border-marquee/40 bg-panel px-4 py-3"
								onmouseenter={() => previewScreening(r.showtimeId)}
								onmouseleave={clearPreview}
							>
								<div class="flex flex-wrap items-center justify-between gap-2">
									<div>
										<div class="font-semibold">{fmtShowtime(r.showAt)}</div>
										<div class="flex flex-wrap items-center gap-x-2 gap-y-1 text-xs text-dim">
											{#if r.format}<span>{r.format} ·</span>{/if}
											<span class="text-marquee">{r.openSeats} of your seats open</span>
											<span>· {r.groupCount} way{r.groupCount === 1 ? '' : 's'} to sit {numSeats} together ·</span>
											{#each r.seatGroups as group (group.join())}
												<button
													type="button"
													onmouseenter={() => highlight(group)}
													onmouseleave={() => highlight([])}
													class="rounded border border-line px-1.5 py-0.5 text-dim hover:border-marquee hover:text-marquee"
													>{group.join('·')}</button
												>
											{/each}
										</div>
									</div>
									<div class="flex items-center gap-3">
										<button
											type="button"
											onclick={() => toggleMatchMap(r.showtimeId)}
											class="text-xs text-dim underline-offset-4 hover:text-marquee hover:underline"
											>{expandedMatch === r.showtimeId ? 'hide seats' : 'view seats'}</button
										>
										<a
											href={amcBookingURL(r.showtimeId)}
											target="_blank"
											rel="noreferrer"
											class="rounded bg-marquee px-4 py-1.5 text-sm font-semibold text-ink hover:brightness-110"
											>book on AMC ↗</a
										>
									</div>
								</div>
								{#if expandedMatch === r.showtimeId}
									<div class="mt-4 border-t border-line pt-4">
										{#if matchLayouts[r.showtimeId]}
											<SeatMap layout={matchLayouts[r.showtimeId]} selected={selectedSeats} readonly highlighted={highlightedSeats} />
										{:else}
											<p class="animate-pulse py-4 text-center text-xs text-dim">loading this screening's seat map…</p>
										{/if}
									</div>
								{/if}
							</li>
						{/each}
					</ul>
					{#if checkedCount > openNow.length}
						<p class="mt-3 text-xs text-dim">
							{checkedCount - openNow.length} other screening{checkedCount - openNow.length === 1 ? '' : 's'} checked — your seats aren't free there.
						</p>
					{/if}
				{:else}
					<div class="rounded-lg border border-line bg-panel px-5 py-4 text-sm text-dim">
						None of the {checkedCount} upcoming screenings have {numSeats} of your seats together right
						now{numSeats > 1 ? ' (adjacent)' : ''}. Mark more seats, or set an alert below.
					</div>
				{/if}
				{#if pendingScans > 0}
					<p class="mt-3 animate-pulse text-xs text-dim">
						{pendingScans} screening{pendingScans === 1 ? '' : 's'} still being scanned in the background —
						results will fill in as the sweep completes.
					</p>
				{/if}
			{/if}
		</section>

		<!-- Alert opt-in -->
		{#if alertsEnabled}
		<section class="mb-12">
			<h2 class="mb-1 font-display text-3xl tracking-wide">
				<span class="mr-2 text-marquee">4</span> EMAIL ME WHEN MORE OPEN UP
			</h2>
			<p class="mb-4 text-sm text-dim">
				Seats free up when people refund. We re-check every few minutes and email you the moment a
				screening gets {numSeats} of your seats together.
			</p>

			{#if createdWatch}
				<div class="rounded-lg border border-marquee/40 bg-panel px-5 py-4">
					<span class="font-semibold text-marquee">Watching.</span>
					<span class="text-sm text-dim">
						We'll email {createdWatch.email} about {createdWatch.movieTitle}
						{#if createdWatch.format}({createdWatch.format}){/if}.
						<a href="/watches" class="text-marquee underline-offset-4 hover:underline">manage watches</a>
					</span>
				</div>
			{:else}
				<form
					class="flex max-w-md flex-wrap gap-3"
					onsubmit={(e) => {
						e.preventDefault();
						createAlert();
					}}
				>
					<input
						type="email"
						required
						placeholder="you@example.com"
						bind:value={email}
						class="min-w-64 flex-1 rounded-lg border border-line bg-panel px-4 py-2.5 placeholder:text-dim/50 focus:border-marquee focus:outline-none"
					/>
					<button
						type="submit"
						disabled={submitting || !email || selectedSeats.size < numSeats}
						class="rounded-lg bg-marquee px-6 py-2.5 font-semibold text-ink transition hover:brightness-110 disabled:opacity-40"
					>
						{submitting ? 'saving…' : 'Alert me'}
					</button>
				</form>
				{#if selectedSeats.size < numSeats}
					<p class="mt-2 text-xs text-dim">mark at least {numSeats} seats first</p>
				{/if}
				{#if submitError}
					<p class="mt-3 text-sm text-red-400">{submitError}</p>
				{/if}
			{/if}
		</section>
		{/if}
	{/if}
{/if}
