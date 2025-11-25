import React, { useEffect, useState } from 'react';
import { scraperApi } from '../services/api';
import type { Job } from '../types';

interface JobModalProps {
  jobId: string;
  onClose: () => void;
}

export const JobModal: React.FC<JobModalProps> = ({ jobId, onClose }) => {
  const [job, setJob] = useState<Job | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    loadJob();
  }, [jobId]);

  const loadJob = async () => {
    try {
      const data = await scraperApi.getJob(jobId);
      setJob(data);
      setError(null);
    } catch (err: any) {
      setError(err.response?.data?.detail || err.message || 'Failed to load job');
    } finally {
      setLoading(false);
    }
  };

  if (loading) {
    return (
      <div className="modal active" onClick={(e) => e.target === e.currentTarget && onClose()}>
        <div className="modal-content">
          <div className="modal-header">
            <h2>Job Details</h2>
            <button className="modal-close" onClick={onClose}>&times;</button>
          </div>
          <p>Loading...</p>
        </div>
      </div>
    );
  }

  if (error || !job) {
    return (
      <div className="modal active" onClick={(e) => e.target === e.currentTarget && onClose()}>
        <div className="modal-content">
          <div className="modal-header">
            <h2>Job Details</h2>
            <button className="modal-close" onClick={onClose}>&times;</button>
          </div>
          <div className="alert alert-error">{error || 'Job not found'}</div>
        </div>
      </div>
    );
  }

  return (
    <div className="modal active" onClick={(e) => e.target === e.currentTarget && onClose()}>
      <div className="modal-content">
        <div className="modal-header">
          <h2>Job Details</h2>
          <button className="modal-close" onClick={onClose}>&times;</button>
        </div>

        <div className="job-header" style={{ marginBottom: '20px' }}>
          <span className="job-id">{job.id}</span>
          <span className={`job-status status-${job.status}`}>
            {job.status.toUpperCase()}
          </span>
        </div>

        <h3>Seed URLs</h3>
        <div className="url-list">
          {job.seed_urls.map((url, i) => (
            <div key={i} className="url-item">🔗 {url}</div>
          ))}
        </div>

        <h3 style={{ marginTop: '20px' }}>Configuration</h3>
        <div className="config-grid">
          <div className="config-item">
            <div className="config-label">Max Depth</div>
            <div className="config-value">{job.config?.max_depth || 3}</div>
          </div>
          <div className="config-item">
            <div className="config-label">Max Pages</div>
            <div className="config-value">{job.config?.max_pages || 1000}</div>
          </div>
          <div className="config-item">
            <div className="config-label">Rate Limit</div>
            <div className="config-value">{job.config?.rate_limit || 2.0}s</div>
          </div>
          <div className="config-item">
            <div className="config-label">Amharic Threshold</div>
            <div className="config-value">{((job.config?.amharic_threshold || 0.3) * 100).toFixed(0)}%</div>
          </div>
        </div>

        <h3 style={{ marginTop: '20px' }}>Progress</h3>
        <div className="config-grid">
          <div className="config-item">
            <div className="config-label">Pages Scraped</div>
            <div className="config-value">{job.progress?.pages_scraped || 0}</div>
          </div>
          <div className="config-item">
            <div className="config-label">Amharic Pages</div>
            <div className="config-value">{job.progress?.pages_amharic || 0}</div>
          </div>
          <div className="config-item">
            <div className="config-label">Queue Size</div>
            <div className="config-value">{job.progress?.queue_size || 0}</div>
          </div>
          <div className="config-item">
            <div className="config-label">Elapsed Time</div>
            <div className="config-value">{Math.round(job.stats?.elapsed_seconds || 0)}s</div>
          </div>
        </div>

        {job.progress?.current_url && (
          <>
            <h3 style={{ marginTop: '20px' }}>Current URL</h3>
            <div className="url-list">
              <div className="url-item">{job.progress.current_url}</div>
            </div>
          </>
        )}

        {job.error && (
          <div className="alert alert-error" style={{ marginTop: '20px' }}>
            <strong>Error:</strong> {job.error}
          </div>
        )}

        <div style={{ marginTop: '20px', fontSize: '0.9em', color: '#999' }}>
          <div>Created: {new Date(job.created_at).toLocaleString()}</div>
          {job.completed_at && <div>Completed: {new Date(job.completed_at).toLocaleString()}</div>}
        </div>
      </div>
    </div>
  );
};

