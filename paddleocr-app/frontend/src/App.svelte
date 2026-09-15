<script>
  import Home from './routes/Home.svelte';
  import Job from './routes/Job.svelte';
  import { route } from './lib/router.svelte.js';
  import { getConfig } from './lib/api.js';

  const jobMatch = $derived(route.path.match(/^\/jobs\/([a-z0-9]+)$/));
  let config = $state(null);
  getConfig().then((c) => (config = c)).catch(() => {});
</script>

<header class="top">
  <h1><a href="#/" style="color: inherit; text-decoration: none">PaddleOCR documents</a></h1>
  {#if config}
    <span class="env">{config.paddleocrUrl} · {config.storage}</span>
  {/if}
</header>

<main>
  {#if jobMatch}
    <Job id={jobMatch[1]} />
  {:else}
    <Home {config} />
  {/if}
</main>
