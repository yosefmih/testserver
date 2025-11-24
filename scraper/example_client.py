#!/usr/bin/env python3
"""
Example client demonstrating how to use the Amharic Scraper API.
"""

import requests
import time
import json
import sys

# Server configuration
SERVER_URL = "http://localhost:8080"

def create_job(seed_urls, config=None):
    """Create a new scraping job."""
    if config is None:
        config = {
            "max_depth": 2,
            "max_pages": 50,
            "rate_limit": 2.0,
            "same_domain_only": True,
            "amharic_threshold": 0.3
        }
    
    payload = {
        "seed_urls": seed_urls,
        "config": config
    }
    
    print(f"Creating scraping job...")
    print(f"Seed URLs: {seed_urls}")
    print(f"Config: {json.dumps(config, indent=2)}")
    
    response = requests.post(f"{SERVER_URL}/api/scrape", json=payload)
    
    if response.status_code == 201:
        job = response.json()
        print(f"\n✓ Job created successfully!")
        print(f"  Job ID: {job['job_id']}")
        print(f"  Status: {job['status']}")
        return job['job_id']
    else:
        print(f"\n✗ Error creating job: {response.status_code}")
        print(f"  {response.text}")
        return None

def check_job_status(job_id):
    """Check the status of a job."""
    response = requests.get(f"{SERVER_URL}/api/jobs/{job_id}")
    
    if response.status_code == 200:
        return response.json()
    else:
        print(f"Error checking job status: {response.status_code}")
        return None

def monitor_job(job_id, poll_interval=5):
    """Monitor a job until completion."""
    print(f"\nMonitoring job {job_id}...")
    print("=" * 60)
    
    while True:
        job = check_job_status(job_id)
        
        if not job:
            break
        
        status = job['status']
        progress = job.get('progress', {})
        
        print(f"\rStatus: {status:12} | "
              f"Pages: {progress.get('pages_scraped', 0):4} | "
              f"Amharic: {progress.get('pages_amharic', 0):4} | "
              f"Queue: {progress.get('queue_size', 0):4} | "
              f"Elapsed: {job.get('stats', {}).get('elapsed_seconds', 0):.1f}s", end='')
        
        if status in ('completed', 'failed', 'cancelled'):
            print()  # New line
            print("=" * 60)
            
            if status == 'completed':
                print(f"\n✓ Job completed successfully!")
                stats = job.get('stats', {})
                print(f"\nFinal Statistics:")
                print(f"  Pages scraped: {stats.get('pages_scraped', 0)}")
                print(f"  Amharic pages: {progress.get('pages_amharic', 0)}")
                print(f"  Total bytes: {stats.get('total_bytes', 0):,}")
                print(f"  Elapsed time: {stats.get('elapsed_seconds', 0):.2f}s")
            elif status == 'failed':
                print(f"\n✗ Job failed: {job.get('error', 'Unknown error')}")
            else:
                print(f"\n⚠ Job was cancelled")
            
            break
        
        time.sleep(poll_interval)

def list_jobs(limit=10):
    """List recent jobs."""
    response = requests.get(f"{SERVER_URL}/api/jobs?limit={limit}")
    
    if response.status_code == 200:
        data = response.json()
        jobs = data.get('jobs', [])
        
        print(f"\nRecent Jobs (showing {len(jobs)}):")
        print("=" * 80)
        print(f"{'Job ID':<38} {'Status':<12} {'Pages':<8} {'Amharic':<8} {'Created'}")
        print("-" * 80)
        
        for job in jobs:
            job_id = job['id']
            status = job['status']
            progress = job.get('progress', {})
            pages = progress.get('pages_scraped', 0)
            amharic = progress.get('pages_amharic', 0)
            created = job.get('created_at', '')[:19]  # Truncate timestamp
            
            print(f"{job_id:<38} {status:<12} {pages:<8} {amharic:<8} {created}")
    else:
        print(f"Error listing jobs: {response.status_code}")

def check_health():
    """Check server health."""
    try:
        response = requests.get(f"{SERVER_URL}/health", timeout=5)
        if response.status_code == 200:
            data = response.json()
            print(f"✓ Server is healthy")
            print(f"  Active jobs: {data.get('active_jobs', 0)}")
            return True
        else:
            print(f"✗ Server returned status {response.status_code}")
            return False
    except requests.exceptions.ConnectionError:
        print(f"✗ Cannot connect to server at {SERVER_URL}")
        return False

def main():
    """Main function."""
    print("Amharic Scraper API Client Example")
    print("=" * 60)
    
    # Check server health
    print("\nChecking server health...")
    if not check_health():
        print("\nPlease start the server first:")
        print("  python server.py")
        sys.exit(1)
    
    # Example seed URLs (replace with actual Amharic websites)
    seed_urls = [
        "https://en.wikipedia.org/wiki/Amharic",  # Example URL
        # Add more URLs here
    ]
    
    # Create a job
    job_id = create_job(seed_urls, config={
        "max_depth": 2,
        "max_pages": 20,  # Small number for testing
        "rate_limit": 2.0,
        "same_domain_only": True,
        "amharic_threshold": 0.2  # Lower threshold for testing
    })
    
    if not job_id:
        sys.exit(1)
    
    # Monitor the job
    monitor_job(job_id, poll_interval=3)
    
    # List recent jobs
    print()
    list_jobs(limit=5)

if __name__ == '__main__':
    main()

