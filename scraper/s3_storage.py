import boto3
import logging
from datetime import datetime
from typing import Optional, Dict
from config import Config

logger = logging.getLogger(__name__)

class S3Storage:
    """Handle S3 storage operations for scraped text."""
    
    def __init__(self, bucket: str = None, prefix: str = None):
        """
        Initialize S3 storage.
        
        Args:
            bucket: S3 bucket name (defaults to Config.S3_BUCKET)
            prefix: S3 prefix for data (defaults to Config.S3_DATA_PREFIX)
        """
        self.bucket = bucket or Config.S3_BUCKET
        self.prefix = prefix or Config.S3_DATA_PREFIX
        
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
    
    def save_text(self, job_id: str, url_hash: str, text: str, metadata: Dict) -> bool:
        """
        Save scraped text to S3.
        
        Args:
            job_id: Job identifier
            url_hash: Hash of URL
            text: Text content to save
            metadata: Additional metadata (url, timestamp, stats, etc.)
            
        Returns:
            True if successful, False otherwise
        """
        try:
            # Generate S3 key
            key = self._generate_key(job_id, url_hash)
            
            # Prepare metadata for S3
            s3_metadata = {
                'url': metadata.get('url', '')[:1024],  # S3 metadata has size limits
                'scraped_at': metadata.get('timestamp', datetime.utcnow().isoformat()),
                'word_count': str(metadata.get('word_count', 0)),
                'amharic_percentage': str(metadata.get('amharic_percentage', 0.0)),
                'depth': str(metadata.get('depth', 0))
            }
            
            # Upload to S3
            self.s3_client.put_object(
                Bucket=self.bucket,
                Key=key,
                Body=text.encode('utf-8'),
                ContentType='text/plain; charset=utf-8',
                Metadata=s3_metadata
            )
            
            logger.info(f"Saved text to S3: {key}")
            return True
            
        except Exception as e:
            logger.error(f"Error saving to S3: {e}")
            return False
    
    def _generate_key(self, job_id: str, url_hash: str) -> str:
        """
        Generate S3 key for text file.
        
        Format: {prefix}/{job_id}/{url_hash}.txt
        """
        return f"{self.prefix}/{job_id}/{url_hash}.txt"
    
    def list_job_files(self, job_id: str) -> list:
        """
        List all files for a specific job.
        
        Args:
            job_id: Job identifier
            
        Returns:
            List of S3 keys
        """
        try:
            prefix = f"{self.prefix}/{job_id}/"
            response = self.s3_client.list_objects_v2(
                Bucket=self.bucket,
                Prefix=prefix
            )
            
            if 'Contents' not in response:
                return []
            
            return [obj['Key'] for obj in response['Contents']]
            
        except Exception as e:
            logger.error(f"Error listing job files: {e}")
            return []
    
    def get_file_metadata(self, key: str) -> Optional[Dict]:
        """
        Get metadata for a specific file.
        
        Args:
            key: S3 key
            
        Returns:
            Metadata dict or None
        """
        try:
            response = self.s3_client.head_object(
                Bucket=self.bucket,
                Key=key
            )
            return response.get('Metadata', {})
        except Exception as e:
            logger.error(f"Error getting file metadata: {e}")
            return None

