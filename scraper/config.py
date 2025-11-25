import os
import logging
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

logger = logging.getLogger(__name__)

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
        logger.info("Validating configuration...")
        
        # S3_BUCKET is always required
        if not cls.S3_BUCKET:
            logger.error("S3_BUCKET is not set")
            raise ValueError("Missing required configuration: S3_BUCKET")
        
        logger.info(f"S3 Bucket: {cls.S3_BUCKET}")
        logger.info(f"AWS Region: {cls.AWS_REGION}")
        logger.info(f"S3 Metadata Key: {cls.S3_METADATA_KEY}")
        logger.info(f"S3 Data Prefix: {cls.S3_DATA_PREFIX}")
        
        # Access keys are optional if using EKS Pod Identity
        if cls.use_iam_role():
            logger.info("Using IAM role authentication (EKS Pod Identity/IRSA)")
        else:
            logger.info("Using AWS access key authentication")
            # If one key is provided, both must be provided
            if cls.AWS_ACCESS_KEY_ID and not cls.AWS_SECRET_ACCESS_KEY:
                logger.error("AWS_SECRET_ACCESS_KEY missing but AWS_ACCESS_KEY_ID is set")
                raise ValueError("AWS_SECRET_ACCESS_KEY required when AWS_ACCESS_KEY_ID is set")
            if cls.AWS_SECRET_ACCESS_KEY and not cls.AWS_ACCESS_KEY_ID:
                logger.error("AWS_ACCESS_KEY_ID missing but AWS_SECRET_ACCESS_KEY is set")
                raise ValueError("AWS_ACCESS_KEY_ID required when AWS_SECRET_ACCESS_KEY is set")
        
        logger.info(f"Server configuration: {cls.SERVER_HOST}:{cls.SERVER_PORT}")
        logger.info(f"Worker configuration: {cls.MAX_CONCURRENT_JOBS} concurrent jobs, {cls.WORKER_THREADS} threads")
        logger.info(f"Default scraping config: max_depth={cls.DEFAULT_MAX_DEPTH}, max_pages={cls.DEFAULT_MAX_PAGES}, rate_limit={cls.DEFAULT_RATE_LIMIT}s")
        logger.info("Configuration validated successfully")

