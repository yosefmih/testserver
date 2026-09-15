<script>
  import { onMount } from 'svelte';
  import { createJob, listJobs, deleteJob, formatDuration, formatTime } from '../lib/api.js';
  import { navigate } from '../lib/router.svelte.js';

  let { config } = $props();

  let file = $state(null);
  let chunkPages = $state(50);
  let concurrency = $state(2);
  let restructure = $state(true);
  let submitting = $state(false);
  let error = $state('');
  let jobs = $state([]);
  let defaultsApplied = false;

  $effect(() => {
    if (config && !defaultsApplied) {
      chunkPages = config.defaultChunkPages;
      concurrency = config.defaultConcurrency;
      restructure = config.defaultRestructure;
      defaultsApplied = true;
    }
  });

  async function refresh() {
    try {
      jobs = await listJobs();
    } catch (e) {
      error = e.message;
    }
  }

  onMount(() => {
    refresh();
    const timer = setInterval(refresh, 3000);
    return () => clearInterval(timer);
  });

  async function submit(event) {
    event.preventDefault();
    if (!file) return;
    submitting = true;
    error = '';
    try {
      const job = await createJob({ file, chunkPages, concurrency, restructure });
      navigate(`/jobs/${job.id}`);
    } catch (e) {
      error = e.message;
    } finally {
      submitting = false;
    }
  }

  async function remove(job) {
    if (!confirm(`Delete ${job.file_name} and its results?`)) return;
    try {
      await deleteJob(job.id);
      await refresh();
    } catch (e) {
      error = e.message;
    }
  }
</script>

<section class="panel">
  <h2>Upload a PDF</h2>
  <form class="upload" onsubmit={submit}>
    <label>
      PDF
      <input type="file" accept="application/pdf" required onchange={(e) => (file = e.target.files[0])} />
    </label>
    <label>
      Pages per request
      <input type="number" min="1" max="500" bind:value={chunkPages} />
    </label>
    <label>
      Requests in flight
      <input type="number" min="1" max="64" bind:value={concurrency} />
    </label>
    <label class="check">
      <input type="checkbox" bind:checked={restructure} />
      Merge tables across pages
    </label>
    <button class="primary" type="submit" disabled={submitting || !file}>
      {submitting ? 'Uploading…' : 'Run OCR'}
    </button>
  </form>
  {#if error}<p class="error">{error}</p>{/if}
</section>

<section class="panel">
  <h2>Documents</h2>
  {#if jobs.length === 0}
    <p style="color: var(--muted)">No documents yet.</p>
  {:else}
    <table>
      <thead>
        <tr>
          <th>Document</th>
          <th>Status</th>
          <th class="num">Pages</th>
          <th class="num">Done</th>
          <th class="num">Pages/s</th>
          <th class="num">Elapsed</th>
          <th>Submitted</th>
          <th></th>
        </tr>
      </thead>
      <tbody>
        {#each jobs as job (job.id)}
          <tr>
            <td><a href={`#/jobs/${job.id}`}>{job.file_name}</a></td>
            <td><span class={`pill ${job.status}`}>{job.status}</span></td>
            <td class="num">{job.pages}</td>
            <td class="num">{job.metrics.pages_done}</td>
            <td class="num">{job.metrics.pages_per_second.toFixed(2)}</td>
            <td class="num">{formatDuration(job.metrics.elapsed_seconds)}</td>
            <td>{formatTime(job.created_at)}</td>
            <td>
              {#if job.status === 'done'}
                <a class="button" href={`/api/jobs/${job.id}/result.zip`}>Download</a>
              {/if}
              {#if job.status === 'done' || job.status === 'failed'}
                <button class="secondary" onclick={() => remove(job)}>Delete</button>
              {/if}
            </td>
          </tr>
        {/each}
      </tbody>
    </table>
  {/if}
</section>
