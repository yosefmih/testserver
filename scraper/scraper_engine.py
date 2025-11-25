import requests
import time
import logging
from collections import deque
from urllib.parse import urljoin
from urllib.robotparser import RobotFileParser
from typing import Set, Callable, Optional, Dict
from datetime import datetime

from url_utils import URLUtils
from text_processor import TextProcessor
from amharic_detector import AmharicDetector
from s3_storage import S3Storage

logger = logging.getLogger(__name__)

class ScraperEngine:
    """
    Core web scraping engine with BFS traversal.
    """
    
    def __init__(
        self,
        job_id: str,
        seed_urls: list,
        max_depth: int = 3,
        max_pages: int = 1000,
        rate_limit: float = 2.0,
        timeout: int = 10,
        same_domain_only: bool = True,
        amharic_threshold: float = 0.3,
        progress_callback: Optional[Callable] = None
    ):
        """
        Initialize scraper engine.
        
        Args:
            job_id: Unique job identifier
            seed_urls: List of starting URLs
            max_depth: Maximum crawl depth
            max_pages: Maximum pages to scrape
            rate_limit: Seconds between requests per domain
            timeout: Request timeout in seconds
            same_domain_only: Only follow links on same domain
            amharic_threshold: Minimum Amharic percentage to save
            progress_callback: Function to call with progress updates
        """
        self.job_id = job_id
        self.seed_urls = seed_urls
        self.max_depth = max_depth
        self.max_pages = max_pages
        self.rate_limit = rate_limit
        self.timeout = timeout
        self.same_domain_only = same_domain_only
        self.amharic_threshold = amharic_threshold
        self.progress_callback = progress_callback
        
        # State
        self.url_queue = deque()
        self.visited_urls: Set[str] = set()
        self.pages_scraped = 0
        self.pages_amharic = 0
        self.total_bytes = 0
        self.current_url = None
        self.start_time = None
        self.domain_last_request = {}  # domain -> timestamp
        self.robots_cache = {}
        
        # Components
        self.text_processor = TextProcessor()
        self.amharic_detector = AmharicDetector(threshold=amharic_threshold)
        self.s3_storage = S3Storage()
        
        # Checkpointing
        self.checkpoint_interval = 10  # Save checkpoint every N pages
        self.last_checkpoint = 0
        
        # Try to load checkpoint first
        loaded = self._load_checkpoint()
        
        if not loaded:
            # Initialize queue with seed URLs only if no checkpoint
            logger.info("No checkpoint found, starting fresh")
            for url in seed_urls:
                if URLUtils.is_valid_http_url(url):
                    self.url_queue.append((url, 0))
    
    def run(self) -> Dict:
        """
        Run the scraping process.
        
        Returns:
            Final statistics dictionary
        """
        self.start_time = time.time()
        logger.info("=" * 60)
        logger.info(f"Starting scraper for job {self.job_id}")
        logger.info(f"Seed URLs: {self.seed_urls}")
        logger.info(f"Configuration:")
        logger.info(f"  Max depth: {self.max_depth}")
        logger.info(f"  Max pages: {self.max_pages}")
        logger.info(f"  Rate limit: {self.rate_limit}s")
        logger.info(f"  Timeout: {self.timeout}s")
        logger.info(f"  Same domain only: {self.same_domain_only}")
        logger.info(f"  Amharic threshold: {self.amharic_threshold * 100}%")
        logger.info("=" * 60)
        
        try:
            while self.url_queue and self.pages_scraped < self.max_pages:
                url, depth = self.url_queue.popleft()
                
                # Skip if already visited
                url_hash = URLUtils.get_hash(url)
                if url_hash in self.visited_urls:
                    continue
                
                # Mark as visited
                self.visited_urls.add(url_hash)
                self.current_url = url
                
                # Scrape the URL
                self._scrape_url(url, depth)
                
                # Report progress
                if self.progress_callback:
                    self.progress_callback(self._get_progress())
                
                # Save checkpoint periodically
                if self.pages_scraped - self.last_checkpoint >= self.checkpoint_interval:
                    self._save_checkpoint()
                    self.last_checkpoint = self.pages_scraped
                
                # Log progress every 10 pages
                if self.pages_scraped % 10 == 0:
                    logger.info(f"Job {self.job_id} progress: {self.pages_scraped} pages scraped, {self.pages_amharic} Amharic, {len(self.url_queue)} in queue")
                
                # Rate limiting
                self._rate_limit_delay(url)
            
            logger.info("=" * 60)
            logger.info(f"Scraping completed for job {self.job_id}")
            logger.info(f"Final stats: {self.pages_scraped} pages scraped, {self.pages_amharic} Amharic pages saved")
            logger.info("=" * 60)
            
            # Delete checkpoint on successful completion
            self._delete_checkpoint()
            
        except Exception as e:
            logger.error(f"Error during scraping: {e}")
            # Save checkpoint before failing so we can resume
            self._save_checkpoint()
            raise
        
        return self._get_final_stats()
    
    def _scrape_url(self, url: str, depth: int):
        """Scrape a single URL."""
        logger.info(f"=" * 80)
        logger.info(f"🔍 Processing URL [Depth: {depth}]: {url}")
        
        try:
            # Check robots.txt
            logger.debug(f"Checking robots.txt for: {url}")
            if not self._can_fetch(url):
                logger.warning(f"❌ SKIPPED - Robots.txt disallows: {url}")
                return
            logger.debug(f"✓ Robots.txt allows fetching")
            
            # Make HTTP request
            headers = {
                'User-Agent': 'Mozilla/5.0 (compatible; AmharicScraperBot/1.0)'
            }
            
            logger.debug(f"Making HTTP request to: {url}")
            response = requests.get(
                url,
                headers=headers,
                timeout=self.timeout,
                allow_redirects=True
            )
            
            logger.info(f"HTTP {response.status_code} - Size: {len(response.content)} bytes")
            
            if response.status_code != 200:
                logger.warning(f"❌ SKIPPED - Non-200 status for {url}: {response.status_code}")
                return
            
            # Only process HTML content
            content_type = response.headers.get('Content-Type', '')
            logger.debug(f"Content-Type: {content_type}")
            if 'text/html' not in content_type.lower():
                logger.warning(f"❌ SKIPPED - Non-HTML content: {url} (type: {content_type})")
                return
            
            logger.info(f"✓ Valid HTML page, extracting text...")
            
            # Extract text
            text = self.text_processor.extract_text(response.text)
            title = self.text_processor.extract_title(response.text)
            
            logger.info(f"📄 Title: {title[:100] if title else '(no title)'}")
            logger.info(f"📝 Extracted text length: {len(text)} characters")
            logger.debug(f"First 200 chars of text: {text[:200]}")
            
            if not text or len(text) < 100:
                logger.warning(f"❌ SKIPPED - Text too short ({len(text)} chars): {url}")
                return
            
            # Check if Amharic
            logger.info(f"🔍 Detecting Amharic in text...")
            is_amharic, amharic_pct, amharic_stats = self.amharic_detector.detect(text)
            
            logger.info(f"📊 Amharic Detection Results:")
            logger.info(f"   - Total characters: {amharic_stats.get('total_chars', 0)}")
            logger.info(f"   - Non-whitespace: {amharic_stats.get('non_whitespace', 0)}")
            logger.info(f"   - Amharic characters: {amharic_stats.get('amharic_chars', 0)}")
            logger.info(f"   - Amharic percentage: {amharic_pct:.2%}")
            logger.info(f"   - Threshold: {self.amharic_threshold:.2%}")
            logger.info(f"   - Is Amharic: {is_amharic}")
            
            self.pages_scraped += 1
            self.total_bytes += len(response.content)
            
            # Save if Amharic
            if is_amharic:
                logger.info(f"✅ SAVING - Page meets Amharic threshold!")
                self._save_text(url, text, title, depth, amharic_pct, amharic_stats)
                self.pages_amharic += 1
            else:
                logger.warning(f"❌ NOT SAVING - Below Amharic threshold ({amharic_pct:.2%} < {self.amharic_threshold:.2%})")
            
            # Extract links for further crawling
            if depth < self.max_depth:
                logger.info(f"🔗 Extracting links (current depth: {depth}, max: {self.max_depth})...")
                self._extract_and_queue_links(url, response.text, depth)
            else:
                logger.info(f"⚠️  Max depth reached ({depth}), not extracting links")
        
        except requests.RequestException as e:
            logger.error(f"❌ REQUEST ERROR for {url}: {type(e).__name__}: {e}")
        except Exception as e:
            logger.error(f"❌ UNEXPECTED ERROR scraping {url}: {type(e).__name__}: {e}", exc_info=True)
    
    def _save_text(self, url: str, text: str, title: str, depth: int, amharic_pct: float, amharic_stats: Dict):
        """Save scraped text to S3."""
        url_hash = URLUtils.get_hash(url)
        word_count = len(text.split())
        
        logger.info(f"💾 Preparing to save to S3:")
        logger.info(f"   - Job ID: {self.job_id}")
        logger.info(f"   - URL Hash: {url_hash}")
        logger.info(f"   - Word count: {word_count}")
        logger.info(f"   - Text size: {len(text)} bytes")
        
        metadata = {
            'url': url,
            'title': title,
            'timestamp': datetime.utcnow().isoformat(),
            'depth': depth,
            'word_count': word_count,
            'amharic_percentage': amharic_pct,
            'amharic_chars': amharic_stats.get('amharic_chars', 0)
        }
        
        success = self.s3_storage.save_text(self.job_id, url_hash, text, metadata)
        if success:
            logger.info(f"✅ Successfully saved to S3")
        else:
            logger.error(f"❌ Failed to save to S3")
    
    def _extract_and_queue_links(self, base_url: str, html: str, current_depth: int):
        """Extract links from HTML and add to queue."""
        try:
            from bs4 import BeautifulSoup
            soup = BeautifulSoup(html, 'lxml')
            
            all_links = soup.find_all('a', href=True)
            logger.info(f"📎 Found {len(all_links)} total <a> tags")
            
            links_added = 0
            links_skipped_invalid = 0
            links_skipped_domain = 0
            links_skipped_visited = 0
            
            for tag in all_links:
                if links_added >= 50:  # Limit links per page
                    logger.info(f"⚠️  Reached link limit (50), stopping extraction")
                    break
                
                href = tag['href']
                absolute_url = urljoin(base_url, href)
                
                # Validate URL
                if not URLUtils.is_valid_http_url(absolute_url):
                    links_skipped_invalid += 1
                    logger.debug(f"Skipped invalid URL: {href}")
                    continue
                
                # Check same domain constraint
                if self.same_domain_only:
                    # Check against all seed URLs
                    if not any(URLUtils.same_domain(absolute_url, seed) for seed in self.seed_urls):
                        links_skipped_domain += 1
                        logger.debug(f"Skipped different domain: {absolute_url}")
                        continue
                
                # Skip if already visited
                url_hash = URLUtils.get_hash(absolute_url)
                if url_hash in self.visited_urls:
                    links_skipped_visited += 1
                    logger.debug(f"Skipped already visited: {absolute_url}")
                    continue
                
                # Add to queue
                self.url_queue.append((absolute_url, current_depth + 1))
                links_added += 1
                logger.debug(f"✓ Queued: {absolute_url}")
            
            logger.info(f"🔗 Link extraction summary:")
            logger.info(f"   - Total found: {len(all_links)}")
            logger.info(f"   - Added to queue: {links_added}")
            logger.info(f"   - Skipped (invalid): {links_skipped_invalid}")
            logger.info(f"   - Skipped (different domain): {links_skipped_domain}")
            logger.info(f"   - Skipped (already visited): {links_skipped_visited}")
            logger.info(f"   - Current queue size: {len(self.url_queue)}")
            
        except Exception as e:
            logger.error(f"❌ Error extracting links from {base_url}: {type(e).__name__}: {e}", exc_info=True)
    
    def _can_fetch(self, url: str) -> bool:
        """Check robots.txt for URL."""
        try:
            domain = URLUtils.get_domain(url)
            robot_url = f"{url.split('://')[0]}://{domain}/robots.txt"
            
            if robot_url not in self.robots_cache:
                rp = RobotFileParser()
                rp.set_url(robot_url)
                try:
                    rp.read()
                    self.robots_cache[robot_url] = rp
                except:
                    # If can't read robots.txt, assume allowed
                    return True
            
            rp = self.robots_cache.get(robot_url)
            return rp is None or rp.can_fetch("*", url)
        except:
            return True
    
    def _rate_limit_delay(self, url: str):
        """Apply rate limiting per domain."""
        domain = URLUtils.get_domain(url)
        last_request = self.domain_last_request.get(domain, 0)
        elapsed = time.time() - last_request
        
        if elapsed < self.rate_limit:
            sleep_time = self.rate_limit - elapsed
            time.sleep(sleep_time)
        
        self.domain_last_request[domain] = time.time()
    
    def _get_progress(self) -> Dict:
        """Get current progress statistics."""
        elapsed = time.time() - self.start_time if self.start_time else 0
        
        return {
            'pages_scraped': self.pages_scraped,
            'pages_amharic': self.pages_amharic,
            'queue_size': len(self.url_queue),
            'current_url': self.current_url,
            'total_bytes': self.total_bytes,
            'elapsed_seconds': round(elapsed, 2)
        }
    
    def _get_final_stats(self) -> Dict:
        """Get final statistics."""
        elapsed = time.time() - self.start_time if self.start_time else 0
        
        return {
            'pages_scraped': self.pages_scraped,
            'pages_amharic': self.pages_amharic,
            'total_bytes': self.total_bytes,
            'elapsed_seconds': round(elapsed, 2),
            'urls_visited': len(self.visited_urls)
        }
    
    def _save_checkpoint(self):
        """Save current scraping state to S3 for recovery."""
        try:
            import json
            from config import Config
            
            checkpoint_data = {
                'job_id': self.job_id,
                'timestamp': datetime.utcnow().isoformat(),
                'pages_scraped': self.pages_scraped,
                'pages_amharic': self.pages_amharic,
                'total_bytes': self.total_bytes,
                'visited_urls': list(self.visited_urls),  # Convert set to list
                'url_queue': list(self.url_queue),  # Convert deque to list
            }
            
            checkpoint_key = f"{Config.S3_DATA_PREFIX}/{self.job_id}/checkpoint.json"
            
            logger.info(f"💾 Saving checkpoint:")
            logger.info(f"   - Pages scraped: {self.pages_scraped}")
            logger.info(f"   - Visited URLs: {len(self.visited_urls)}")
            logger.info(f"   - Queue size: {len(self.url_queue)}")
            
            self.s3_storage.s3_client.put_object(
                Bucket=self.s3_storage.bucket,
                Key=checkpoint_key,
                Body=json.dumps(checkpoint_data, indent=2).encode('utf-8'),
                ContentType='application/json'
            )
            
            logger.info(f"✅ Checkpoint saved to s3://{self.s3_storage.bucket}/{checkpoint_key}")
            
        except Exception as e:
            logger.error(f"❌ Failed to save checkpoint: {e}", exc_info=True)
    
    def _load_checkpoint(self) -> bool:
        """Load checkpoint from S3 if it exists."""
        try:
            import json
            from config import Config
            
            checkpoint_key = f"{Config.S3_DATA_PREFIX}/{self.job_id}/checkpoint.json"
            
            logger.info(f"🔍 Looking for checkpoint: s3://{self.s3_storage.bucket}/{checkpoint_key}")
            
            response = self.s3_storage.s3_client.get_object(
                Bucket=self.s3_storage.bucket,
                Key=checkpoint_key
            )
            
            checkpoint_data = json.loads(response['Body'].read().decode('utf-8'))
            
            logger.info(f"✅ Found checkpoint from {checkpoint_data.get('timestamp')}")
            logger.info(f"   - Pages scraped: {checkpoint_data.get('pages_scraped', 0)}")
            logger.info(f"   - Visited URLs: {len(checkpoint_data.get('visited_urls', []))}")
            logger.info(f"   - Queue size: {len(checkpoint_data.get('url_queue', []))}")
            
            # Restore state
            self.pages_scraped = checkpoint_data.get('pages_scraped', 0)
            self.pages_amharic = checkpoint_data.get('pages_amharic', 0)
            self.total_bytes = checkpoint_data.get('total_bytes', 0)
            self.visited_urls = set(checkpoint_data.get('visited_urls', []))
            self.url_queue = deque(checkpoint_data.get('url_queue', []))
            self.last_checkpoint = self.pages_scraped
            
            logger.info(f"🔄 Resuming from checkpoint - {len(self.url_queue)} URLs in queue")
            
            return True
            
        except self.s3_storage.s3_client.exceptions.NoSuchKey:
            logger.info(f"No checkpoint found (first run or completed job)")
            return False
        except Exception as e:
            logger.warning(f"Could not load checkpoint: {e}")
            return False
    
    def _delete_checkpoint(self):
        """Delete checkpoint after successful completion."""
        try:
            from config import Config
            checkpoint_key = f"{Config.S3_DATA_PREFIX}/{self.job_id}/checkpoint.json"
            
            self.s3_storage.s3_client.delete_object(
                Bucket=self.s3_storage.bucket,
                Key=checkpoint_key
            )
            
            logger.info(f"🗑️  Deleted checkpoint (job complete)")
            
        except Exception as e:
            logger.debug(f"Could not delete checkpoint: {e}")

