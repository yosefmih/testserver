#!/usr/bin/env python3
import argparse
import hashlib
import time
import random
import string
import sys
from datetime import datetime
import json

class MiningSimulator:
    def __init__(self, duration_minutes=5, initial_difficulty=4, failure_probability=0.3):
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
        
        if self.should_fail:
            # Determine when to fail (random time within duration)
            self.failure_time = self.start_time + random.uniform(30, self.duration_seconds - 30)
            print(f"[{datetime.now()}] WARNING: This run is scheduled to fail (probability: {failure_probability*100}%)")
        
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
                print(f"[{datetime.now()}] Difficulty increased to {self.difficulty}")
            elif avg_block_time > self.target_block_time * 2:
                # Too slow, decrease difficulty
                self.difficulty = max(1, self.difficulty - 1)
                print(f"[{datetime.now()}] Difficulty decreased to {self.difficulty}")
    
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
            "elapsed_seconds": round(elapsed, 2),
            "blocks_found": self.blocks_found,
            "total_hashes": self.total_hashes,
            "hash_rate": round(hash_rate, 2),
            "current_difficulty": self.difficulty,
            "avg_block_time": round(sum(self.block_times[-5:]) / len(self.block_times[-5:]), 2) if self.block_times else 0
        }
        
        print(f"[STATS] {json.dumps(stats)}")
    
    def run(self):
        """Main mining loop"""
        print(f"[{datetime.now()}] Starting mining simulator")
        print(f"[{datetime.now()}] Duration: {self.duration_seconds}s, Initial difficulty: {self.difficulty}")
        print(f"[{datetime.now()}] Target block time: {self.target_block_time}s")
        print(f"[{datetime.now()}] Failure probability: {self.failure_probability*100}%")
        
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
            print(f"[{datetime.now()}] Mining block #{self.blocks_found + 1}...")
            nonce, hash_value, hash_count = self.mine_block(json.dumps(block_data))
            
            self.total_hashes += hash_count
            
            if nonce is not None:
                # Block found
                block_time = time.time() - self.last_block_time
                self.block_times.append(block_time)
                self.blocks_found += 1
                self.last_block_time = time.time()
                
                print(f"[{datetime.now()}] Block #{self.blocks_found} found!")
                print(f"  Hash: {hash_value}")
                print(f"  Nonce: {nonce}")
                print(f"  Hashes tried: {hash_count}")
                print(f"  Time: {block_time:.2f}s")
                
                # Adjust difficulty
                self.adjust_difficulty()
            
            # Log stats every 10 seconds
            if time.time() - last_stats_time >= 10:
                self.log_stats()
                last_stats_time = time.time()
            
            # Check if time is up
            if time.time() - self.start_time >= self.duration_seconds:
                break
        
        # Final stats
        print(f"\n[{datetime.now()}] Mining completed successfully!")
        print(f"Total duration: {time.time() - self.start_time:.2f}s")
        print(f"Blocks found: {self.blocks_found}")
        print(f"Total hashes: {self.total_hashes}")
        print(f"Average hash rate: {self.total_hashes / (time.time() - self.start_time):.2f} H/s")
        
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
    
    args = parser.parse_args()
    
    if args.duration < 1 or args.duration > 60:
        print("Duration must be between 1 and 60 minutes")
        sys.exit(1)
    
    if args.difficulty < 1 or args.difficulty > 8:
        print("Difficulty must be between 1 and 8")
        sys.exit(1)
    
    if args.failure_probability < 0 or args.failure_probability > 1:
        print("Failure probability must be between 0 and 1")
        sys.exit(1)
    
    simulator = MiningSimulator(
        duration_minutes=args.duration,
        initial_difficulty=args.difficulty,
        failure_probability=args.failure_probability
    )
    simulator.target_block_time = args.target_block_time
    
    try:
        exit_code = simulator.run()
        sys.exit(exit_code)
    except KeyboardInterrupt:
        print(f"\n[{datetime.now()}] Mining interrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n[{datetime.now()}] ERROR: Mining failed - {e}")
        print(f"[{datetime.now()}] Exiting with error code 1")
        sys.exit(1)

if __name__ == "__main__":
    main() 