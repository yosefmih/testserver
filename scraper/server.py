#!/usr/bin/env python3
"""
Amharic Web Scraper Server

A FastAPI-based HTTP server for managing web scraping jobs that extract Amharic text.
"""

import logging
from fastapi import FastAPI, HTTPException, status
from fastapi.responses import JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, validator
from typing import Dict, List, Optional
import os

from config import Config
from job_manager import JobManager
from worker import WorkerPool

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Initialize FastAPI app
app = FastAPI(
    title="Amharic Web Scraper API",
    description="Extract Amharic text from websites and store in S3",
    version="1.0.0"
)

# Initialize components
try:
    logger.info("=" * 60)
    logger.info("Initializing Amharic Web Scraper Server")
    logger.info("=" * 60)
    Config.validate()
    job_manager = JobManager()
    worker_pool = WorkerPool()
    logger.info("=" * 60)
    logger.info("Server initialized successfully")
    logger.info("=" * 60)
except Exception as e:
    logger.error("=" * 60)
    logger.error(f"Failed to initialize server: {e}")
    logger.error("=" * 60)
    raise


# Request/Response Models
class ScrapeConfig(BaseModel):
    max_depth: int = Field(default=3, ge=1, le=10, description="Maximum crawl depth")
    max_pages: int = Field(default=1000, ge=1, le=10000, description="Maximum pages to scrape")
    rate_limit: float = Field(default=2.0, ge=0.5, le=10.0, description="Seconds between requests per domain")
    timeout: int = Field(default=10, ge=5, le=60, description="Request timeout in seconds")
    same_domain_only: bool = Field(default=True, description="Only follow links on same domain")
    amharic_threshold: float = Field(default=0.3, ge=0.0, le=1.0, description="Minimum Amharic percentage")


class ScrapeRequest(BaseModel):
    seed_urls: List[str] = Field(..., min_items=1, max_items=100, description="Starting URLs to scrape")
    config: Optional[ScrapeConfig] = Field(default_factory=ScrapeConfig)
    
    @validator('seed_urls')
    def validate_urls(cls, v):
        if not all(url.startswith(('http://', 'https://')) for url in v):
            raise ValueError('All URLs must start with http:// or https://')
        return v


class JobResponse(BaseModel):
    job_id: str
    status: str
    created_at: str


class HealthResponse(BaseModel):
    status: str
    active_jobs: int


@app.get('/health', response_model=HealthResponse, tags=["Health"])
async def health():
    """Health check endpoint."""
    active_jobs = worker_pool.get_active_job_count()
    logger.debug(f"Health check: {active_jobs} active jobs")
    return {
        'status': 'healthy',
        'active_jobs': active_jobs
    }


@app.post('/api/scrape', response_model=JobResponse, status_code=status.HTTP_201_CREATED, tags=["Jobs"])
async def create_scrape_job(request: ScrapeRequest):
    """
    Create a new scraping job.
    
    - **seed_urls**: List of starting URLs to scrape
    - **config**: Optional configuration parameters
    """
    try:
        logger.info(f"Received scrape request with {len(request.seed_urls)} seed URL(s)")
        logger.debug(f"Seed URLs: {request.seed_urls}")
        
        # Convert Pydantic model to dict
        config = request.config.dict() if request.config else {}
        logger.debug(f"Job config: {config}")
        
        # Create job
        job_id = job_manager.create_job(request.seed_urls, config)
        logger.info(f"Created job {job_id}")
        
        # Submit to worker pool
        success = worker_pool.submit_job(job_id, request.seed_urls, config)
        
        if not success:
            logger.warning(f"Failed to submit job {job_id} to worker pool - pool is full")
            job_manager.update_job_status(job_id, 'failed', 'Failed to submit to worker pool')
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail='Worker pool is full'
            )
        
        logger.info(f"Job {job_id} submitted to worker pool successfully")
        
        # Get job info
        job = job_manager.get_job(job_id)
        
        return {
            'job_id': job_id,
            'status': job['status'],
            'created_at': job['created_at']
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error creating scrape job: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )


@app.get('/api/jobs/{job_id}', tags=["Jobs"])
async def get_job_status(job_id: str):
    """
    Get status of a scraping job.
    
    Returns job metadata including status, progress, and statistics.
    """
    try:
        logger.debug(f"Retrieving status for job {job_id}")
        job = job_manager.get_job(job_id)
        
        if not job:
            logger.warning(f"Job {job_id} not found")
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail='Job not found'
            )
        
        logger.debug(f"Job {job_id} status: {job.get('status', 'unknown')}")
        return job
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting job status: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )


