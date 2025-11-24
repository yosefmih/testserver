import logging
import threading
from concurrent.futures import ThreadPoolExecutor, Future
from typing import Dict, Optional
from queue import Queue

from scraper_engine import ScraperEngine
from job_manager import JobManager
from config import Config

logger = logging.getLogger(__name__)

class WorkerPool:
    """
    Manages a pool of worker threads for processing scraping jobs.
    """
    
    def __init__(self, num_workers: int = None):
        """
        Initialize worker pool.
        
        Args:
            num_workers: Number of concurrent workers (defaults to Config.MAX_CONCURRENT_JOBS)
        """
        self.num_workers = num_workers or Config.MAX_CONCURRENT_JOBS
        self.executor = ThreadPoolExecutor(max_workers=self.num_workers)
        self.active_jobs: Dict[str, Future] = {}
        self.job_manager = JobManager()
        self.lock = threading.Lock()
        
        logger.info(f"Initialized worker pool with {self.num_workers} workers")
    
    def submit_job(self, job_id: str, seed_urls: list, config: Dict) -> bool:
        """
        Submit a scraping job to the worker pool.
        
        Args:
            job_id: Job identifier
            seed_urls: List of starting URLs
            config: Job configuration
            
        Returns:
            True if job was submitted, False if pool is full
        """
        with self.lock:
            # Check if job already exists
            if job_id in self.active_jobs:
                logger.warning(f"Job {job_id} already active")
                return False
            
            # Submit job to executor
            future = self.executor.submit(
                self._process_job,
                job_id,
                seed_urls,
                config
            )
            
            self.active_jobs[job_id] = future
            
            # Add callback to clean up when done
            future.add_done_callback(lambda f: self._cleanup_job(job_id))
            
            logger.info(f"Submitted job {job_id} to worker pool")
            return True
    
    def _process_job(self, job_id: str, seed_urls: list, config: Dict):
        """
        Process a scraping job.
        
        Args:
            job_id: Job identifier
            seed_urls: List of starting URLs
            config: Job configuration
        """
        logger.info(f"Starting processing of job {job_id}")
        
        try:
            # Update status to running
            self.job_manager.update_job_status(job_id, 'running')
            
            # Create progress callback
            def progress_callback(progress: Dict):
                self.job_manager.update_job_progress(job_id, progress)
            
            # Initialize scraper engine
            scraper = ScraperEngine(
                job_id=job_id,
                seed_urls=seed_urls,
                max_depth=config.get('max_depth', Config.DEFAULT_MAX_DEPTH),
                max_pages=config.get('max_pages', Config.DEFAULT_MAX_PAGES),
                rate_limit=config.get('rate_limit', Config.DEFAULT_RATE_LIMIT),
                timeout=config.get('timeout', Config.DEFAULT_TIMEOUT),
                same_domain_only=config.get('same_domain_only', True),
                amharic_threshold=config.get('amharic_threshold', Config.DEFAULT_AMHARIC_THRESHOLD),
                progress_callback=progress_callback
            )
            
            # Run scraper
            final_stats = scraper.run()
            
            # Update job as completed
            self.job_manager.update_job_progress(job_id, scraper._get_progress(), final_stats)
            self.job_manager.update_job_status(job_id, 'completed')
            
            logger.info(f"Completed job {job_id}: {final_stats}")
            
        except Exception as e:
            logger.error(f"Error processing job {job_id}: {e}")
            self.job_manager.update_job_status(job_id, 'failed', error=str(e))
    
    def _cleanup_job(self, job_id: str):
        """Remove job from active jobs."""
        with self.lock:
            if job_id in self.active_jobs:
                del self.active_jobs[job_id]
                logger.info(f"Cleaned up job {job_id}")
    
    def get_active_job_count(self) -> int:
        """Get number of currently active jobs."""
        with self.lock:
            return len(self.active_jobs)
    
    def is_job_active(self, job_id: str) -> bool:
        """Check if a job is currently active."""
        with self.lock:
            return job_id in self.active_jobs
    
    def shutdown(self, wait: bool = True):
        """
        Shutdown the worker pool.
        
        Args:
            wait: Whether to wait for active jobs to complete
        """
        logger.info("Shutting down worker pool")
        self.executor.shutdown(wait=wait)

