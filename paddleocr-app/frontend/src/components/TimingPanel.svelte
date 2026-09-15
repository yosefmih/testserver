<script>
  import { duration } from '../lib/format.js';

  let { job } = $props();

  const STAGES = [
    { key: 'split', label: 'split PDF', color: 'var(--line-strong)' },
    { key: 'upload', label: 'upload chunk', color: 'var(--muted)' },
    { key: 'ocr', label: 'OCR round trip', color: 'var(--accent)' },
    { key: 'store', label: 'store pages', color: 'var(--done)' },
  ];

  const t = (iso) => (iso ? new Date(iso).getTime() : null);
  const clock = (iso) => (iso ? new Date(iso).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' }) : '–');

  const origin = $derived(t(job.created_at));
  const end = $derived(t(job.finished_at) ?? Date.now());
  const span = $derived(Math.max(1000, end - origin));
  const pct = (ms) => `${(ms / span) * 100}%`;

  const rows = $derived(
    job.chunks.map((c) => {
      const start = t(c.started_at);
      const stop = t(c.finished_at) ?? (start ? Date.now() : null);
      const total = start && stop ? (stop - start) / 1000 : null;
      const known = STAGES.reduce((sum, s) => sum + (c.timings?.[s.key] ?? 0), 0);
      return { chunk: c, start, stop, total, known, other: total != null ? Math.max(0, total - known) : 0 };
    })
  );

  const recognition = $derived.by(() => {
    const starts = rows.map((r) => r.start).filter(Boolean);
    const stops = rows.map((r) => r.stop).filter(Boolean);
    return starts.length ? { start: Math.min(...starts), stop: Math.max(...stops) } : null;
  });

  const phases = $derived.by(() => {
    const list = [{ label: 'Queued before start', seconds: job.metrics.queued_seconds, from: origin, to: t(job.started_at) }];
    if (recognition) list.push({ label: 'Recognition (all requests)', seconds: (recognition.stop - recognition.start) / 1000, from: recognition.start, to: recognition.stop });
    if (job.timings?.assemble != null) list.push({ label: job.assembled_with === 'restructure-pages' ? 'Restructure pages' : 'Concatenate pages', seconds: job.timings.assemble });
    if (job.timings?.archive != null) list.push({ label: 'Write markdown, page index and zip', seconds: job.timings.archive });
    list.push({ label: 'Total (submitted → finished)', seconds: (end - origin) / 1000, from: origin, to: end });
    return list;
  });

  const ticks = $derived.by(() => {
    const seconds = span / 1000;
    const step = seconds <= 120 ? 15 : seconds <= 600 ? 60 : seconds <= 1800 ? 300 : 600;
    const out = [];
    for (let s = 0; s <= seconds; s += step) out.push(s);
    return out;
  });
</script>

<section class="timing">
  <div class="gantt">
    <div class="axis">
      {#each ticks as s}
        <span style={`left:${pct(s * 1000)}`}>{duration(s)}</span>
      {/each}
    </div>
    {#each rows as row (row.chunk.index)}
      <div class="row">
        <div class="label mono">#{row.chunk.index + 1} <span class="muted">p{row.chunk.first_page}–{row.chunk.last_page}</span></div>
        <div class="track">
          {#if row.start}
            <div class={`bar ${row.chunk.status}`} style={`left:${pct(row.start - origin)};width:${pct(Math.max(row.stop - row.start, 800))}`} title={`${duration(row.total)} · ${clock(row.chunk.started_at)} → ${clock(row.chunk.finished_at)}`}>
              {#if row.known > 0 && row.total}
                {#each STAGES as stage}
                  {#if row.chunk.timings?.[stage.key]}
                    <span style={`flex:${row.chunk.timings[stage.key]};background:${stage.color}`} title={`${stage.label}: ${duration(row.chunk.timings[stage.key])}`}></span>
                  {/if}
                {/each}
                {#if row.other > 0.05}<span style={`flex:${row.other};background:transparent`}></span>{/if}
              {/if}
            </div>
          {:else}
            <div class="bar queued" style="left:0;width:0"></div>
          {/if}
        </div>
      </div>
    {/each}
    <div class="legend">
      {#each STAGES as stage}
        <span><i style={`background:${stage.color}`}></i>{stage.label}</span>
      {/each}
      <span><i class="failed"></i>failed</span>
    </div>
  </div>

  <div class="tables">
    <table>
      <thead>
        <tr><th>Request</th><th>Pages</th><th>Started</th><th>Ended</th><th class="num">Split</th><th class="num">Upload</th><th class="num">OCR</th><th class="num">Store</th><th class="num">Total</th><th class="num">Attempts</th><th>Status</th></tr>
      </thead>
      <tbody>
        {#each rows as row (row.chunk.index)}
          <tr>
            <td class="mono">#{row.chunk.index + 1}</td>
            <td class="mono">{row.chunk.first_page}–{row.chunk.last_page}</td>
            <td class="mono">{clock(row.chunk.started_at)}</td>
            <td class="mono">{clock(row.chunk.finished_at)}</td>
            {#each STAGES as stage}
              <td class="num mono">{row.chunk.timings?.[stage.key] != null ? duration(row.chunk.timings[stage.key]) : '–'}</td>
            {/each}
            <td class="num mono">{duration(row.total)}</td>
            <td class="num mono">{row.chunk.attempts}</td>
            <td><span class={`pill ${row.chunk.status}`}>{row.chunk.status}</span>{#if row.chunk.error}<div class="error">{row.chunk.error}</div>{/if}</td>
          </tr>
        {/each}
      </tbody>
    </table>

    <table class="phases">
      <thead><tr><th>Phase</th><th>From</th><th>To</th><th class="num">Duration</th></tr></thead>
      <tbody>
        {#each phases as phase}
          <tr>
            <td>{phase.label}</td>
            <td class="mono">{phase.from ? clock(new Date(phase.from).toISOString()) : '–'}</td>
            <td class="mono">{phase.to ? clock(new Date(phase.to).toISOString()) : '–'}</td>
            <td class="num mono">{duration(phase.seconds)}</td>
          </tr>
        {/each}
      </tbody>
    </table>
  </div>
</section>

<style>
  .timing { padding: 14px 28px 18px; background: var(--surface); border-bottom: 1px solid var(--line); }
  .gantt { display: flex; flex-direction: column; gap: 4px; }
  .axis { position: relative; height: 18px; margin-left: 132px; border-bottom: 1px solid var(--line); font-size: 11px; color: var(--muted); }
  .axis span { position: absolute; transform: translateX(-50%); }
  .row { display: grid; grid-template-columns: 132px 1fr; align-items: center; gap: 0; }
  .label { font-size: 12px; padding-right: 10px; white-space: nowrap; }
  .track { position: relative; height: 18px; background: repeating-linear-gradient(90deg, transparent 0 calc(10% - 1px), var(--line) calc(10% - 1px) 10%); border-radius: 3px; }
  .bar { position: absolute; top: 2px; bottom: 2px; display: flex; overflow: hidden; border-radius: 3px; background: var(--accent); min-width: 3px; }
  .bar span { display: block; height: 100%; }
  .bar.running { background: var(--running); }
  .bar.failed { background: var(--failed); }
  .bar.failed span { display: none; }
  .legend { display: flex; flex-wrap: wrap; gap: 14px; margin: 8px 0 0 132px; font-size: 11px; color: var(--muted); }
  .legend i { display: inline-block; width: 10px; height: 10px; border-radius: 2px; margin-right: 5px; vertical-align: -1px; }
  .legend i.failed { background: var(--failed); }
  .tables { display: grid; grid-template-columns: 2fr 1fr; gap: 20px; margin-top: 16px; }
  table { width: 100%; border-collapse: collapse; font-size: 12.5px; }
  th, td { padding: 5px 8px; border-bottom: 1px solid var(--line); text-align: left; vertical-align: top; }
  th { font-size: 11px; text-transform: uppercase; letter-spacing: 0.05em; color: var(--muted); font-weight: 500; }
  .num { text-align: right; }
  .error { font-size: 11px; }
  @media (max-width: 1000px) {
    .tables { grid-template-columns: 1fr; }
    .timing { padding: 14px 16px; overflow-x: auto; }
  }
</style>
