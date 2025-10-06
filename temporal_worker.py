#!/usr/bin/env python3
"""
Simple Temporal worker for testing KEDA autoscaling.
Demonstrates basic workflow and activity patterns.
"""

import asyncio
import logging
import os
from datetime import timedelta, datetime
from temporalio import workflow
from temporalio.client import Client
from temporalio.worker import Worker
from temporalio import activity
from dotenv import load_dotenv
from concurrent.futures import ThreadPoolExecutor
from typing import List, Optional
import requests
from urllib.parse import urlparse, urljoin, urldefrag
import re
import hashlib
import psycopg2
from dataclasses import dataclass, asdict

# Load environment variables from .env file (development only)
if os.path.exists('.env'):
    load_dotenv()

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Temporal configuration - will be validated when worker starts
def get_temporal_config():
    """Get and validate Temporal configuration from environment."""
    host = os.getenv("TEMPORAL_HOST")  # e.g., "your-namespace.tmprl.cloud:7233"
    namespace = os.getenv("TEMPORAL_NAMESPACE")  # e.g., "your-namespace.accounting"
    task_queue = os.getenv("TASK_QUEUE")  # e.g., "order-processing-queue"
    api_key = os.getenv("TEMPORAL_API_KEY")  # Required for Temporal Cloud
    
    # Validate required environment variables
    missing = []
    if not host:
        missing.append("TEMPORAL_HOST")
    if not namespace:
        missing.append("TEMPORAL_NAMESPACE") 
    if not task_queue:
        missing.append("TASK_QUEUE")
    if not api_key:
        missing.append("TEMPORAL_API_KEY")
    
    if missing:
        raise ValueError(f"Missing required environment variables: {', '.join(missing)}")
    
    return host, namespace, task_queue, api_key


@activity.defn
async def process_order_activity(order_id: str) -> str:
    """
    Simple activity that simulates order processing.
    """
    logger.info(f"Processing order: {order_id}")
    
    # Simulate some work
    await asyncio.sleep(2)
    
    result = f"Order {order_id} processed successfully"
    logger.info(result)
    return result


@activity.defn
async def send_notification_activity(message: str) -> str:
    """
    Simple activity that simulates sending a notification.
    """
    logger.info(f"Sending notification: {message}")
    
    # Simulate notification sending
    await asyncio.sleep(1)
    
    result = f"Notification sent: {message}"
    logger.info(result)
    return result


@dataclass
class ScrapeResult:
    url: str
    url_hash: str
    status_code: Optional[int]
    title: Optional[str]
    content_length: int
    links_found: int
    depth: int
    response_time_ms: int
    error: Optional[str]
    domain: str
    extracted_links: List[str]


@dataclass
class ScraperConfig:
    seed_urls: List[str]
    max_depth: int
    max_pages: int
    batch_size: int
    db_host: str
    db_port: int
    db_name: str
    db_user: str
    db_pass: str
    politeness_delay_ms: int = 1000


def get_db_connection(config: ScraperConfig):
    return psycopg2.connect(
        host=config.db_host,
        port=config.db_port,
        dbname=config.db_name,
        user=config.db_user,
        password=config.db_pass
    )


def get_url_hash(url: str) -> str:
    return hashlib.sha256(url.encode('utf-8')).hexdigest()


@activity.defn
def init_scraper_db(config_dict: dict) -> dict:
    config = ScraperConfig(**config_dict)
    conn = get_db_connection(config)
    
    try:
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
            
            cur.execute("""
                CREATE INDEX IF NOT EXISTS idx_url_hash ON scraped_pages(url_hash)
            """)
            
            cur.execute("""
                CREATE INDEX IF NOT EXISTS idx_timestamp ON scraped_pages(timestamp)
            """)
            
            cur.execute("""
                CREATE TABLE IF NOT EXISTS scrape_queue (
                    id SERIAL PRIMARY KEY,
                    url TEXT NOT NULL,
                    url_hash VARCHAR(64) NOT NULL,
                    depth INTEGER NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    claimed_at TIMESTAMP,
                    UNIQUE(url_hash)
                )
            """)
            
            cur.execute("""
                CREATE INDEX IF NOT EXISTS idx_queue_claimed ON scrape_queue(claimed_at)
            """)
            
            conn.commit()
            
        return {"status": "initialized", "timestamp": datetime.now().isoformat()}
    finally:
        conn.close()


