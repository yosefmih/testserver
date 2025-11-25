import { useState, useEffect } from 'react';
import { scraperApi } from '../services/api';
import { JobCard } from './JobCard';
import { JobModal } from './JobModal';
import type { Job } from '../types';

export const JobList = () => {
  const [jobs, setJobs] = useState<Job[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [selectedJobId, setSelectedJobId] = useState<string | null>(null);
  const [refreshing, setRefreshing] = useState(false);

  useEffect(() => {
    loadJobs();
    
    // Auto-refresh every 5 seconds if there are running jobs
    const interval = setInterval(() => {
      const hasRunningJobs = jobs.some(job => job.status === 'running');
      if (hasRunningJobs) {
        loadJobs(true);
      }
    }, 5000);

    return () => clearInterval(interval);
  }, [jobs.length > 0 && jobs.some(job => job.status === 'running')]);

  const loadJobs = async (silent = false) => {
    if (!silent) {
      setLoading(true);
    } else {
      setRefreshing(true);
    }
    
    try {
      const data = await scraperApi.listJobs(50);
      setJobs(data.jobs);
      setError(null);
    } catch (err: any) {
      setError(err.response?.data?.detail || err.message || 'Failed to load jobs');
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  };

  if (loading) {
    return (
      <div className="card">
        <h2 className="card-title">📊 Scraping Jobs</h2>
        <p>Loading jobs...</p>
      </div>
    );
  }

  if (error) {
    return (
      <div className="card">
        <h2 className="card-title">📊 Scraping Jobs</h2>
        <div className="alert alert-error">{error}</div>
        <button className="btn btn-secondary" onClick={() => loadJobs()}>
          Retry
        </button>
      </div>
    );
  }

  return (
    <>
      <div className="card">
        <div className="card-header">
          <h2 className="card-title">📊 Scraping Jobs</h2>
          <button 
            className={`btn btn-secondary ${refreshing ? 'spinning' : ''}`}
            onClick={() => loadJobs()}
            disabled={refreshing}
          >
            🔄 Refresh
          </button>
        </div>

        {jobs.length === 0 ? (
          <div className="empty-state">
            <div className="empty-state-icon">📭</div>
            <p>No jobs yet. Create one to get started!</p>
          </div>
        ) : (
          <div className="jobs-grid">
            {jobs.map(job => (
              <JobCard
                key={job.id}
                job={job}
                onClick={() => setSelectedJobId(job.id)}
              />
            ))}
          </div>
        )}
      </div>

      {selectedJobId && (
        <JobModal
          jobId={selectedJobId}
          onClose={() => setSelectedJobId(null)}
        />
      )}
    </>
  );
};

