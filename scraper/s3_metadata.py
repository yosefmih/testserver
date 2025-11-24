import boto3
import json
import logging
from datetime import datetime
from typing import Dict, Optional
from config import Config
import time

logger = logging.getLogger(__name__)

class S3MetadataStore:
    """
    Manages job metadata in S3.
    Uses a single JSON file with optimistic locking.
    """
    
    def __init__(self, bucket: str = None, key: str = None):
        """
        Initialize metadata store.
        
        Args:
            bucket: S3 bucket name
            key: S3 key for metadata file
        """
        self.bucket = bucket or Config.S3_BUCKET
        self.key = key or Config.S3_METADATA_KEY
        
        # Create S3 client - will use IAM role if running in EKS with Pod Identity
        # or explicit credentials if provided
        if Config.use_iam_role():
            logger.info("Using IAM role for S3 access (EKS Pod Identity)")
            self.s3_client = boto3.client('s3', region_name=Config.AWS_REGION)
        else:
            logger.info("Using AWS access keys for S3 access")
            self.s3_client = boto3.client(
                's3',
                aws_access_key_id=Config.AWS_ACCESS_KEY_ID,
                aws_secret_access_key=Config.AWS_SECRET_ACCESS_KEY,
                region_name=Config.AWS_REGION
            )
        
        self._cache = None
        self._etag = None
    
    def load(self) -> Dict:
        """
        Load metadata from S3.
        
        Returns:
            Dictionary with 'jobs' key containing all jobs
        """
        try:
            response = self.s3_client.get_object(Bucket=self.bucket, Key=self.key)
            self._etag = response['ETag']
            self._cache = json.loads(response['Body'].read().decode('utf-8'))
            logger.info(f"Loaded metadata from S3: {len(self._cache.get('jobs', {}))} jobs")
            return self._cache
        except self.s3_client.exceptions.NoSuchKey:
            logger.info("Metadata file not found in S3, creating new one")
            return {"jobs": {}, "version": 1, "last_updated": datetime.utcnow().isoformat()}
        except Exception as e:
            logger.error(f"Error loading metadata from S3: {e}")
            return {"jobs": {}, "version": 1, "last_updated": datetime.utcnow().isoformat()}
    
    def save(self, data: Dict, max_retries: int = 3) -> bool:
        """
        Save metadata to S3 with optimistic locking.
        
        Args:
            data: Metadata dictionary to save
            max_retries: Maximum number of retry attempts
            
        Returns:
            True if successful, False otherwise
        """
        for attempt in range(max_retries):
            try:
                # Update timestamp
                data['last_updated'] = datetime.utcnow().isoformat()
                
                # Prepare put parameters
                params = {
                    'Bucket': self.bucket,
                    'Key': self.key,
                    'Body': json.dumps(data, indent=2),
                    'ContentType': 'application/json'
                }
                
                # Add conditional put if we have an ETag (optimistic locking)
                if self._etag:
                    params['IfMatch'] = self._etag
                
                response = self.s3_client.put_object(**params)
                self._etag = response['ETag']
                self._cache = data
                logger.info(f"Saved metadata to S3 (attempt {attempt + 1})")
                return True
                
            except self.s3_client.exceptions.PreconditionFailed:
                # ETag mismatch - someone else updated the file
                logger.warning(f"Metadata conflict detected, reloading (attempt {attempt + 1})")
                time.sleep(0.1 * (attempt + 1))  # Exponential backoff
                self.load()  # Reload to get latest version
                continue
                
            except Exception as e:
                logger.error(f"Error saving metadata to S3: {e}")
                if attempt == max_retries - 1:
                    return False
                time.sleep(0.1 * (attempt + 1))
        
        return False
    
    def get_job(self, job_id: str) -> Optional[Dict]:
        """
        Get a specific job's metadata.
        
        Args:
            job_id: Job identifier
            
        Returns:
            Job metadata dict or None
        """
        if self._cache is None:
            self.load()
        
        return self._cache.get('jobs', {}).get(job_id)
    
    def update_job(self, job_id: str, updates: Dict) -> bool:
        """
        Update a specific job's metadata.
        
        Args:
            job_id: Job identifier
            updates: Dictionary of fields to update
            
        Returns:
            True if successful, False otherwise
        """
        # Load latest version
        data = self.load()
        
        # Get or create job entry
        if job_id not in data['jobs']:
            data['jobs'][job_id] = {'id': job_id}
        
        # Apply updates
        data['jobs'][job_id].update(updates)
        data['jobs'][job_id]['updated_at'] = datetime.utcnow().isoformat()
        
        # Save back to S3
        return self.save(data)
    
    def list_jobs(self, limit: int = 100) -> list:
        """
        List all jobs.
        
        Args:
            limit: Maximum number of jobs to return
            
        Returns:
            List of job metadata dicts
        """
        if self._cache is None:
            self.load()
        
        jobs = list(self._cache.get('jobs', {}).values())
        
        # Sort by created_at descending
        jobs.sort(key=lambda j: j.get('created_at', ''), reverse=True)
        
        return jobs[:limit]

