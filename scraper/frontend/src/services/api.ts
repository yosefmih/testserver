import axios from 'axios';
import type { Job, JobsResponse, ScrapeRequest, CreateJobResponse } from '../types';

const api = axios.create({
  baseURL: '/api',
  headers: {
    'Content-Type': 'application/json',
  },
});

export const scraperApi = {
  createJob: async (request: ScrapeRequest): Promise<CreateJobResponse> => {
    const { data } = await api.post<CreateJobResponse>('/scrape', request);
    return data;
  },

  getJob: async (jobId: string): Promise<Job> => {
    const { data } = await api.get<Job>(`/jobs/${jobId}`);
    return data;
  },

  listJobs: async (limit: number = 50): Promise<JobsResponse> => {
    const { data } = await api.get<JobsResponse>(`/jobs?limit=${limit}`);
    return data;
  },

  cancelJob: async (jobId: string): Promise<void> => {
    await api.delete(`/jobs/${jobId}`);
  },

  checkHealth: async (): Promise<{ status: string; active_jobs: number }> => {
    const { data } = await api.get('/health');
    return data;
  },
};

