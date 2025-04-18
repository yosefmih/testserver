#!/usr/bin/env python3
import os
import sys
import time
import psutil

def print_memory_usage():
    """Print current memory usage information."""
    process = psutil.Process(os.getpid())
    memory_info = process.memory_info()
    print(f"Current memory usage: {memory_info.rss / (1024 * 1024):.2f} MB")
    
def allocate_memory(chunk_size_mb=100, delay=0.1):
    """
    Allocate memory in chunks until OOM occurs.
    
    Args:
        chunk_size_mb: Size of each memory chunk in MiB
        delay: Delay between allocations in seconds
    """
    chunk_size = chunk_size_mb * 1024 * 1024  # Convert MB to bytes
    memory_blocks = []
    
    print(f"Starting memory allocation in {chunk_size_mb}MB chunks...")
    print(f"PID: {os.getpid()}")
    
    try:
        while True:
            # Allocate a block of memory
            memory_blocks.append(bytearray(chunk_size))
            
            # Print current memory usage
            print_memory_usage()
            
            # Small delay to allow for monitoring
            time.sleep(delay)
            
    except MemoryError:
        print("Memory allocation failed - Out of Memory")
    except KeyboardInterrupt:
        print("Stopped by user")
    except Exception as e:
        print(f"Error: {e}")
    finally:
        print("Final memory state:")
        print_memory_usage()

if __name__ == "__main__":
    chunk_size = 100  # Default chunk size in MB
    
    # Allow custom chunk size via command line
    if len(sys.argv) > 1:
        try:
            chunk_size = int(sys.argv[1])
        except ValueError:
            print(f"Invalid chunk size: {sys.argv[1]}. Using default of {chunk_size}MB.")
    
    print(f"OOM Test - will allocate memory in {chunk_size}MB chunks until failure")
    allocate_memory(chunk_size_mb=chunk_size)
