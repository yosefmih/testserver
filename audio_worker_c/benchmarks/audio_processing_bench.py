#!/usr/bin/env python3
"""
Audio Processing Benchmark
Tests the C worker's audio processing performance by timing real jobs
"""

import redis
import json
import base64
import time
import numpy as np
import subprocess
import sys
import argparse
from pathlib import Path

def generate_test_audio(duration_seconds=5, sample_rate=44100):
    """Generate synthetic test audio"""
    print(f"🎵 Generating {duration_seconds}s test audio at {sample_rate}Hz...")
    
    # Generate time array
    t = np.linspace(0, duration_seconds, int(sample_rate * duration_seconds), endpoint=False)
    
    # Create rich test signal
    signal = np.sin(2 * np.pi * 440 * t)      # A4
    signal += 0.5 * np.sin(2 * np.pi * 880 * t)   # A5
    signal += 0.3 * np.sin(2 * np.pi * 220 * t)   # A3
    signal += 0.1 * np.random.randn(len(signal))   # Some noise
    
    # Normalize and convert to 16-bit PCM
    signal = signal / np.max(np.abs(signal)) * 0.8
    pcm_data = (signal * 32767).astype(np.int16).tobytes()
    
    print(f"✅ Generated {len(pcm_data)} bytes ({len(pcm_data)/(1024*1024):.1f} MB)")
    return pcm_data

def benchmark_effect(redis_client, pcm_data, effect_list, iterations=5):
    """Benchmark a specific effect combination"""
    effect_name = "+".join(effect_list)
    print(f"🧪 Benchmarking: {effect_name}")
    
    times = []
    
    for i in range(iterations):
        # Create job
        job_id = f"bench-{effect_name.replace('+', '_')}-{int(time.time())}-{i}"
        audio_b64 = base64.b64encode(pcm_data).decode('utf-8')
        
        metadata = {
            'created_at': time.strftime('%Y-%m-%dT%H:%M:%S'),
            'effects': effect_list
        }
        
        # Submit job
        pipe = redis_client.pipeline()
        pipe.set(f"audio:job:{job_id}:input", audio_b64, ex=3600)
        pipe.set(f"audio:job:{job_id}:status", "queued", ex=3600)
        pipe.set(f"audio:job:{job_id}:metadata", json.dumps(metadata), ex=3600)
        pipe.lpush("audio:queue", job_id)
        pipe.execute()
        
        # Wait for completion and measure time
        start_time = time.time()
        
        while True:
            status = redis_client.get(f"audio:job:{job_id}:status")
            if status == "completed":
                # Get the actual processing time from metadata
                metadata_str = redis_client.get(f"audio:job:{job_id}:metadata")
                if metadata_str:
                    updated_metadata = json.loads(metadata_str)
                    processing_time_ms = updated_metadata.get('processing_time_ms', 0)
                    times.append(processing_time_ms)
                    break
                else:
                    # Fallback to wall clock time
                    wall_time = (time.time() - start_time) * 1000
                    times.append(wall_time)
                    break
            elif status == "failed":
                error = redis_client.get(f"audio:job:{job_id}:error")
                print(f"❌ Job failed: {error}")
                return None
            
            time.sleep(0.1)
    
    if not times:
        return None
    
    avg_time = sum(times) / len(times)
    min_time = min(times)
    max_time = max(times)
    
    # Calculate throughput metrics
    samples = len(pcm_data) // 2  # 16-bit samples
    sample_rate = 44100  # Known from generation
    audio_duration = samples / sample_rate
    realtime_factor = (audio_duration * 1000) / avg_time
    
    result = {
        'effect': effect_name,
        'avg_ms': avg_time,
        'min_ms': min_time, 
        'max_ms': max_time,
        'audio_duration_ms': audio_duration * 1000,
        'realtime_factor': realtime_factor,
        'samples_per_sec': samples / (avg_time / 1000),
        'iterations': iterations
    }
    
    print(f"   ✅ Avg: {avg_time:.1f}ms, Min: {min_time:.1f}ms, Max: {max_time:.1f}ms")
    print(f"      Realtime factor: {realtime_factor:.1f}x")
    print(f"      Throughput: {samples/(avg_time/1000)/1e6:.1f}M samples/sec")
    
    return result

def main():
    parser = argparse.ArgumentParser(description='Audio processing performance benchmark')
    parser.add_argument('--duration', type=int, default=5, help='Audio duration in seconds')
    parser.add_argument('--iterations', type=int, default=5, help='Iterations per test')
    parser.add_argument('--redis-host', default='localhost', help='Redis host')
    parser.add_argument('--redis-port', type=int, default=6379, help='Redis port')
    parser.add_argument('--effect', help='Test specific effect only')
    
    args = parser.parse_args()
    
    print("🎧 Audio Processing Benchmark")
    print("============================")
    print(f"Duration: {args.duration}s")
    print(f"Iterations: {args.iterations}")
    print()
    
    # Connect to Redis
    try:
        redis_client = redis.Redis(host=args.redis_host, port=args.redis_port, decode_responses=True)
        redis_client.ping()
        print(f"✅ Connected to Redis at {args.redis_host}:{args.redis_port}")
    except redis.ConnectionError:
        print("❌ Could not connect to Redis. Make sure Redis is running.")
        return 1
    
    # Generate test audio
    pcm_data = generate_test_audio(args.duration)
    print()
    
    # Define test cases
    test_cases = [
        ['low_pass'],
        ['high_pass'], 
        ['reverb'],
        ['echo'],
        ['pitch_shift'],
        ['distortion'],
        ['reverb', 'low_pass'],
        ['echo', 'distortion'],
        ['reverb', 'echo', 'low_pass'],
        ['pitch_shift', 'high_pass'],
        ['reverb', 'low_pass', 'echo', 'distortion']
    ]
    
    if args.effect:
        # Test specific effect
        effects = args.effect.split(',')
        test_cases = [effects]
    
    results = []
    
    # Run benchmarks
    for effect_list in test_cases:
        result = benchmark_effect(redis_client, pcm_data, effect_list, args.iterations)
        if result:
            results.append(result)
        print()
    
    # Summary
    print("📊 Benchmark Summary")
    print("===================")
    print(f"{'Effect':<30} {'Avg(ms)':<10} {'Realtime':<10} {'Throughput':<15}")
    print("-" * 70)
    
    for result in results:
        throughput_msamples = result['samples_per_sec'] / 1e6
        print(f"{result['effect']:<30} {result['avg_ms']:<10.1f} "
              f"{result['realtime_factor']:<10.1f}x {throughput_msamples:<15.1f}M smp/s")
    
    print()
    print("🏁 Benchmark completed!")
    
    return 0

if __name__ == "__main__":
    sys.exit(main())