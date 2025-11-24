import uuid
import logging
from datetime import datetime
from typing import Dict, Optional
from s3_metadata import S3MetadataStore

logger = logging.getLogger(__name__)

class JobManager:
    """
    Manages scraping job lifecycle and metadata.
    """
    
    def __init__(self):
        """Initialize job manager."""
        self.metadata_store = S3MetadataStore()
    
    def create_job(self, seed_urls: list, config: Dict) -> str:
        """
        Create a new scraping job.
        
        Args:
            seed_urls: List of starting URLs
            config: Job configuration
            
        Returns:
            Job ID
        """
        job_id = str(uuid.uuid4())
        
        job_data = {
            'id': job_id,
            'status': 'queued',
            'seed_urls': seed_urls,
            'config': config,
            'created_at': datetime.utcnow().isoformat(),
            'started_at': None,
            'completed_at': None,
            'progress': {
                'pages_scraped': 0,
                'pages_amharic': 0,
                'queue_size': 0,
                'current_url': None
            },
            'stats': {
                'total_bytes': 0,
                'elapsed_seconds': 0
            },
            'error': None
        }
        
        # Save to S3
        self.metadata_store.update_job(job_id, job_data)
        
        logger.info(f"Created job {job_id}")
        return job_id
    
    def get_job(self, job_id: str) -> Optional[Dict]:
        """
        Get job metadata.
        
        Args:
            job_id: Job identifier
            
        Returns:
            Job metadata or None
        """
        return self.metadata_store.get_job(job_id)
    
    def update_job_status(self, job_id: str, status: str, error: str = None) -> bool:
        """
        Update job status.
        
        Args:
            job_id: Job identifier
            status: New status (queued, running, completed, failed, cancelled)
            error: Error message if failed
            
        Returns:
            True if successful
        """
        updates = {'status': status}
        
        if status == 'running':
            updates['started_at'] = datetime.utcnow().isoformat()
        elif status in ('completed', 'failed', 'cancelled'):
            updates['completed_at'] = datetime.utcnow().isoformat()
        
        if error:
            updates['error'] = error
        
        success = self.metadata_store.update_job(job_id, updates)
        logger.info(f"Updated job {job_id} status to {status}")
        return success
    
    def update_job_progress(self, job_id: str, progress: Dict, stats: Dict = None) -> bool:
        """
        Update job progress.
        
        Args:
            job_id: Job identifier
            progress: Progress dictionary
            stats: Optional statistics dictionary
            
        Returns:
            True if successful
        """
        updates = {'progress': progress}
        
        if stats:
            updates['stats'] = stats
        
        return self.metadata_store.update_job(job_id, updates)
    
    def list_jobs(self, limit: int = 100) -> list:
        """
        List all jobs.
        
        Args:
            limit: Maximum number of jobs to return
            
        Returns:
            List of job metadata
        """
        return self.metadata_store.list_jobs(limit)
    
    def delete_job(self, job_id: str) -> bool:
        """
        Delete a job (mark as cancelled).
        
        Args:
            job_id: Job identifier
            
        Returns:
            True if successful
        """
        return self.update_job_status(job_id, 'cancelled')

