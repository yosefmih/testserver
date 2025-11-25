import type { Job } from '../types';

interface JobCardProps {
  job: Job;
  onClick: () => void;
}

export const JobCard = ({ job, onClick }: JobCardProps) => {
  const getStatusClass = (status: string) => {
    switch (status) {
      case 'running': return 'status-running';
      case 'completed': return 'status-completed';
      case 'failed': return 'status-failed';
      case 'queued': return 'status-queued';
      default: return '';
    }
  };

  const progress = job.progress || {};
  const stats = job.stats || {};
  const percentage = job.config?.max_pages
    ? Math.round((progress.pages_scraped || 0) / job.config.max_pages * 100)
    : 0;

  return (
    <div className={`job-card ${getStatusClass(job.status)}`} onClick={onClick}>
      <div className="job-header">
        <span className="job-id">Job: {job.id.substring(0, 8)}...</span>
        <span className={`job-status ${getStatusClass(job.status)}`}>
          {job.status.toUpperCase()}
        </span>
      </div>

      <div className="job-stats">
        <div className="stat">
          <span>📄 Pages:</span>
          <span className="stat-value">{progress.pages_scraped || 0}</span>
        </div>
        <div className="stat">
          <span>📝 Amharic:</span>
          <span className="stat-value">{progress.pages_amharic || 0}</span>
        </div>
        <div className="stat">
          <span>⏱️ Queue:</span>
          <span className="stat-value">{progress.queue_size || 0}</span>
        </div>
        <div className="stat">
          <span>⏰ Time:</span>
          <span className="stat-value">{Math.round(stats.elapsed_seconds || 0)}s</span>
        </div>
      </div>

      {job.status === 'running' && (
        <div className="progress-bar">
          <div className="progress-fill" style={{ width: `${percentage}%` }} />
        </div>
      )}
    </div>
  );
};

