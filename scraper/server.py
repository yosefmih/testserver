#!/usr/bin/env python3
"""
Amharic Web Scraper Server

A Flask-based HTTP server for managing web scraping jobs that extract Amharic text.
"""

import logging
from flask import Flask, request, jsonify
from typing import Dict

from config import Config
from job_manager import JobManager
from worker import WorkerPool

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Initialize Flask app
app = Flask(__name__)

# Initialize components
try:
    Config.validate()
    job_manager = JobManager()
    worker_pool = WorkerPool()
    logger.info("Server initialized successfully")
except Exception as e:
    logger.error(f"Failed to initialize server: {e}")
    raise

@app.route('/health', methods=['GET'])
def health():
    """Health check endpoint."""
    return jsonify({
        'status': 'healthy',
        'active_jobs': worker_pool.get_active_job_count()
    })

@app.route('/api/scrape', methods=['POST'])
def create_scrape_job():
    """
    Create a new scraping job.
    
    Request body:
    {
        "seed_urls": ["https://example.com"],
        "config": {
            "max_depth": 3,
            "max_pages": 500,
            "rate_limit": 2.0,
            "timeout": 10,
            "same_domain_only": true,
            "amharic_threshold": 0.3
        }
    }
    """
    try:
        data = request.get_json()
        
        # Validate request
        if not data:
            return jsonify({'error': 'Request body is required'}), 400
        
        seed_urls = data.get('seed_urls', [])
        if not seed_urls or not isinstance(seed_urls, list):
            return jsonify({'error': 'seed_urls must be a non-empty list'}), 400
        
        if not all(isinstance(url, str) for url in seed_urls):
            return jsonify({'error': 'All seed_urls must be strings'}), 400
        
        config = data.get('config', {})
        if not isinstance(config, dict):
            return jsonify({'error': 'config must be a dictionary'}), 400
        
        # Create job
        job_id = job_manager.create_job(seed_urls, config)
        
        # Submit to worker pool
        success = worker_pool.submit_job(job_id, seed_urls, config)
        
        if not success:
            job_manager.update_job_status(job_id, 'failed', 'Failed to submit to worker pool')
            return jsonify({'error': 'Worker pool is full'}), 503
        
        # Get job info
        job = job_manager.get_job(job_id)
        
        return jsonify({
            'job_id': job_id,
            'status': job['status'],
            'created_at': job['created_at']
        }), 201
        
    except Exception as e:
        logger.error(f"Error creating scrape job: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/jobs/<job_id>', methods=['GET'])
def get_job_status(job_id: str):
    """
    Get status of a scraping job.
    
    Returns job metadata including status, progress, and statistics.
    """
    try:
        job = job_manager.get_job(job_id)
        
        if not job:
            return jsonify({'error': 'Job not found'}), 404
        
        return jsonify(job), 200
        
    except Exception as e:
        logger.error(f"Error getting job status: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/jobs', methods=['GET'])
def list_jobs():
    """
    List all scraping jobs.
    
    Query parameters:
    - limit: Maximum number of jobs to return (default: 100)
    """
    try:
        limit = request.args.get('limit', 100, type=int)
        limit = min(limit, 1000)  # Cap at 1000
        
        jobs = job_manager.list_jobs(limit)
        
        return jsonify({
            'jobs': jobs,
            'count': len(jobs)
        }), 200
        
    except Exception as e:
        logger.error(f"Error listing jobs: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/jobs/<job_id>', methods=['DELETE'])
def cancel_job(job_id: str):
    """
    Cancel a scraping job.
    
    Note: Currently running jobs will complete their current page before stopping.
    """
    try:
        job = job_manager.get_job(job_id)
        
        if not job:
            return jsonify({'error': 'Job not found'}), 404
        
        # Update status to cancelled
        success = job_manager.delete_job(job_id)
        
        if not success:
            return jsonify({'error': 'Failed to cancel job'}), 500
        
        return jsonify({
            'job_id': job_id,
            'status': 'cancelled'
        }), 200
        
    except Exception as e:
        logger.error(f"Error cancelling job: {e}")
        return jsonify({'error': str(e)}), 500

@app.errorhandler(404)
def not_found(e):
    """Handle 404 errors."""
    return jsonify({'error': 'Endpoint not found'}), 404

@app.errorhandler(500)
def internal_error(e):
    """Handle 500 errors."""
    logger.error(f"Internal server error: {e}")
    return jsonify({'error': 'Internal server error'}), 500

def main():
    """Main entry point."""
    logger.info(f"Starting server on {Config.SERVER_HOST}:{Config.SERVER_PORT}")
    logger.info(f"S3 Bucket: {Config.S3_BUCKET}")
    logger.info(f"Max concurrent jobs: {Config.MAX_CONCURRENT_JOBS}")
    
    try:
        app.run(
            host=Config.SERVER_HOST,
            port=Config.SERVER_PORT,
            debug=False,
            threaded=True
        )
    except KeyboardInterrupt:
        logger.info("Shutting down server")
        worker_pool.shutdown(wait=False)
    except Exception as e:
        logger.error(f"Server error: {e}")
        worker_pool.shutdown(wait=False)
        raise

if __name__ == '__main__':
    main()