@activity.defn
def enqueue_urls(config_dict: dict, urls: List[dict]) -> dict:
    config = ScraperConfig(**config_dict)
    conn = get_db_connection(config)
    
    try:
        enqueued = 0
        with conn.cursor() as cur:
            for url_info in urls:
                url = url_info["url"]
                depth = url_info["depth"]
                url_hash = get_url_hash(url)
                
                try:
                    cur.execute("""
                        INSERT INTO scrape_queue (url, url_hash, depth)
                        VALUES (%s, %s, %s)
                        ON CONFLICT (url_hash) DO NOTHING
                    """, (url, url_hash, depth))
                    
                    if cur.rowcount > 0:
                        enqueued += 1
                except Exception as e:
                    logger.error(f"Error enqueuing {url}: {e}")
            
            conn.commit()
        
        return {"enqueued": enqueued, "total_attempted": len(urls)}
    finally:
        conn.close()


@activity.defn
def fetch_url_batch(config_dict: dict, batch_size: int) -> List[dict]:
    config = ScraperConfig(**config_dict)
    conn = get_db_connection(config)
    
    try:
        with conn.cursor() as cur:
            cur.execute("""
                WITH claimed AS (
                    SELECT id, url, depth
                    FROM scrape_queue
                    WHERE claimed_at IS NULL
                    ORDER BY depth ASC, created_at ASC
                    LIMIT %s
                    FOR UPDATE SKIP LOCKED
                )
                UPDATE scrape_queue
                SET claimed_at = NOW()
                FROM claimed
                WHERE scrape_queue.id = claimed.id
                RETURNING scrape_queue.url, scrape_queue.depth
            """, (batch_size,))
            
            rows = cur.fetchall()
            conn.commit()
            
            return [{"url": row[0], "depth": row[1]} for row in rows]
    finally:
        conn.close()


@activity.defn
def scrape_url(config_dict: dict, url: str, depth: int) -> dict:
    import time
    
    config = ScraperConfig(**config_dict)
    start_time = time.time()
    
    result = ScrapeResult(
        url=url,
        url_hash=get_url_hash(url),
        status_code=None,
        title=None,
        content_length=0,
        links_found=0,
        depth=depth,
        response_time_ms=0,
        error=None,
        domain=urlparse(url).netloc,
        extracted_links=[]
    )
    
    try:
        activity.heartbeat({"url": url, "status": "fetching"})
        
        headers = {
            'User-Agent': 'Mozilla/5.0 (compatible; TemporalScraperBot/1.0)'
        }
        response = requests.get(url, headers=headers, timeout=10, allow_redirects=True)
        
        response_time = int((time.time() - start_time) * 1000)
        result.response_time_ms = response_time
        result.status_code = response.status_code
        result.content_length = len(response.content)
        
        if response.status_code == 200:
            activity.heartbeat({"url": url, "status": "parsing"})
            
            title_match = re.search(r'<title[^>]*>([^<]+)</title>', response.text, re.IGNORECASE)
            result.title = title_match.group(1).strip() if title_match else None
            
            href_pattern = re.compile(r'href=[\'"]?([^\'" >]+)', re.IGNORECASE)
            links = []
            
            for match in href_pattern.finditer(response.text):
                link = match.group(1)
                absolute_link = urljoin(response.url, link)
                absolute_link, _ = urldefrag(absolute_link)
                
                if absolute_link.startswith(('http://', 'https://')):
                    links.append(absolute_link)
            
            result.extracted_links = links[:50]
            result.links_found = len(result.extracted_links)
    
    except requests.RequestException as e:
        result.error = str(e)
        result.response_time_ms = int((time.time() - start_time) * 1000)
        logger.error(f"Error scraping {url}: {e}")
    
    return asdict(result)


