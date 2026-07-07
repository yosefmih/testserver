<script lang="ts">
	import type { SeatingLayout } from './api';

	let {
		layout,
		selected,
		onChange,
		readonly = false,
		highlighted = new Set<string>(),
		preview = new Set<string>()
	}: {
		layout: SeatingLayout;
		selected: Set<string>;
		onChange?: (next: Set<string>) => void;
		readonly?: boolean;
		highlighted?: Set<string>;
		preview?: Set<string>;
	} = $props();

	let gridEl: HTMLDivElement | undefined = $state();
	let painting = $state(false);
	let paintOn = true;
	let anchor: { row: number; col: number } | null = null;
	let baseSelection = new Set<string>();

	const visibleSeats = $derived(layout.seats.filter((s) => s.shouldDisplay && s.name !== ''));
	const rowLabels = $derived.by(() => {
		const byRow = new Map<number, string>();
		for (const s of visibleSeats) {
			const letter = s.name.replace(/[0-9]/g, '');
			if (letter && !byRow.has(s.row)) byRow.set(s.row, letter);
		}
		return byRow;
	});
	const rowCount = $derived(Math.max(...visibleSeats.map((s) => s.row)));

	// Drag = rectangle selection: the block between where the pointer went
	// down and where it is now. Seats are resolved from grid geometry, not
	// pointerenter events, so fast drags can't skip seats.
	function startPaint(e: PointerEvent, seatName: string, row: number, col: number) {
		if (readonly || !onChange) return;
		e.preventDefault();
		painting = true;
		paintOn = !selected.has(seatName);
		anchor = { row, col };
		baseSelection = new Set(selected);
		applyRect(row, col);
	}

	function movePaint(e: PointerEvent) {
		if (!painting || !anchor || !gridEl) return;
		const rect = gridEl.getBoundingClientRect();
		const col = clamp(Math.ceil(((e.clientX - rect.left) / rect.width) * layout.columns), 1, layout.columns);
		const row = clamp(Math.ceil(((e.clientY - rect.top) / rect.height) * rowCount), 1, rowCount);
		applyRect(row, col);
	}

	function applyRect(row: number, col: number) {
		if (!anchor || !onChange) return;
		const r1 = Math.min(anchor.row, row);
		const r2 = Math.max(anchor.row, row);
		const c1 = Math.min(anchor.col, col);
		const c2 = Math.max(anchor.col, col);
		const next = new Set(baseSelection);
		for (const s of visibleSeats) {
			if (s.row >= r1 && s.row <= r2 && s.column >= c1 && s.column <= c2) {
				if (paintOn) next.add(s.name);
				else next.delete(s.name);
			}
		}
		onChange(next);
	}

	function endPaint() {
		painting = false;
		anchor = null;
	}

	function clamp(v: number, lo: number, hi: number) {
		return Math.max(lo, Math.min(hi, v));
	}
</script>

<svelte:window onpointermove={movePaint} onpointerup={endPaint} onpointercancel={endPaint} />