@app.get('/api/jobs', tags=["Jobs"])
async def list_jobs(limit: int = 100):
    """
    List all scraping jobs.
    
    - **limit**: Maximum number of jobs to return (default: 100, max: 1000)
    """
    try:
        limit = min(limit, 1000)  # Cap at 1000
        
        jobs = job_manager.list_jobs(limit)
        
        return {
            'jobs': jobs,
            'count': len(jobs)
        }
        
    except Exception as e:
        logger.error(f"Error listing jobs: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )


@app.delete('/api/jobs/{job_id}', tags=["Jobs"])
async def cancel_job(job_id: str):
    """
    Cancel a scraping job.
    
    Note: Currently running jobs will complete their current page before stopping.
    """
    try:
        logger.info(f"Cancellation requested for job {job_id}")
        job = job_manager.get_job(job_id)
        
        if not job:
            logger.warning(f"Cannot cancel job {job_id} - not found")
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail='Job not found'
            )
        
        # Update status to cancelled
        success = job_manager.delete_job(job_id)
        
        if not success:
            logger.error(f"Failed to cancel job {job_id}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail='Failed to cancel job'
            )
        
        logger.info(f"Job {job_id} cancelled successfully")
        return {
            'job_id': job_id,
            'status': 'cancelled'
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error cancelling job: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )


@app.on_event("startup")
async def startup_event():
    """Log startup information and resume abandoned jobs."""
    logger.info("=" * 60)
    logger.info("Amharic Web Scraper API Started")
    logger.info(f"API Documentation: http://{Config.SERVER_HOST}:{Config.SERVER_PORT}/docs")
    logger.info(f"ReDoc: http://{Config.SERVER_HOST}:{Config.SERVER_PORT}/redoc")
    logger.info("=" * 60)
    
    # Resume any jobs that were running when pod was evicted
    logger.info("🔍 Checking for abandoned jobs to resume...")
    resume_abandoned_jobs()


def resume_abandoned_jobs():
    """Resume jobs that were running when pod was evicted."""
    try:
        # Get all jobs
        jobs = job_manager.list_jobs(limit=1000)
        
        # Find jobs that are stuck in "running" state
        running_jobs = [j for j in jobs if j.get('status') == 'running']
        
        if not running_jobs:
            logger.info("✅ No abandoned jobs found")
            return
        
        logger.info(f"🔄 Found {len(running_jobs)} jobs in 'running' state - attempting to resume")
        
        for job in running_jobs:
            job_id = job['id']
            
            # Check if job is already active in worker pool
            if worker_pool.is_job_active(job_id):
                logger.debug(f"Job {job_id} already active, skipping")
                continue
            
            # Check if checkpoint exists
            from config import Config
            checkpoint_key = f"{Config.S3_DATA_PREFIX}/{job_id}/checkpoint.json"
            
            try:
                # Quick check if checkpoint exists
                job_manager.metadata_store.s3_client.head_object(
                    Bucket=Config.S3_BUCKET,
                    Key=checkpoint_key
                )
                
                logger.info(f"🔄 Resuming job {job_id[:8]}... from checkpoint")
                
                # Re-submit to worker pool
                success = worker_pool.submit_job(
                    job_id,
                    job.get('seed_urls', []),
                    job.get('config', {})
                )
                
                if success:
                    logger.info(f"✅ Job {job_id[:8]}... resumed successfully")
                else:
                    logger.warning(f"⚠️  Could not resume job {job_id[:8]}... - worker pool full")
                    
            except job_manager.metadata_store.s3_client.exceptions.NoSuchKey:
                # No checkpoint - job might be complete, mark as failed
                logger.warning(f"⚠️  Job {job_id[:8]}... has no checkpoint, marking as failed")
                job_manager.update_job_status(job_id, 'failed', 'No checkpoint found after restart')
            except Exception as e:
                logger.error(f"❌ Error resuming job {job_id[:8]}...: {e}")
        
        logger.info(f"✅ Job resume process complete")
        
    except Exception as e:
        logger.error(f"❌ Error in resume_abandoned_jobs: {e}", exc_info=True)


@app.on_event("shutdown")
async def shutdown_event():
    """Cleanup on shutdown."""
    logger.info("=" * 60)
    logger.info("Shutting down server")
    logger.info("=" * 60)
    worker_pool.shutdown(wait=False)


# Mount static files LAST so API routes take precedence
static_dir = os.path.join(os.path.dirname(__file__), "static")
if os.path.exists(static_dir):
    app.mount("/", StaticFiles(directory=static_dir, html=True), name="static")
    logger.info(f"Mounted static files from {static_dir}")


if __name__ == '__main__':
    import uvicorn
    
    logger.info(f"Starting server on {Config.SERVER_HOST}:{Config.SERVER_PORT}")
    logger.info(f"S3 Bucket: {Config.S3_BUCKET}")
    logger.info(f"Max concurrent jobs: {Config.MAX_CONCURRENT_JOBS}")
    
    uvicorn.run(
        app,
        host=Config.SERVER_HOST,
        port=Config.SERVER_PORT,
        log_level="info"
    )

