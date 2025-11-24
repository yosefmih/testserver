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
        
        # Initialize queue
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
        logger.info(f"Starting scraper for job {self.job_id}")
        logger.info(f"Seed URLs: {self.seed_urls}")
        logger.info(f"Max depth: {self.max_depth}, Max pages: {self.max_pages}")
        
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
                
                # Rate limiting
                self._rate_limit_delay(url)
            
            logger.info(f"Scraping completed for job {self.job_id}")
            
        except Exception as e:
            logger.error(f"Error during scraping: {e}")
            raise
        
        return self._get_final_stats()
    
    def _scrape_url(self, url: str, depth: int):
        """Scrape a single URL."""
        try:
            # Check robots.txt
            if not self._can_fetch(url):
                logger.info(f"Robots.txt disallows: {url}")
                return
            
            # Make HTTP request
            headers = {
                'User-Agent': 'Mozilla/5.0 (compatible; AmharicScraperBot/1.0)'
            }
            
            response = requests.get(
                url,
                headers=headers,
                timeout=self.timeout,
                allow_redirects=True
            )
            
            if response.status_code != 200:
                logger.warning(f"Non-200 status for {url}: {response.status_code}")
                return
            
            # Only process HTML content
            content_type = response.headers.get('Content-Type', '')
            if 'text/html' not in content_type.lower():
                logger.debug(f"Skipping non-HTML content: {url}")
                return
            
            # Extract text
            text = self.text_processor.extract_text(response.text)
            title = self.text_processor.extract_title(response.text)
            
            if not text or len(text) < 100:
                logger.debug(f"Text too short, skipping: {url}")
                return
            
            # Check if Amharic
            is_amharic, amharic_pct, amharic_stats = self.amharic_detector.detect(text)
            
            self.pages_scraped += 1
            self.total_bytes += len(response.content)
            
            logger.info(f"Scraped [{self.pages_scraped}]: {url} (Amharic: {amharic_pct:.2%})")
            
            # Save if Amharic
            if is_amharic:
                self._save_text(url, text, title, depth, amharic_pct, amharic_stats)
                self.pages_amharic += 1
            
            # Extract links for further crawling
            if depth < self.max_depth:
                self._extract_and_queue_links(url, response.text, depth)
        
        except requests.RequestException as e:
            logger.error(f"Request error for {url}: {e}")
        except Exception as e:
            logger.error(f"Error scraping {url}: {e}")
    
    def _save_text(self, url: str, text: str, title: str, depth: int, amharic_pct: float, amharic_stats: Dict):
        """Save scraped text to S3."""
        url_hash = URLUtils.get_hash(url)
        
        metadata = {
            'url': url,
            'title': title,
            'timestamp': datetime.utcnow().isoformat(),
            'depth': depth,
            'word_count': len(text.split()),
            'amharic_percentage': amharic_pct,
            'amharic_chars': amharic_stats.get('amharic_chars', 0)
        }
        
        self.s3_storage.save_text(self.job_id, url_hash, text, metadata)
    
    def _extract_and_queue_links(self, base_url: str, html: str, current_depth: int):
        """Extract links from HTML and add to queue."""
        try:
            from bs4 import BeautifulSoup
            soup = BeautifulSoup(html, 'lxml')
            
            links_added = 0
            for tag in soup.find_all('a', href=True):
                if links_added >= 50:  # Limit links per page
                    break
                
                href = tag['href']
                absolute_url = urljoin(base_url, href)
                
                # Validate URL
                if not URLUtils.is_valid_http_url(absolute_url):
                    continue
                
                # Check same domain constraint
                if self.same_domain_only:
                    # Check against all seed URLs
                    if not any(URLUtils.same_domain(absolute_url, seed) for seed in self.seed_urls):
                        continue
                
                # Skip if already visited
                url_hash = URLUtils.get_hash(absolute_url)
                if url_hash in self.visited_urls:
                    continue
                
                # Add to queue
                self.url_queue.append((absolute_url, current_depth + 1))
                links_added += 1
            
            logger.debug(f"Added {links_added} links from {base_url}")
            
        except Exception as e:
            logger.error(f"Error extracting links from {base_url}: {e}")
    
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

