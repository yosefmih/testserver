#!/usr/bin/env python3
"""
Amharic Web Scraper Server

A FastAPI-based HTTP server for managing web scraping jobs that extract Amharic text.
"""

import logging
from fastapi import FastAPI, HTTPException, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, validator
from typing import Dict, List, Optional

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
    Config.validate()
    job_manager = JobManager()
    worker_pool = WorkerPool()
    logger.info("Server initialized successfully")
except Exception as e:
    logger.error(f"Failed to initialize server: {e}")
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
    return {
        'status': 'healthy',
        'active_jobs': worker_pool.get_active_job_count()
    }


@app.post('/api/scrape', response_model=JobResponse, status_code=status.HTTP_201_CREATED, tags=["Jobs"])
async def create_scrape_job(request: ScrapeRequest):
    """
    Create a new scraping job.
    
    - **seed_urls**: List of starting URLs to scrape
    - **config**: Optional configuration parameters
    """
    try:
        # Convert Pydantic model to dict
        config = request.config.dict() if request.config else {}
        
        # Create job
        job_id = job_manager.create_job(request.seed_urls, config)
        
        # Submit to worker pool
        success = worker_pool.submit_job(job_id, request.seed_urls, config)
        
        if not success:
            job_manager.update_job_status(job_id, 'failed', 'Failed to submit to worker pool')
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail='Worker pool is full'
            )
        
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
        job = job_manager.get_job(job_id)
        
        if not job:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail='Job not found'
            )
        
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
        job = job_manager.get_job(job_id)
        
        if not job:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail='Job not found'
            )
        
        # Update status to cancelled
        success = job_manager.delete_job(job_id)
        
        if not success:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail='Failed to cancel job'
            )
        
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


@app.on_event("shutdown")
async def shutdown_event():
    """Cleanup on shutdown."""
    logger.info("Shutting down server")
    worker_pool.shutdown(wait=False)


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

