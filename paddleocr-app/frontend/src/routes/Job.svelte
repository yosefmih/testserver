<script>
  import { onMount } from 'svelte';
  import { Marked } from 'marked';
  import DOMPurify from 'dompurify';
  import { getJob, getResultMarkdown, formatDuration, formatTime } from '../lib/api.js';

  let { id } = $props();

  let job = $state(null);
  let error = $state('');
  let preview = $state('');
  let previewLoading = $state(false);

  const marked = new Marked({
    renderer: {
      image({ href, title, text }) {
        const src = /^(https?:)?\/\//.test(href) ? href : `/api/jobs/${id}/files/${href}`;
        return `<img src="${src}" alt="${text ?? ''}" title="${title ?? ''}">`;
      },
    },
  });

  const progress = $derived(job ? (job.metrics.pages_done / job.pages) * 100 : 0);

  async function refresh() {
    try {
      job = await getJob(id);
      error = '';
    } catch (e) {
      error = e.message;
    }
  }

  onMount(() => {
    refresh();
    const timer = setInterval(() => {
      if (job && (job.status === 'done' || job.status === 'failed')) return;
      refresh();
    }, 2000);
    return () => clearInterval(timer);
  });

  $effect(() => {
    if (job?.status === 'done' && !preview && !previewLoading) loadPreview();
  });

  async function loadPreview() {
    previewLoading = true;
    try {
      const markdown = await getResultMarkdown(id);
      preview = DOMPurify.sanitize(await marked.parse(markdown));
    } catch (e) {
      error = e.message;
    } finally {
      previewLoading = false;
    }
  }
</script>

{#if error}
  <p class="error">{error}</p>
{/if}

{#if job}
  <section class="panel">
    <h2>{job.file_name} <span class={`pill ${job.status}`}>{job.status}</span></h2>
    <div class="progress"><div style={`width: ${progress}%`}></div></div>
    <div class="stats">
      <div><b>{job.metrics.pages_done} / {job.pages}</b><span>pages</span></div>
      <div><b>{job.metrics.chunks_done} / {job.chunks.length}</b><span>requests of {job.chunk_pages} pages</span></div>
      <div><b>{job.metrics.pages_per_second.toFixed(2)}</b><span>pages / second</span></div>
      <div><b>{formatDuration(job.metrics.elapsed_seconds)}</b><span>elapsed</span></div>
      <div><b>{job.concurrency}</b><span>in flight</span></div>
      <div><b>{formatTime(job.created_at)}</b><span>submitted</span></div>
    </div>
    <div class="chunks" title="one square per request">
      {#each job.chunks as chunk (chunk.index)}
        <div class={`chunk ${chunk.status}`} title={`pages ${chunk.first_page}-${chunk.last_page}: ${chunk.status}${chunk.error ? ' - ' + chunk.error : ''}`}></div>
      {/each}
    </div>
    {#if job.error}<p class="error">{job.error}</p>{/if}
    {#if job.status === 'done'}
      <div class="actions">
        <a class="button" href={`/api/jobs/${job.id}/result.zip`}>Download markdown + images (zip)</a>
        <a class="button" href={`/api/jobs/${job.id}/result.md`} target="_blank">Open markdown</a>
        <span style="color: var(--muted); align-self: center">assembled with {job.assembled_with}</span>
      </div>
    {/if}
  </section>

  {#if job.status === 'done'}
    <section class="panel">
      <h2>Preview</h2>
      {#if previewLoading}
        <p style="color: var(--muted)">Rendering…</p>
      {:else}
        <div class="preview">{@html preview}</div>
      {/if}
    </section>
  {/if}
{/if}
