import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

class Config:
    # AWS Configuration
    # For EKS Pod Identity/IRSA, these can be None (boto3 will use IAM role)
    AWS_ACCESS_KEY_ID = os.getenv('AWS_ACCESS_KEY_ID')
    AWS_SECRET_ACCESS_KEY = os.getenv('AWS_SECRET_ACCESS_KEY')
    AWS_REGION = os.getenv('AWS_REGION', 'us-east-1')
    S3_BUCKET = os.getenv('S3_BUCKET')
    
    # S3 Paths
    S3_METADATA_KEY = os.getenv('S3_METADATA_KEY', 'scraper-metadata/jobs.json')
    S3_DATA_PREFIX = os.getenv('S3_DATA_PREFIX', 'scraper-data')
    
    # Server Configuration
    SERVER_HOST = os.getenv('SERVER_HOST', '0.0.0.0')
    SERVER_PORT = int(os.getenv('SERVER_PORT', 8080))
    
    # Worker Configuration
    MAX_CONCURRENT_JOBS = int(os.getenv('MAX_CONCURRENT_JOBS', 3))
    WORKER_THREADS = int(os.getenv('WORKER_THREADS', 5))
    
    # Scraping Defaults
    DEFAULT_RATE_LIMIT = float(os.getenv('DEFAULT_RATE_LIMIT', 2.0))
    DEFAULT_TIMEOUT = int(os.getenv('DEFAULT_TIMEOUT', 10))
    DEFAULT_MAX_DEPTH = int(os.getenv('DEFAULT_MAX_DEPTH', 3))
    DEFAULT_MAX_PAGES = int(os.getenv('DEFAULT_MAX_PAGES', 1000))
    DEFAULT_AMHARIC_THRESHOLD = float(os.getenv('DEFAULT_AMHARIC_THRESHOLD', 0.3))
    
    @classmethod
    def use_iam_role(cls):
        """Check if using IAM role (EKS Pod Identity) instead of access keys."""
        return not (cls.AWS_ACCESS_KEY_ID and cls.AWS_SECRET_ACCESS_KEY)
    
    @classmethod
    def validate(cls):
        """Validate required configuration."""
        # S3_BUCKET is always required
        if not cls.S3_BUCKET:
            raise ValueError("Missing required configuration: S3_BUCKET")
        
        # Access keys are optional if using EKS Pod Identity
        if not cls.use_iam_role():
            # If one key is provided, both must be provided
            if cls.AWS_ACCESS_KEY_ID and not cls.AWS_SECRET_ACCESS_KEY:
                raise ValueError("AWS_SECRET_ACCESS_KEY required when AWS_ACCESS_KEY_ID is set")
            if cls.AWS_SECRET_ACCESS_KEY and not cls.AWS_ACCESS_KEY_ID:
                raise ValueError("AWS_ACCESS_KEY_ID required when AWS_SECRET_ACCESS_KEY is set")

