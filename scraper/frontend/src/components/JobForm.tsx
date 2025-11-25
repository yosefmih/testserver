import { useState } from 'react';
import { scraperApi } from '../services/api';
import type { ScrapeConfig } from '../types';

interface JobFormProps {
  onJobCreated: () => void;
}

export const JobForm = ({ onJobCreated }: JobFormProps) => {
  const [seedUrls, setSeedUrls] = useState('');
  const [config, setConfig] = useState<ScrapeConfig>({
    max_depth: 3,
    max_pages: 100,
    rate_limit: 2.0,
    timeout: 10,
    same_domain_only: true,
    amharic_threshold: 0.3,
  });
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setSuccess(null);
    setLoading(true);

    const urls = seedUrls.split('\n').map(url => url.trim()).filter(url => url);

    if (urls.length === 0) {
      setError('Please enter at least one URL');
      setLoading(false);
      return;
    }

    try {
      const result = await scraperApi.createJob({
        seed_urls: urls,
        config,
      });
      setSuccess(`Job created successfully! ID: ${result.job_id.substring(0, 8)}...`);
      setSeedUrls('');
      setTimeout(() => {
        setSuccess(null);
        onJobCreated();
      }, 2000);
    } catch (err: any) {
      setError(err.response?.data?.detail || err.message || 'Failed to create job');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="card">
      <h2 className="card-title">📝 Create New Scraping Job</h2>
      
      {error && (
        <div className="alert alert-error">{error}</div>
      )}
      
      {success && (
        <div className="alert alert-success">{success}</div>
      )}

      <form onSubmit={handleSubmit}>
        <div className="form-group">
          <label>Seed URLs (one per line)</label>
          <textarea
            value={seedUrls}
            onChange={(e) => setSeedUrls(e.target.value)}
            placeholder="https://example.com&#10;https://another-site.com"
            rows={4}
            required
          />
        </div>

        <div className="form-row">
          <div className="form-group">
            <label>Max Depth</label>
            <input
              type="number"
              value={config.max_depth}
              onChange={(e) => setConfig({ ...config, max_depth: parseInt(e.target.value) })}
              min="1"
              max="10"
            />
          </div>
          <div className="form-group">
            <label>Max Pages</label>
            <input
              type="number"
              value={config.max_pages}
              onChange={(e) => setConfig({ ...config, max_pages: parseInt(e.target.value) })}
              min="1"
              max="10000"
            />
          </div>
          <div className="form-group">
            <label>Rate Limit (seconds)</label>
            <input
              type="number"
              value={config.rate_limit}
              onChange={(e) => setConfig({ ...config, rate_limit: parseFloat(e.target.value) })}
              min="0.5"
              max="10"
              step="0.5"
            />
          </div>
        </div>

        <div className="form-row">
          <div className="form-group">
            <label>Timeout (seconds)</label>
            <input
              type="number"
              value={config.timeout}
              onChange={(e) => setConfig({ ...config, timeout: parseInt(e.target.value) })}
              min="5"
              max="60"
            />
          </div>
          <div className="form-group">
            <label>Same Domain Only</label>
            <select
              value={config.same_domain_only ? 'true' : 'false'}
              onChange={(e) => setConfig({ ...config, same_domain_only: e.target.value === 'true' })}
            >
              <option value="true">Yes</option>
              <option value="false">No</option>
            </select>
          </div>
          <div className="form-group">
            <label>Amharic Threshold</label>
            <input
              type="number"
              value={config.amharic_threshold}
              onChange={(e) => setConfig({ ...config, amharic_threshold: parseFloat(e.target.value) })}
              min="0"
              max="1"
              step="0.1"
            />
          </div>
        </div>

        <button type="submit" className="btn btn-primary" disabled={loading}>
          {loading ? 'Creating...' : 'Start Scraping'}
        </button>
      </form>
    </div>
  );
};

