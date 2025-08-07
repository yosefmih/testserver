#!/usr/bin/env python3
"""
Simple script to queue a WAV file to the C audio worker
"""

import redis
import json
import base64
import time
import wave
import sys

def read_wav_file(wav_path):
    """Read WAV file and convert to PCM data like server.py does"""
    print(f"🎵 Loading WAV file: {wav_path}")
    
    try:
        with wave.open(wav_path, 'rb') as wav_file:
            # Get WAV parameters
            frames = wav_file.getnframes()
            sample_width = wav_file.getsampwidth()
            framerate = wav_file.getframerate()
            channels = wav_file.getnchannels()
            
            print(f"   Frames: {frames}, Sample width: {sample_width}, Rate: {framerate}, Channels: {channels}")
            
            # Read raw audio data
            audio_data = wav_file.readframes(frames)
            
            print(f"✅ Read {len(audio_data)} bytes from WAV file")
            return audio_data
            
    except Exception as e:
        print(f"❌ Error reading WAV file: {e}")
        return None

def queue_job(wav_path):
    """Queue the WAV file for processing"""
    
    # Connect to Redis
    try:
        redis_client = redis.Redis(host='localhost', port=6379, decode_responses=True)
        redis_client.ping()
        print("✅ Connected to Redis")
    except redis.ConnectionError as e:
        print(f"❌ Could not connect to Redis: {e}")
        return False
    
    # Read the WAV file
    pcm_data = read_wav_file(wav_path)
    if not pcm_data:
        return False
    
    # Create job
    job_id = f"wav-test-{int(time.time())}"
    audio_b64 = base64.b64encode(pcm_data).decode('utf-8')
    
    metadata = {
        'created_at': time.strftime('%Y-%m-%dT%H:%M:%S'),
        'hostname': 'test-client',
        'effects': ['reverb', 'low_pass']
    }
    
    print(f"📦 Creating job: {job_id}")
    print(f"   Audio size: {len(pcm_data)} bytes → {len(audio_b64)} chars base64")
    
    # Store job in Redis (same format as server.py)
    pipe = redis_client.pipeline()
    pipe.set(f"audio:job:{job_id}:input", audio_b64, ex=3600)
    pipe.set(f"audio:job:{job_id}:status", "queued", ex=3600)
    pipe.set(f"audio:job:{job_id}:metadata", json.dumps(metadata), ex=3600)
    pipe.lpush("audio:queue", job_id)
    pipe.execute()
    
    print(f"✅ Job queued: {job_id}")
    print(f"📊 Queue length: {redis_client.llen('audio:queue')}")
    
    # Monitor job briefly
    print("👀 Monitoring job status...")
    for _ in range(30):  # Wait up to 30 seconds
        status = redis_client.get(f"audio:job:{job_id}:status")
        print(f"   Status: {status}")
        
        if status == "completed":
            # Get result info
            result_size = redis_client.strlen(f"audio:job:{job_id}:result")
            metadata_str = redis_client.get(f"audio:job:{job_id}:metadata")
            
            if metadata_str:
                metadata = json.loads(metadata_str)
                processing_time = metadata.get('processing_time_ms', 'unknown')
                print(f"✅ Job completed in {processing_time}ms")
                print(f"📁 Result size: {result_size} bytes (base64)")
                
                # Save result to file
                if result_size > 0:
                    result_data = redis_client.get(f"audio:job:{job_id}:result")
                    if result_data:
                        audio_bytes = base64.b64decode(result_data)
                        output_file = f"output_{job_id}.wav"
                        with open(output_file, 'wb') as f:
                            f.write(audio_bytes)
                        print(f"💾 Processed audio saved to: {output_file}")
            
            return True
            
        elif status == "failed":
            error = redis_client.get(f"audio:job:{job_id}:error") or "Unknown error"
            print(f"❌ Job failed: {error}")
            return False
        
        time.sleep(1)
    
    print("⏰ Job monitoring timeout")
    return False

def main():
    wav_path = "/Users/yosefmihretie/projects/testserver/tmp/test_audio.wav"
    
    print("🎧 WAV File Audio Processing Test")
    print("=================================")
    print(f"Queueing: {wav_path}")
    print()
    
    success = queue_job(wav_path)
    
    if success:
        print("🎉 Test completed successfully!")
    else:
        print("❌ Test failed")
    
    return 0 if success else 1

if __name__ == "__main__":
    sys.exit(main())