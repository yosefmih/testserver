#!/usr/bin/env python3
import argparse
import hashlib
import time
import random
import string
import sys
import signal
from datetime import datetime
import json
import logging
import psycopg2
from psycopg2.extras import RealDictCursor
import os

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

class MiningSimulator:
    def __init__(self, duration_minutes=5, initial_difficulty=4, failure_probability=0.3, db_config=None):
        self.duration_seconds = duration_minutes * 60
        self.difficulty = initial_difficulty  # Number of leading zeros required
        self.blocks_found = 0
        self.total_hashes = 0
        self.start_time = time.time()
        self.last_block_time = self.start_time
        self.block_times = []
        self.target_block_time = 30  # seconds
        self.failure_probability = failure_probability
        self.should_fail = random.random() < failure_probability
        self.db_config = db_config
        self.db_conn = None
        self.session_id = None
        
        # Setup database connection and schema
        if self.db_config:
            self.setup_database()
            self.load_state()
        
        # Setup signal handlers for graceful shutdown
        signal.signal(signal.SIGINT, self.signal_handler)
        signal.signal(signal.SIGTERM, self.signal_handler)
        
        if self.should_fail:
            # Determine when to fail (random time within duration)
            self.failure_time = self.start_time + random.uniform(30, self.duration_seconds - 30)
            logger.warning(f"This run is scheduled to fail (probability: {failure_probability*100}%)")
    
    def setup_database(self):
        """Setup database connection and create tables if needed"""
        max_retries = 15
        retry_delay = 2
        
        for attempt in range(max_retries):
            try:
                logger.info(f"Attempting database connection (attempt {attempt + 1}/{max_retries})")
                logger.info(f"Connecting to: {self.db_config['host']}:{self.db_config['port']}")
                
                self.db_conn = psycopg2.connect(**self.db_config)
                self.db_conn.autocommit = True
                
                with self.db_conn.cursor() as cursor:
                    # Test the connection
                    cursor.execute("SELECT 1")
                    
                    # Create mining_sessions table
                    cursor.execute("""
                        CREATE TABLE IF NOT EXISTS mining_sessions (
                            session_id SERIAL PRIMARY KEY,
                            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                            difficulty INTEGER NOT NULL,
                            blocks_found INTEGER DEFAULT 0,
                            total_hashes BIGINT DEFAULT 0,
                            block_times JSONB DEFAULT '[]'::jsonb,
                            last_block_time TIMESTAMP,
                            target_block_time INTEGER DEFAULT 30,
                            is_active BOOLEAN DEFAULT TRUE
                        )
                    """)
                    
                    logger.info("Database connection established and tables created")
                    return
                    
            except psycopg2.Error as e:
                logger.warning(f"Database connection attempt {attempt + 1} failed: {e}")
                if attempt < max_retries - 1:
                    logger.info(f"Retrying in {retry_delay} seconds...")
                    time.sleep(retry_delay)
                else:
                    logger.error(f"All database connection attempts failed after {max_retries} retries")
                    self.db_conn = None
    
    def load_state(self):
        """Load existing state from database or create new session"""
        if not self.db_conn:
            return
            
        try:
            with self.db_conn.cursor(cursor_factory=RealDictCursor) as cursor:
                # Look for active session
                cursor.execute("""
                    SELECT * FROM mining_sessions 
                    WHERE is_active = TRUE 
                    ORDER BY updated_at DESC 
                    LIMIT 1
                """)
                
                session = cursor.fetchone()
                
                if session:
                    # Continue existing session
                    self.session_id = session['session_id']
                    self.difficulty = session['difficulty']
                    self.blocks_found = session['blocks_found']
                    self.total_hashes = session['total_hashes']
                    self.block_times = session['block_times'] or []
                    self.target_block_time = session['target_block_time']
                    
                    if session['last_block_time']:
                        # Use current time as reference for next block timing
                        self.last_block_time = time.time()
                    
                    logger.info(f"Resuming session {self.session_id}")
                    logger.info(f"Loaded state: difficulty={self.difficulty}, blocks={self.blocks_found}, hashes={self.total_hashes}")
                    
                else:
                    # Create new session
                    cursor.execute("""
                        INSERT INTO mining_sessions (difficulty, target_block_time)
                        VALUES (%s, %s)
                        RETURNING session_id
                    """, (self.difficulty, self.target_block_time))
                    
                    self.session_id = cursor.fetchone()['session_id']
                    logger.info(f"Created new session {self.session_id}")
                    
        except psycopg2.Error as e:
            logger.error(f"Failed to load state: {e}")
    
    def save_state(self):
        """Save current state to database"""
        if not self.db_conn or not self.session_id:
            return
            
        try:
            with self.db_conn.cursor() as cursor:
                cursor.execute("""
                    UPDATE mining_sessions SET
                        updated_at = CURRENT_TIMESTAMP,
                        difficulty = %s,
                        blocks_found = %s,
                        total_hashes = %s,
                        block_times = %s,
                        last_block_time = %s,
                        target_block_time = %s
                    WHERE session_id = %s
                """, (
                    self.difficulty,
                    self.blocks_found,
                    self.total_hashes,
                    json.dumps(self.block_times),
                    datetime.fromtimestamp(self.last_block_time) if self.last_block_time else None,
                    self.target_block_time,
                    self.session_id
                ))
                
                logger.info(f"State saved to database (session {self.session_id})")
                
        except psycopg2.Error as e:
            logger.error(f"Failed to save state: {e}")
    
    def close_session(self):
        """Mark session as inactive and close database connection"""
        if not self.db_conn or not self.session_id:
            return
            
        try:
            with self.db_conn.cursor() as cursor:
                cursor.execute("""
                    UPDATE mining_sessions SET
                        is_active = FALSE,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE session_id = %s
                """, (self.session_id,))
                
                logger.info(f"Session {self.session_id} marked as inactive")
                
        except psycopg2.Error as e:
            logger.error(f"Failed to close session: {e}")
        finally:
            if self.db_conn:
                self.db_conn.close()
    
    def signal_handler(self, signum, frame):
        """Handle shutdown signals gracefully"""
        logger.info(f"Received signal {signum}, saving state and shutting down...")
        self.save_state()
        self.close_session()
        sys.exit(0)
        
    def generate_random_data(self, length=32):
        """Generate random string for mining"""
        return ''.join(random.choices(string.ascii_letters + string.digits, k=length))
    
    def compute_hash(self, data, nonce):
        """Compute SHA-256 hash of data + nonce"""
        content = f"{data}{nonce}".encode('utf-8')
        return hashlib.sha256(content).hexdigest()
    
    def is_valid_hash(self, hash_value):
        """Check if hash meets difficulty requirement"""
        return hash_value.startswith('0' * self.difficulty)
    
    def adjust_difficulty(self):
        """Adjust difficulty based on block time"""
        if len(self.block_times) >= 3:
            avg_block_time = sum(self.block_times[-3:]) / 3
            
            if avg_block_time < self.target_block_time * 0.5:
                # Too fast, increase difficulty
                self.difficulty += 1
                logger.info(f"Difficulty increased to {self.difficulty}")
            elif avg_block_time > self.target_block_time * 2:
                # Too slow, decrease difficulty
                self.difficulty = max(1, self.difficulty - 1)
                logger.info(f"Difficulty decreased to {self.difficulty}")
    
    def mine_block(self, block_data):
        """Mine a single block"""
        nonce = 0
        hash_count = 0
        
        while True:
            # Check if we should simulate a failure
            if self.should_fail and time.time() >= self.failure_time:
                error_types = [
                    "Mining hardware failure detected",
                    "Memory corruption in hash calculation",
                    "Invalid block data structure",
                    "Consensus algorithm violation",
                    "Network connectivity lost"
                ]
                error_msg = random.choice(error_types)
                raise Exception(error_msg)
            
            hash_value = self.compute_hash(block_data, nonce)
            hash_count += 1
            
            if self.is_valid_hash(hash_value):
                return nonce, hash_value, hash_count
            
            nonce += 1
            
            # Check if we should stop
            if time.time() - self.start_time > self.duration_seconds:
                return None, None, hash_count
    
    def log_stats(self):
        """Log current mining statistics"""
        elapsed = time.time() - self.start_time
        hash_rate = self.total_hashes / elapsed if elapsed > 0 else 0
        
        stats = {
            "timestamp": datetime.now().isoformat(),
            "session_id": self.session_id,
            "elapsed_seconds": round(elapsed, 2),
            "blocks_found": self.blocks_found,
            "total_hashes": self.total_hashes,
            "hash_rate": round(hash_rate, 2),
            "current_difficulty": self.difficulty,
            "avg_block_time": round(sum(self.block_times[-5:]) / len(self.block_times[-5:]), 2) if self.block_times else 0
        }
        
        logger.info(f"[STATS] {json.dumps(stats)}")
        
        # Save state periodically
        if self.db_conn:
            self.save_state()
    
    def run(self):
        """Main mining loop"""
        logger.info("Starting mining simulator")
        logger.info(f"Duration: {self.duration_seconds}s, Initial difficulty: {self.difficulty}")
        logger.info(f"Target block time: {self.target_block_time}s")
        logger.info(f"Failure probability: {self.failure_probability*100}%")
        
        if self.session_id:
            logger.info(f"Session ID: {self.session_id}")
        
        last_stats_time = time.time()
        
        while time.time() - self.start_time < self.duration_seconds:
            # Generate new block data
            block_data = {
                "block_number": self.blocks_found + 1,
                "timestamp": time.time(),
                "data": self.generate_random_data(),
                "previous_hash": "0" * 64 if self.blocks_found == 0 else self.compute_hash(str(self.blocks_found), 0)
            }
            
            # Mine the block
            logger.info(f"Mining block #{self.blocks_found + 1}...")
            nonce, hash_value, hash_count = self.mine_block(json.dumps(block_data))
            
            self.total_hashes += hash_count
            
            if nonce is not None:
                # Block found
                block_time = time.time() - self.last_block_time
                self.block_times.append(block_time)
                self.blocks_found += 1
                self.last_block_time = time.time()
                
                logger.info(f"Block #{self.blocks_found} found!")
                logger.info(f"  Hash: {hash_value}")
                logger.info(f"  Nonce: {nonce}")
                logger.info(f"  Hashes tried: {hash_count}")
                logger.info(f"  Time: {block_time:.2f}s")
                
                # Adjust difficulty
                self.adjust_difficulty()
            
            # Log stats every 10 seconds
            if time.time() - last_stats_time >= 10:
                self.log_stats()
                last_stats_time = time.time()
            
            # Check if time is up
            if time.time() - self.start_time >= self.duration_seconds:
                break
        
        # Final stats and cleanup
        logger.info("Mining completed successfully!")
        logger.info(f"Total duration: {time.time() - self.start_time:.2f}s")
        logger.info(f"Blocks found: {self.blocks_found}")
        logger.info(f"Total hashes: {self.total_hashes}")
        logger.info(f"Average hash rate: {self.total_hashes / (time.time() - self.start_time):.2f} H/s")
        
        # Save final state
        if self.db_conn:
            self.save_state()
        
        # Exit with success
        return 0