@activity.defn
def save_scrape_results(config_dict: dict, results: List[dict]) -> dict:
    config = ScraperConfig(**config_dict)
    conn = get_db_connection(config)
    
    try:
        saved = 0
        new_urls_to_enqueue = []
        
        with conn.cursor() as cur:
            for result_dict in results:
                result = ScrapeResult(**result_dict)
                
                try:
                    cur.execute("""
                        INSERT INTO scraped_pages 
                        (url, url_hash, status_code, title, content_length, links_found, 
                         depth, response_time_ms, error, domain)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                        ON CONFLICT (url_hash) DO NOTHING
                    """, (
                        result.url,
                        result.url_hash,
                        result.status_code,
                        result.title,
                        result.content_length,
                        result.links_found,
                        result.depth,
                        result.response_time_ms,
                        result.error,
                        result.domain
                    ))
                    
                    if cur.rowcount > 0:
                        saved += 1
                    
                    cur.execute("""
                        DELETE FROM scrape_queue WHERE url_hash = %s
                    """, (result.url_hash,))
                    
                    if result.extracted_links and result.depth < config.max_depth:
                        for link in result.extracted_links:
                            new_urls_to_enqueue.append({
                                "url": link,
                                "depth": result.depth + 1
                            })
                
                except Exception as e:
                    logger.error(f"Error saving result for {result.url}: {e}")
            
            conn.commit()
        
        return {
            "saved": saved,
            "new_urls_discovered": len(new_urls_to_enqueue),
            "new_urls": new_urls_to_enqueue
        }
    finally:
        conn.close()


@activity.defn
def get_scraper_stats(config_dict: dict) -> dict:
    config = ScraperConfig(**config_dict)
    conn = get_db_connection(config)
    
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM scraped_pages")
            total_scraped = cur.fetchone()[0]
            
            cur.execute("SELECT COUNT(*) FROM scrape_queue WHERE claimed_at IS NULL")
            queue_size = cur.fetchone()[0]
            
            cur.execute("""
                SELECT domain, COUNT(*) as count 
                FROM scraped_pages 
                GROUP BY domain 
                ORDER BY count DESC 
                LIMIT 5
            """)
            top_domains = [{"domain": row[0], "count": row[1]} for row in cur.fetchall()]
            
            cur.execute("SELECT AVG(response_time_ms) FROM scraped_pages WHERE response_time_ms > 0")
            avg_response_time = cur.fetchone()[0] or 0
        
        return {
            "total_scraped": total_scraped,
            "queue_size": queue_size,
            "top_domains": top_domains,
            "avg_response_time_ms": round(float(avg_response_time), 2)
        }
    finally:
        conn.close()


@workflow.defn
class WebScraperWorkflow:
    
    @workflow.run
    async def run(self, config_dict: dict) -> dict:
        config = ScraperConfig(**config_dict)
        
        seed_urls = [{"url": url, "depth": 0} for url in config.seed_urls]
        await workflow.execute_activity(
            enqueue_urls,
            args=[config_dict, seed_urls],
            start_to_close_timeout=timedelta(seconds=30)
        )
        
        total_scraped = 0
        batch_num = 0
        
        while total_scraped < config.max_pages:
            batch_num += 1
            workflow.logger.info(f"Processing batch {batch_num}")
            
            url_batch = await workflow.execute_activity(
                fetch_url_batch,
                args=[config_dict, config.batch_size],
                start_to_close_timeout=timedelta(seconds=30)
            )
            
            if not url_batch:
                workflow.logger.info("No more URLs to scrape")
                break
            
            scrape_tasks = []
            for url_info in url_batch:
                task = workflow.execute_activity(
                    scrape_url,
                    args=[config_dict, url_info["url"], url_info["depth"]],
                    start_to_close_timeout=timedelta(seconds=30),
                    heartbeat_timeout=timedelta(seconds=15),
                    retry_policy={
                        "initial_interval": timedelta(seconds=2),
                        "maximum_interval": timedelta(seconds=30),
                        "maximum_attempts": 3,
                    }
                )
                scrape_tasks.append(task)
                
                await asyncio.sleep(config.politeness_delay_ms / 1000.0)
            
            scrape_results = await asyncio.gather(*scrape_tasks, return_exceptions=True)
            
            valid_results = [r for r in scrape_results if not isinstance(r, Exception)]
            
            if valid_results:
                save_result = await workflow.execute_activity(
                    save_scrape_results,
                    args=[config_dict, valid_results],
                    start_to_close_timeout=timedelta(seconds=60)
                )
                
                if save_result["new_urls"]:
                    await workflow.execute_activity(
                        enqueue_urls,
                        args=[config_dict, save_result["new_urls"]],
                        start_to_close_timeout=timedelta(seconds=30)
                    )
                
                total_scraped += len(valid_results)
            
            if batch_num % 5 == 0:
                stats = await workflow.execute_activity(
                    get_scraper_stats,
                    config_dict,
                    start_to_close_timeout=timedelta(seconds=10)
                )
                workflow.logger.info(f"Stats: {stats}")
        
        final_stats = await workflow.execute_activity(
            get_scraper_stats,
            config_dict,
            start_to_close_timeout=timedelta(seconds=10)
        )
        
        return {
            "status": "completed",
            "batches_processed": batch_num,
            "total_scraped": total_scraped,
            "final_stats": final_stats
        }


