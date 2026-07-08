<script lang="ts">
	import { untrack } from 'svelte';
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

	let viewportEl: HTMLDivElement | undefined = $state();
	let contentEl: HTMLDivElement | undefined = $state();
	let gridEl: HTMLDivElement | undefined = $state();

	// The map is a pan/zoom canvas: it starts fitted so the whole auditorium
	// is visible on any screen, then pinch (or the buttons) zooms in for
	// precise seat picking. One finger drags a selection rectangle; two
	// fingers pinch-zoom and pan.
	let scale = $state(1);
	let tx = $state(0);
	let ty = $state(0);
	let fitScale = 1;
	const maxScale = 3;

	let painting = $state(false);
	let paintOn = true;
	let anchor: { row: number; col: number } | null = null;
	let baseSelection = new Set<string>();

	const activePointers = new Map<number, { x: number; y: number }>();
	let pinchStart: { dist: number; midX: number; midY: number; scale: number; tx: number; ty: number } | null = null;
	let panStart: { x: number; y: number; tx: number; ty: number } | null = null;

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

	$effect(() => {
		layout;
		if (viewportEl && contentEl) untrack(fitToViewport);
	});

	const viewportHeight = $derived(Math.min(Math.round((rowCount * 23 + 60) * Math.max(scale, fitScale)), 560));

	function fitToViewport() {
		if (!viewportEl || !contentEl) return;
		const vw = viewportEl.clientWidth;
		const cw = contentEl.offsetWidth;
		fitScale = Math.min(1, vw / cw);
		scale = fitScale;
		tx = Math.max(0, (vw - cw * fitScale) / 2);
		ty = 0;
	}

	function zoomAt(cx: number, cy: number, factor: number) {
		const next = clamp(scale * factor, fitScale, maxScale);
		if (next === scale) return;
		tx = cx - ((cx - tx) / scale) * next;
		ty = cy - ((cy - ty) / scale) * next;
		scale = next;
		clampPan();
	}

	function zoomButtons(factor: number) {
		if (!viewportEl) return;
		zoomAt(viewportEl.clientWidth / 2, viewportEl.clientHeight / 2, factor);
	}

	function clampPan() {
		if (!viewportEl || !contentEl) return;
		const vw = viewportEl.clientWidth;
		const vh = viewportEl.clientHeight;
		const cw = contentEl.offsetWidth * scale;
		const ch = contentEl.offsetHeight * scale;
		tx = cw <= vw ? (vw - cw) / 2 : clamp(tx, vw - cw, 0);
		ty = ch <= vh ? Math.max(0, (vh - ch) / 2) : clamp(ty, vh - ch, 0);
	}

	function onViewportPointerDown(e: PointerEvent) {
		activePointers.set(e.pointerId, { x: e.clientX, y: e.clientY });
		if (activePointers.size === 1 && !painting) {
			panStart = { x: e.clientX, y: e.clientY, tx, ty };
		}
		if (activePointers.size === 2) {
			panStart = null;
			if (painting) {
				painting = false;
				anchor = null;
				onChange?.(baseSelection);
			}
			const [a, b] = [...activePointers.values()];
			pinchStart = {
				dist: Math.hypot(a.x - b.x, a.y - b.y),
				midX: (a.x + b.x) / 2,
				midY: (a.y + b.y) / 2,
				scale,
				tx,
				ty
			};
		}
	}

	function onWindowPointerMove(e: PointerEvent) {
		if (activePointers.has(e.pointerId)) {
			activePointers.set(e.pointerId, { x: e.clientX, y: e.clientY });
		}
		if (pinchStart && activePointers.size === 2 && viewportEl) {
			const [a, b] = [...activePointers.values()];
			const rect = viewportEl.getBoundingClientRect();
			const dist = Math.hypot(a.x - b.x, a.y - b.y);
			const midX = (a.x + b.x) / 2 - rect.left;
			const midY = (a.y + b.y) / 2 - rect.top;
			const startMidX = pinchStart.midX - rect.left;
			const startMidY = pinchStart.midY - rect.top;
			const next = clamp(pinchStart.scale * (dist / pinchStart.dist), fitScale, maxScale);
			tx = midX - ((startMidX - pinchStart.tx) / pinchStart.scale) * next;
			ty = midY - ((startMidY - pinchStart.ty) / pinchStart.scale) * next;
			scale = next;
			clampPan();
			return;
		}
		if (painting) {
			movePaint(e);
			return;
		}
		if (panStart && activePointers.size === 1) {
			tx = panStart.tx + (e.clientX - panStart.x);
			ty = panStart.ty + (e.clientY - panStart.y);
			clampPan();
		}
	}

	function onWindowPointerUp(e: PointerEvent) {
		activePointers.delete(e.pointerId);
		if (activePointers.size < 2) pinchStart = null;
		if (activePointers.size === 0) panStart = null;
		endPaint();
	}

	function onWheel(e: WheelEvent) {
		if (!e.ctrlKey || !viewportEl) return;
		e.preventDefault();
		const rect = viewportEl.getBoundingClientRect();
		zoomAt(e.clientX - rect.left, e.clientY - rect.top, e.deltaY < 0 ? 1.15 : 1 / 1.15);
	}

	// Drag = rectangle selection: the block between where the pointer went
	// down and where it is now. Seats are resolved from grid geometry (which
	// reflects the current zoom), so fast drags can't skip seats.
	function startPaint(e: PointerEvent, seatName: string, row: number, col: number) {
		if (readonly || !onChange || activePointers.size > 1) return;
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

<svelte:window onpointermove={onWindowPointerMove} onpointerup={onWindowPointerUp} onpointercancel={onWindowPointerUp} />

<div class="relative">
	<div class="absolute right-1 top-1 z-20 flex gap-1">
		<button
			type="button"
			aria-label="Zoom in"
			onclick={() => zoomButtons(1.4)}
			class="h-8 w-8 rounded-lg border border-line bg-panel-2 text-base text-dim hover:text-marquee">+</button
		>
		<button
			type="button"
			aria-label="Zoom out"
			onclick={() => zoomButtons(1 / 1.4)}
			class="h-8 w-8 rounded-lg border border-line bg-panel-2 text-base text-dim hover:text-marquee">−</button
		>
		<button
			type="button"
			aria-label="Fit whole map"
			onclick={fitToViewport}
			class="h-8 rounded-lg border border-line bg-panel-2 px-2 text-[10px] uppercase tracking-wider text-dim hover:text-marquee">fit</button
		>
	</div>

	<div
		bind:this={viewportEl}
		role="application"
		aria-label="Seat map. Drag to select seats, pinch or use the zoom buttons to zoom."
		onpointerdown={onViewportPointerDown}
		onwheel={onWheel}
		class="touch-none overflow-hidden"
		style="height: {viewportHeight}px; max-height: 70vh;"
	>
		<div
			bind:this={contentEl}
			class="w-max origin-top-left"
			style="transform: translate({tx}px, {ty}px) scale({scale});"
		>
			<div class="mx-auto mb-1 h-3 w-3/4 rounded-[100%] border-t-2 border-marquee shadow-[0_-6px_24px_rgba(242,185,13,0.35)]"></div>
			<p class="mb-6 text-center text-[10px] uppercase tracking-[0.3em] text-dim">screen</p>

			<div class="flex justify-center gap-2">
				<div
					bind:this={gridEl}
					class="grid select-none gap-[3px]"
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
		</div>
	</div>

	<div class="mt-4 flex flex-wrap items-center justify-center gap-x-6 gap-y-2 text-xs text-dim">
		{#if readonly}
			<span class="flex items-center gap-2"><span class="h-3.5 w-3.5 rounded-t bg-emerald-400 shadow-[0_0_8px_rgba(52,211,153,0.7)]"></span> yours, open now</span>
			<span class="flex items-center gap-2"><span class="flex h-3.5 w-3.5 items-center justify-center rounded-t bg-marquee/15 ring-1 ring-marquee/30 text-[8px] text-marquee/50">✕</span> yours, taken</span>
			<span class="flex items-center gap-2"><span class="h-3.5 w-3.5 rounded-t bg-panel-2 ring-1 ring-line"></span> open (unmarked)</span>
			<span class="flex items-center gap-2"><span class="flex h-3.5 w-3.5 items-center justify-center rounded-t bg-[#171310] ring-1 ring-[#292018] text-[8px] text-[#3d3227]">✕</span> taken</span>
		{:else}
			<span class="flex items-center gap-2"><span class="h-3.5 w-3.5 rounded-t bg-panel-2 ring-1 ring-line"></span> open now</span>
			<span class="flex items-center gap-2"><span class="flex h-3.5 w-3.5 items-center justify-center rounded-t bg-[#171310] ring-1 ring-[#292018] text-[8px] text-[#3d3227]">✕</span> taken now</span>
			<span class="flex items-center gap-2"><span class="h-3.5 w-3.5 rounded-t bg-marquee shadow-[0_0_8px_rgba(242,185,13,0.6)]"></span> watching</span>
			<span class="text-dim/70">drag to select a block · pinch or +/− to zoom · two-finger drag to pan</span>
		{/if}
	</div>
</div>