def main():
    parser = argparse.ArgumentParser(description='Cryptocurrency mining simulator for testing')
    parser.add_argument('--duration', type=int, default=5,
                      help='Duration in minutes (default: 5)')
    parser.add_argument('--difficulty', type=int, default=4,
                      help='Initial mining difficulty - number of leading zeros (default: 4)')
    parser.add_argument('--target-block-time', type=int, default=30,
                      help='Target time between blocks in seconds (default: 30)')
    parser.add_argument('--failure-probability', type=float, default=0.3,
                      help='Probability of failure during execution (default: 0.3 = 30%%)')
    
    parser.add_argument('--no-db', action='store_true',
                      help='Run without database persistence (use env vars: DB_HOST, DB_PORT, DB_NAME, DB_USER, DB_PASSWORD)')
    
    args = parser.parse_args()
    
    if args.duration < 1 or args.duration > 60:
        logger.error("Duration must be between 1 and 60 minutes")
        sys.exit(1)
    
    if args.difficulty < 1 or args.difficulty > 8:
        logger.error("Difficulty must be between 1 and 8")
        sys.exit(1)
    
    if args.failure_probability < 0 or args.failure_probability > 1:
        logger.error("Failure probability must be between 0 and 1")
        sys.exit(1)
    
    # Setup database configuration from environment variables
    db_config = None
    if not args.no_db:
        db_host = os.getenv('DB_HOST', 'localhost')
        db_port = int(os.getenv('DB_PORT', '5432'))
        db_name = os.getenv('DB_NAME')
        db_user = os.getenv('DB_USER')
        db_password = os.getenv('DB_PASSWORD')
        
        if not db_name or not db_user:
            logger.error("Database configuration required via environment variables: DB_NAME, DB_USER")
            logger.error("Optional: DB_HOST (default: localhost), DB_PORT (default: 5432), DB_PASSWORD")
            logger.error("Use --no-db to run without persistence")
            sys.exit(1)
        
        db_config = {
            'host': db_host,
            'port': db_port,
            'database': db_name,
            'user': db_user,
            'sslmode': 'disable',  # Disable SSL for Cloud SQL Proxy
            'password': db_password or ''  # Use empty string if no password provided
        }
        
        logger.info(f"Using PostgreSQL database: {db_user}@{db_host}:{db_port}/{db_name}")
    else:
        logger.info("Running without database persistence")
    
    simulator = MiningSimulator(
        duration_minutes=args.duration,
        initial_difficulty=args.difficulty,
        failure_probability=args.failure_probability,
        db_config=db_config
    )
    simulator.target_block_time = args.target_block_time
    
    try:
        exit_code = simulator.run()
        if simulator.db_conn:
            simulator.close_session()
        sys.exit(exit_code)
    except KeyboardInterrupt:
        logger.info("Mining interrupted by user")
        if simulator.db_conn:
            simulator.save_state()
            simulator.close_session()
        sys.exit(1)
    except Exception as e:
        logger.error(f"Mining failed - {e}")
        if simulator.db_conn:
            simulator.save_state()
            simulator.close_session()
        logger.error("Exiting with error code 1")
        sys.exit(1)

if __name__ == "__main__":
    main() 