@workflow.defn
class OrderProcessingWorkflow:
    """
    Simple workflow that processes orders and sends notifications.
    """

    @workflow.run
    async def run(self, order_id: str) -> str:
        logger.info(f"Starting order processing workflow for order: {order_id}")

        # Process the order
        order_result = await workflow.execute_activity(
            process_order_activity,
            order_id,
            start_to_close_timeout=timedelta(seconds=30),
        )

        # Send notification
        notification_result = await workflow.execute_activity(
            send_notification_activity,
            f"Order {order_id} has been processed",
            start_to_close_timeout=timedelta(seconds=30),
        )

        final_result = f"Workflow completed: {order_result}, {notification_result}"
        logger.info(final_result)
        return final_result


async def create_worker():
    """
    Create and configure the Temporal worker.
    """
    # Get and validate configuration
    host, namespace, task_queue, api_key = get_temporal_config()
    
    logger.info(f"Connecting to Temporal at {host}")
    logger.info(f"Using namespace: {namespace}")
    logger.info(f"Using task queue: {task_queue}")

    # Create client with API key for Temporal Cloud
    client = await Client.connect(
        host, 
        namespace=namespace,
        api_key=api_key,
        tls=True  # Enable TLS for Temporal Cloud
    )

    activity_threads = int(os.getenv("ACTIVITY_THREADS", "8"))
    worker = Worker(
        client,
        task_queue=task_queue,
        workflows=[OrderProcessingWorkflow, WebScraperWorkflow],
        activities=[
            process_order_activity, 
            send_notification_activity,
            init_scraper_db,
            enqueue_urls,
            fetch_url_batch,
            scrape_url,
            save_scrape_results,
            get_scraper_stats
        ],
        activity_executor=ThreadPoolExecutor(max_workers=activity_threads),
    )

    logger.info("Temporal worker created successfully")
    return worker


def initialize_scraper_db():
    """Initialize scraper database tables on worker startup."""
    db_host = os.getenv("DB_HOST")
    db_port = os.getenv("DB_PORT", "5432")
    db_name = os.getenv("DB_NAME")
    db_user = os.getenv("DB_USER")
    db_pass = os.getenv("DB_PASS")
    
    if not all([db_host, db_name, db_user, db_pass]):
        logger.warning("Scraper DB env vars not set, skipping DB initialization")
        return
    
    try:
        conn = psycopg2.connect(
            host=db_host,
            port=db_port,
            dbname=db_name,
            user=db_user,
            password=db_pass
        )
        
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
            
            cur.execute("""
                CREATE INDEX IF NOT EXISTS idx_url_hash ON scraped_pages(url_hash)
            """)
            
            cur.execute("""
                CREATE INDEX IF NOT EXISTS idx_timestamp ON scraped_pages(timestamp)
            """)
            
            cur.execute("""
                CREATE TABLE IF NOT EXISTS scrape_queue (
                    id SERIAL PRIMARY KEY,
                    url TEXT NOT NULL,
                    url_hash VARCHAR(64) NOT NULL,
                    depth INTEGER NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    claimed_at TIMESTAMP,
                    UNIQUE(url_hash)
                )
            """)
            
            cur.execute("""
                CREATE INDEX IF NOT EXISTS idx_queue_claimed ON scrape_queue(claimed_at)
            """)
            
            conn.commit()
        
        conn.close()
        logger.info("Scraper database initialized successfully")
    except Exception as e:
        logger.error(f"Failed to initialize scraper database: {e}")


async def main():
    """
    Main function to start the Temporal worker.
    """
    logger.info("Starting Temporal worker...")
    
    try:
        initialize_scraper_db()
        
        worker = await create_worker()
        _, _, task_queue, _ = get_temporal_config()
        logger.info(f"Worker started and listening on task queue: {task_queue}")
        
        await worker.run()
        
    except KeyboardInterrupt:
        logger.info("Worker stopped by user")
    except Exception as e:
        logger.error(f"Worker failed: {e}")
        raise


if __name__ == "__main__":
    asyncio.run(main())