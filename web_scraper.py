#!/usr/bin/env python3
import argparse
import psycopg2
import os
import sys
import time
import requests
import json
from datetime import datetime
from urllib.parse import urlparse, urljoin, urldefrag
from urllib.robotparser import RobotFileParser
import random
from collections import deque
import hashlib
import logging

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class WebScraper:
    def __init__(self, seed_urls, duration_minutes=5, max_depth=3):
        self.seed_urls = seed_urls
        self.duration_seconds = duration_minutes * 60
        self.max_depth = max_depth
        self.visited_urls = set()
        self.url_queue = deque()
        self.start_time = time.time()
        self.pages_scraped = 0
        self.total_bytes = 0
        self.robots_cache = {}
        
        # Initialize queue with seed URLs
        for url in seed_urls:
            self.url_queue.append((url, 0))  # (url, depth)
    
    def init_db(self, conn):
        """Initialize the database table if it doesn't exist"""
        with conn.cursor() as cur:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS scraped_pages (
                    id SERIAL PRIMARY KEY,
                    url TEXT NOT NULL,
                    url_hash VARCHAR(64) NOT NULL,
                    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    status_code INTEGER,
                    title TEXT,
                    content_length INTEGER,
                    links_found INTEGER,
                    depth INTEGER,
                    response_time_ms INTEGER,
                    error TEXT,
                    domain VARCHAR(255),
                    UNIQUE(url_hash)
                )
            """)
            
            # Create index for faster lookups
            cur.execute("""
                CREATE INDEX IF NOT EXISTS idx_url_hash ON scraped_pages(url_hash)
            """)
            
            cur.execute("""
                CREATE INDEX IF NOT EXISTS idx_timestamp ON scraped_pages(timestamp)
            """)
            
            conn.commit()
    
    def get_url_hash(self, url):
        """Generate a hash for URL to handle long URLs"""
        return hashlib.sha256(url.encode('utf-8')).hexdigest()
    
    def is_url_visited(self, conn, url):
        """Check if URL has been visited before"""
        url_hash = self.get_url_hash(url)
        if url_hash in self.visited_urls:
            return True
            
        with conn.cursor() as cur:
            cur.execute("SELECT 1 FROM scraped_pages WHERE url_hash = %s", (url_hash,))
            exists = cur.fetchone() is not None
            if exists:
                self.visited_urls.add(url_hash)
            return exists
    
    def can_fetch(self, url):
        """Check robots.txt for the given URL"""
        try:
            parsed = urlparse(url)
            robot_url = f"{parsed.scheme}://{parsed.netloc}/robots.txt"
            
            if robot_url not in self.robots_cache:
                rp = RobotFileParser()
                rp.set_url(robot_url)
                try:
                    rp.read()
                    self.robots_cache[robot_url] = rp
                except:
                    # If we can't read robots.txt, assume we can fetch
                    return True
            
            rp = self.robots_cache.get(robot_url)
            return rp is None or rp.can_fetch("*", url)
        except:
            return True
    
    def extract_links(self, url, html_content):
        """Extract links from HTML content"""
        # Simple link extraction - in production, use BeautifulSoup
        links = []
        import re
        href_pattern = re.compile(r'href=[\'"]?([^\'" >]+)', re.IGNORECASE)
        
        for match in href_pattern.finditer(html_content):
            link = match.group(1)
            absolute_link = urljoin(url, link)
            # Remove fragment
            absolute_link, _ = urldefrag(absolute_link)
            
            # Only include HTTP/HTTPS links
            if absolute_link.startswith(('http://', 'https://')):
                links.append(absolute_link)
        
        return links
    
    def extract_title(self, html_content):
        """Extract title from HTML content"""
        import re
        title_match = re.search(r'<title[^>]*>([^<]+)</title>', html_content, re.IGNORECASE)
        return title_match.group(1).strip() if title_match else None
    
    def scrape_url(self, url, depth):
        """Scrape a single URL"""
        start_time = time.time()
        result = {
            'url': url,
            'url_hash': self.get_url_hash(url),
            'depth': depth,
            'timestamp': datetime.now(),
            'domain': urlparse(url).netloc
        }
        
        try:
            # Check robots.txt
            if not self.can_fetch(url):
                logger.info(f"Robots.txt disallows: {url}")
                result['error'] = 'Disallowed by robots.txt'
                result['status_code'] = None
                return result
            
            # Make request with timeout
            headers = {
                'User-Agent': 'Mozilla/5.0 (compatible; KubernetesTestBot/1.0)'
            }
            response = requests.get(url, headers=headers, timeout=10, allow_redirects=True)
            
            response_time = int((time.time() - start_time) * 1000)
            
            result['status_code'] = response.status_code
            result['response_time_ms'] = response_time
            result['content_length'] = len(response.content)
            
            if response.status_code == 200:
                # Extract title
                result['title'] = self.extract_title(response.text)
                
                # Extract links for further crawling
                links = self.extract_links(response.url, response.text)
                result['links_found'] = len(links)
                
                # Add new links to queue if within depth limit
                if depth < self.max_depth:
                    for link in links[:20]:  # Limit links per page
                        self.url_queue.append((link, depth + 1))
            else:
                result['links_found'] = 0
                result['title'] = None
            
            result['error'] = None
            
        except requests.RequestException as e:
            result['error'] = str(e)
            result['status_code'] = None
            result['response_time_ms'] = int((time.time() - start_time) * 1000)
            result['content_length'] = 0
            result['links_found'] = 0
            result['title'] = None
            logger.error(f"Error scraping {url}: {e}")
        
        return result
    
    def save_result(self, conn, result):
        """Save scraping result to database"""
        with conn.cursor() as cur:
            try:
                cur.execute("""
                    INSERT INTO scraped_pages 
                    (url, url_hash, status_code, title, content_length, links_found, 
                     depth, response_time_ms, error, domain, timestamp)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (url_hash) DO NOTHING
                """, (
                    result['url'],
                    result['url_hash'],
                    result.get('status_code'),
                    result.get('title'),
                    result.get('content_length', 0),
                    result.get('links_found', 0),
                    result['depth'],
                    result.get('response_time_ms'),
                    result.get('error'),
                    result['domain'],
                    result['timestamp']
                ))
                conn.commit()
                return cur.rowcount > 0
            except Exception as e:
                logger.error(f"Error saving to database: {e}")
                conn.rollback()
                return False
    
    def log_stats(self, conn):
        """Log scraping statistics"""
        elapsed = time.time() - self.start_time
        pages_per_minute = (self.pages_scraped / elapsed) * 60 if elapsed > 0 else 0
        
        # Get domain statistics
        with conn.cursor() as cur:
            cur.execute("""
                SELECT domain, COUNT(*) as count 
                FROM scraped_pages 
                WHERE timestamp >= %s
                GROUP BY domain 
                ORDER BY count DESC 
                LIMIT 5
            """, (datetime.fromtimestamp(self.start_time),))
            
            top_domains = cur.fetchall()
        
        stats = {
            "timestamp": datetime.now().isoformat(),
            "elapsed_seconds": round(elapsed, 2),
            "pages_scraped": self.pages_scraped,
            "pages_per_minute": round(pages_per_minute, 2),
            "queue_size": len(self.url_queue),
            "visited_urls": len(self.visited_urls),
            "top_domains": [{"domain": d[0], "count": d[1]} for d in top_domains]
        }
        
        logger.info(f"Stats: {json.dumps(stats, indent=2)}")
    
    def run(self, conn):
        """Main scraping loop"""
        logger.info(f"Starting web scraper")
        logger.info(f"Duration: {self.duration_seconds}s, Max depth: {self.max_depth}")
        logger.info(f"Seed URLs: {self.seed_urls}")
        
        last_stats_time = time.time()
        
        while time.time() - self.start_time < self.duration_seconds:
            # Check if we have URLs to process
            if not self.url_queue:
                logger.info("URL queue empty, waiting...")
                time.sleep(5)
                continue
            
            url, depth = self.url_queue.popleft()
            
            # Skip if already visited
            if self.is_url_visited(conn, url):
                continue
            
            # Mark as visited
            self.visited_urls.add(self.get_url_hash(url))
            
            # Scrape the URL
            logger.info(f"Scraping: {url} (depth: {depth})")
            result = self.scrape_url(url, depth)
            
            # Save to database
            if self.save_result(conn, result):
                self.pages_scraped += 1
                self.total_bytes += result.get('content_length', 0)
            
            # Be polite - random delay between requests
            delay = random.uniform(0.5, 2.0)
            time.sleep(delay)
            
            # Log stats every 30 seconds
            if time.time() - last_stats_time >= 30:
                self.log_stats(conn)
                last_stats_time = time.time()
        
        # Final stats
        logger.info(f"\nScraping completed!")
        logger.info(f"Total pages scraped: {self.pages_scraped}")
        logger.info(f"Total URLs visited: {len(self.visited_urls)}")
        self.log_stats(conn)

def main():
    parser = argparse.ArgumentParser(description='Web scraper for Kubernetes testing')
    parser.add_argument('--duration', type=int, default=5,
                      help='Duration in minutes (default: 5)')
    parser.add_argument('--max-depth', type=int, default=3,
                      help='Maximum crawl depth (default: 3)')
    
    args = parser.parse_args()
    
    # Get seed URLs from environment variable
    seed_urls_str = os.environ.get('SEED_URLS', '')
    if not seed_urls_str:
        logger.error("No seed URLs provided. Set SEED_URLS environment variable (comma-separated)")
        sys.exit(1)
    
    seed_urls = [url.strip() for url in seed_urls_str.split(',') if url.strip()]
    if not seed_urls:
        logger.error("No valid seed URLs found")
        sys.exit(1)
    
    # Get database credentials from environment variables
    db_host = os.environ.get('DB_HOST')
    db_port = os.environ.get('DB_PORT', '5432')
    db_name = os.environ.get('DB_NAME')
    db_user = os.environ.get('DB_USER')
    db_pass = os.environ.get('DB_PASS')

    # Validate required environment variables
    missing_vars = []
    for var_name in ['DB_HOST', 'DB_NAME', 'DB_USER', 'DB_PASS']:
        if not os.environ.get(var_name):
            missing_vars.append(var_name)
    
    if missing_vars:
        logger.error(f"Missing required environment variables: {', '.join(missing_vars)}")
        sys.exit(1)
    
    try:
        # Connect to database
        conn = psycopg2.connect(
            host=db_host,
            port=db_port,
            dbname=db_name,
            user=db_user,
            password=db_pass
        )
        
        # Initialize scraper
        scraper = WebScraper(
            seed_urls=seed_urls,
            duration_minutes=args.duration,
            max_depth=args.max_depth
        )
        
        # Initialize database
        scraper.init_db(conn)
        
        # Run scraper
        scraper.run(conn)
        
    except psycopg2.Error as e:
        logger.error(f"Database error: {e}")
        sys.exit(1)
    except KeyboardInterrupt:
        logger.info("Scraping interrupted by user")
        sys.exit(1)
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        sys.exit(1)
    finally:
        if 'conn' in locals():
            conn.close()

if __name__ == "__main__":
    main() 