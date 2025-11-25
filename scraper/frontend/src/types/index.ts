export interface ScrapeConfig {
  max_depth?: number;
  max_pages?: number;
  rate_limit?: number;
  timeout?: number;
  same_domain_only?: boolean;
  amharic_threshold?: number;
}

export interface ScrapeRequest {
  seed_urls: string[];
  config?: ScrapeConfig;
}

export interface JobProgress {
  pages_scraped: number;
  pages_amharic: number;
  queue_size: number;
  current_url?: string;
}

export interface JobStats {
  total_bytes: number;
  elapsed_seconds: number;
  urls_visited?: number;
}

export type JobStatus = 'queued' | 'running' | 'completed' | 'failed' | 'cancelled';

export interface Job {
  id: string;
  status: JobStatus;
  seed_urls: string[];
  config?: ScrapeConfig;
  created_at: string;
  started_at?: string;
  completed_at?: string;
  progress: JobProgress;
  stats: JobStats;
  error?: string;
}

export interface JobsResponse {
  jobs: Job[];
  count: number;
}

export interface CreateJobResponse {
  job_id: string;
  status: string;
  created_at: string;
}