<div class="overflow-x-auto">
	<div class="min-w-[640px]">
		<div class="mx-auto mb-1 h-3 w-3/4 rounded-[100%] border-t-2 border-marquee shadow-[0_-6px_24px_rgba(242,185,13,0.35)]"></div>
		<p class="mb-6 text-center text-[10px] uppercase tracking-[0.3em] text-dim">screen</p>

		<div class="flex justify-center gap-2">
			<div
				bind:this={gridEl}
				class="grid touch-none select-none gap-[3px]"
				style="grid-template-columns: repeat({layout.columns}, minmax(0, 1fr)); direction: ltr;"
			>
				{#each visibleSeats as seat (seat.name)}
					{@const isSelected = selected.has(seat.name)}
					{@const isHighlighted = highlighted.has(seat.name)}
					{@const isPreviewed = preview.has(seat.name)}
					<button
						type="button"
						title="{seat.name}{seat.available ? '' : ' — taken right now'}{seat.type === 'Wheelchair' ? ' (wheelchair space)' : ''}"
						aria-pressed={isSelected}
						onpointerdown={(e) => startPaint(e, seat.name, seat.row, seat.column)}
						style="grid-column: {seat.column}; grid-row: {seat.row};"
						class="flex h-5 w-5 items-center justify-center rounded-t-md text-[8px] font-semibold transition-all duration-100
							{isHighlighted
							? 'z-10 scale-150 bg-white text-ink ring-2 ring-white shadow-[0_0_14px_rgba(255,255,255,0.9)]'
							: isPreviewed
							? 'z-10 scale-125 bg-emerald-400 text-emerald-950 shadow-[0_0_10px_rgba(52,211,153,0.8)]'
							: readonly && isSelected && seat.available
								? 'bg-emerald-400 text-emerald-950 shadow-[0_0_10px_rgba(52,211,153,0.7)]'
								: readonly && isSelected
									? 'bg-marquee/15 text-marquee/50 ring-1 ring-marquee/30'
									: isSelected
										? 'scale-110 bg-marquee text-ink shadow-[0_0_10px_rgba(242,185,13,0.6)]'
										: seat.available
											? 'bg-panel-2 text-transparent ring-1 ring-line hover:bg-line hover:text-dim'
											: 'bg-[#171310] text-transparent ring-1 ring-[#292018] hover:text-dim'}"
					>
						{#if seat.type === 'Wheelchair'}
							<span class="{isSelected || isHighlighted ? 'text-inherit' : 'text-sky-700'} text-[9px]">♿</span>
						{:else if isHighlighted || isPreviewed}
							{seat.name}
						{:else if readonly && isSelected}
							{#if seat.available}{seat.name}{:else}✕{/if}
						{:else if isSelected}
							{seat.name}
						{:else if !seat.available}
							<span class="text-[#3d3227]">✕</span>
						{/if}
					</button>
				{/each}
			</div>
			<div class="flex flex-col justify-between py-0.5 text-[9px] text-dim">
				{#each [...rowLabels.entries()].sort((a, b) => a[0] - b[0]) as [row, letter] (row)}
					<span class="flex h-5 items-center">{letter}</span>
				{/each}
			</div>
		</div>

		<div class="mt-6 flex flex-wrap items-center justify-center gap-x-6 gap-y-2 text-xs text-dim">
			{#if readonly}
				<span class="flex items-center gap-2"><span class="h-3.5 w-3.5 rounded-t bg-emerald-400 shadow-[0_0_8px_rgba(52,211,153,0.7)]"></span> yours, open now</span>
				<span class="flex items-center gap-2"><span class="flex h-3.5 w-3.5 items-center justify-center rounded-t bg-marquee/15 ring-1 ring-marquee/30 text-[8px] text-marquee/50">✕</span> yours, taken</span>
				<span class="flex items-center gap-2"><span class="h-3.5 w-3.5 rounded-t bg-panel-2 ring-1 ring-line"></span> open (unmarked)</span>
				<span class="flex items-center gap-2"><span class="flex h-3.5 w-3.5 items-center justify-center rounded-t bg-[#171310] ring-1 ring-[#292018] text-[8px] text-[#3d3227]">✕</span> taken</span>
			{:else}
				<span class="flex items-center gap-2"><span class="h-3.5 w-3.5 rounded-t bg-panel-2 ring-1 ring-line"></span> open now</span>
				<span class="flex items-center gap-2"><span class="flex h-3.5 w-3.5 items-center justify-center rounded-t bg-[#171310] ring-1 ring-[#292018] text-[8px] text-[#3d3227]">✕</span> taken now</span>
				<span class="flex items-center gap-2"><span class="h-3.5 w-3.5 rounded-t bg-marquee shadow-[0_0_8px_rgba(242,185,13,0.6)]"></span> watching</span>
				<span class="text-dim/70">tip: drag any rectangle of seats to select the block</span>
			{/if}
		</div>
	</div>
</div>
