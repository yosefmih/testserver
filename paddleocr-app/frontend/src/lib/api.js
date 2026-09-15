async function request(url, options) {
  const response = await fetch(url, options);
  if (!response.ok) {
    let detail = response.statusText;
    try {
      detail = (await response.json()).detail ?? detail;
    } catch {}
    throw new Error(`${response.status}: ${detail}`);
  }
  return response.status === 204 ? null : response.json();
}

export const getConfig = () => request('/api/config');
export const listJobs = () => request('/api/jobs');
export const getJob = (id) => request(`/api/jobs/${id}`);
export const deleteJob = (id) => request(`/api/jobs/${id}`, { method: 'DELETE' });

export function createJob({ file, chunkPages, concurrency, restructure }) {
  const body = new FormData();
  body.append('pdf', file);
  body.append('chunkPages', String(chunkPages));
  body.append('concurrency', String(concurrency));
  body.append('restructure', String(restructure));
  return request('/api/jobs', { method: 'POST', body });
}

export async function getResultMarkdown(id) {
  const response = await fetch(`/api/jobs/${id}/result.md`);
  if (!response.ok) throw new Error(`${response.status}: could not load result`);
  return response.text();
}

export function formatDuration(seconds) {
  if (!seconds) return '0s';
  const m = Math.floor(seconds / 60);
  const s = Math.round(seconds % 60);
  return m ? `${m}m ${s}s` : `${s}s`;
}

export function formatTime(iso) {
  return iso ? new Date(iso).toLocaleString() : '';
}
