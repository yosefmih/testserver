#!/usr/bin/env python3
import argparse
import redis
import os
import sys
import time
import json
import base64
import numpy as np
import scipy.signal
import scipy.io.wavfile
from datetime import datetime
import logging
import io
from dotenv import load_dotenv

load_dotenv(override=True)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

class AudioProcessor:
    def __init__(self, sample_rate=44100):
        self.sample_rate = sample_rate
        
    def apply_low_pass_filter(self, audio_data, cutoff_freq=1000):
        """Apply a low-pass Butterworth filter"""
        nyquist = self.sample_rate / 2
        normalized_cutoff = cutoff_freq / nyquist
        b, a = scipy.signal.butter(4, normalized_cutoff, btype='low')
        filtered = scipy.signal.filtfilt(b, a, audio_data)
        return filtered
    
    def apply_high_pass_filter(self, audio_data, cutoff_freq=500):
        """Apply a high-pass Butterworth filter"""
        nyquist = self.sample_rate / 2
        normalized_cutoff = cutoff_freq / nyquist
        b, a = scipy.signal.butter(4, normalized_cutoff, btype='high')
        filtered = scipy.signal.filtfilt(b, a, audio_data)
        return filtered
    
    def apply_reverb(self, audio_data, room_size=0.5, damping=0.5):
        """Apply a simple reverb effect using convolution"""
        # Create a simple impulse response for reverb
        reverb_time = int(room_size * self.sample_rate)
        impulse = np.random.randn(reverb_time) * damping
        impulse = impulse * np.exp(-3 * np.linspace(0, 1, reverb_time))
        
        # Convolve with the audio signal
        reverb_audio = scipy.signal.convolve(audio_data, impulse, mode='same')
        
        # Mix dry and wet signals
        return 0.7 * audio_data + 0.3 * reverb_audio
    
    def apply_echo(self, audio_data, delay_ms=500, decay=0.5):
        """Apply echo effect"""
        delay_samples = int(delay_ms * self.sample_rate / 1000)
        echo_audio = np.zeros_like(audio_data)
        
        # Add delayed copies
        for i in range(3):  # 3 echoes
            delay = delay_samples * (i + 1)
            amplitude = decay ** (i + 1)
            if delay < len(audio_data):
                echo_audio[delay:] += audio_data[:-delay] * amplitude
        
        return audio_data + echo_audio * 0.5
    
    def apply_pitch_shift(self, audio_data, semitones=2):
        """Shift pitch by the specified number of semitones"""
        # Simple pitch shift using resampling
        shift_factor = 2 ** (semitones / 12)
        shifted_length = int(len(audio_data) / shift_factor)
        
        # Resample
        shifted = scipy.signal.resample(audio_data, shifted_length)
        
        # Stretch back to original length
        return scipy.signal.resample(shifted, len(audio_data))
    
    def apply_distortion(self, audio_data, gain=2.0, threshold=0.7):
        """Apply distortion/clipping effect"""
        # Amplify signal
        distorted = audio_data * gain
        
        # Soft clipping
        distorted = np.tanh(distorted * threshold) / threshold
        
        return distorted
    
    def normalize_audio(self, audio_data):
        """Normalize audio to prevent clipping"""
        max_val = np.max(np.abs(audio_data))
        if max_val > 0:
            return audio_data / max_val * 0.95
        return audio_data

class AudioWorker:
    def __init__(self, redis_client, duration_minutes=5):
        self.redis_client = redis_client
        self.duration_seconds = duration_minutes * 60
        self.processor = AudioProcessor()
        self.jobs_processed = 0
        self.start_time = time.time()
        
    def process_job(self, job_id):
        """Process a single audio job"""
        logger.info(f"Processing job {job_id}")
        
        try:
            # Update status to processing
            self.redis_client.set(f"audio:job:{job_id}:status", "processing")
            
            # Get input audio data
            audio_data_b64 = self.redis_client.get(f"audio:job:{job_id}:input")
            if not audio_data_b64:
                raise Exception("Input audio data not found")
            
            # Decode audio data
            audio_bytes = base64.b64decode(audio_data_b64)
            audio_data = np.frombuffer(audio_bytes, dtype=np.int16).astype(np.float32) / 32768.0
            
            # Get processing parameters
            metadata_str = self.redis_client.get(f"audio:job:{job_id}:metadata")
            metadata = json.loads(metadata_str) if metadata_str else {}
            effects = metadata.get('effects', ['reverb', 'low_pass'])
            
            logger.info(f"Applying effects: {effects}")
            
            # Apply effects based on configuration
            processed = audio_data.copy()
            
            for effect in effects:
                if effect == 'low_pass':
                    processed = self.processor.apply_low_pass_filter(processed, cutoff_freq=2000)
                elif effect == 'high_pass':
                    processed = self.processor.apply_high_pass_filter(processed, cutoff_freq=300)
                elif effect == 'reverb':
                    processed = self.processor.apply_reverb(processed, room_size=0.7)
                elif effect == 'echo':
                    processed = self.processor.apply_echo(processed, delay_ms=300)
                elif effect == 'pitch_shift':
                    processed = self.processor.apply_pitch_shift(processed, semitones=3)
                elif effect == 'distortion':
                    processed = self.processor.apply_distortion(processed, gain=2.5)
            
            # Normalize to prevent clipping
            processed = self.processor.normalize_audio(processed)
            
            # Convert back to 16-bit PCM
            processed_int16 = (processed * 32767).astype(np.int16)
            
            # Create WAV file in memory
            wav_buffer = io.BytesIO()
            scipy.io.wavfile.write(wav_buffer, self.processor.sample_rate, processed_int16)
            wav_buffer.seek(0)
            
            # Encode result
            result_b64 = base64.b64encode(wav_buffer.read()).decode('utf-8')
            
            # Store result
            pipe = self.redis_client.pipeline()
            pipe.set(f"audio:job:{job_id}:result", result_b64)
            pipe.set(f"audio:job:{job_id}:status", "completed")
            pipe.expire(f"audio:job:{job_id}:result", 3600)  # 1 hour TTL
            
            # Update metadata with processing info
            metadata['processed_at'] = datetime.now().isoformat()
            
            calculation_start_time = time.time()  # Current time as float (seconds since epoch)
            created_at_value = metadata.get('created_at') # This is an ISO string

            if isinstance(created_at_value, str):
                try:
                    # Convert ISO string to datetime object
                    created_at_dt = datetime.fromisoformat(created_at_value)
                    # Convert datetime object to Unix timestamp (float)
                    created_at_timestamp = created_at_dt.timestamp()
                except ValueError as ve:
                    logger.error(f"Error parsing 'created_at' string '{created_at_value}': {ve}. Using current time as fallback for processing duration.")
                    created_at_timestamp = calculation_start_time  # Fallback to avoid crash, makes duration 0 or negative if clock skewed
            elif isinstance(created_at_value, (int, float)): # Should not happen with current server code
                logger.warning(f"'created_at' in metadata is a number, not an ISO string: {created_at_value}. Using it directly.")
                created_at_timestamp = float(created_at_value)
            else: # Default if 'created_at' is missing or is of an unexpected type
                logger.warning(f"'created_at' not found in metadata or is of an unexpected type. Using current time as fallback for processing duration.")
                created_at_timestamp = calculation_start_time # Fallback

            processing_duration_seconds = calculation_start_time - created_at_timestamp
            metadata['processing_time_ms'] = int(processing_duration_seconds * 1000)
            
            metadata['effects_applied'] = effects
            pipe.set(f"audio:job:{job_id}:metadata", json.dumps(metadata))
            
            pipe.execute()
            
            logger.info(f"Job {job_id} completed successfully")
            self.jobs_processed += 1
            
        except Exception as e:
            logger.error(f"Error processing job {job_id}: {e}")
            # Mark job as failed
            pipe = self.redis_client.pipeline()
            pipe.set(f"audio:job:{job_id}:status", "failed")
            pipe.set(f"audio:job:{job_id}:error", str(e))
            pipe.expire(f"audio:job:{job_id}:error", 3600)
            pipe.execute()
    
    def run(self):
        """Main worker loop"""
        logger.info(f"Starting audio worker, will run for {self.duration_seconds} seconds")
        
        while time.time() - self.start_time < self.duration_seconds:
            try:
                # Block for up to 5 seconds waiting for a job
                result = self.redis_client.brpop("audio:queue", timeout=5)
                
                if result:
                    _, job_id = result
                    self.process_job(job_id)
                else:
                    logger.debug("No jobs in queue, waiting...")
                    
                # Log stats every 30 seconds
                if int(time.time() - self.start_time) % 30 == 0:
                    self.log_stats()
                    
            except Exception as e:
                logger.error(f"Error in worker loop: {e}")
                time.sleep(1)
        
        # Final stats
        self.log_stats()
        logger.info(f"Worker shutting down. Processed {self.jobs_processed} jobs.")
    
    def log_stats(self):
        """Log worker statistics"""
        elapsed = time.time() - self.start_time
        jobs_per_minute = (self.jobs_processed / elapsed) * 60 if elapsed > 0 else 0
        
        stats = {
            "elapsed_seconds": round(elapsed, 2),
            "jobs_processed": self.jobs_processed,
            "jobs_per_minute": round(jobs_per_minute, 2),
            "queue_length": self.redis_client.llen("audio:queue")
        }
        
        logger.info(f"Worker stats: {json.dumps(stats)}")

def main():
    parser = argparse.ArgumentParser(description='Audio processing worker for Kubernetes')
    parser.add_argument('--duration', type=int, default=5,
                      help='Duration in minutes (default: 5)')
    
    args = parser.parse_args()
    
    # Connect to Redis
    redis_url = os.environ.get('REDIS_URL')
    if redis_url:
        redis_client = redis.from_url(redis_url, decode_responses=True)
        logger.info("Connected to Redis via REDIS_URL")
    else:
        # Try individual parameters
        redis_host = os.environ.get('REDIS_HOST')
        redis_port = int(os.environ.get('REDIS_PORT', 6379))
        redis_pass = os.environ.get('REDIS_PASS')
        
        if not redis_host:
            logger.error("Redis connection not configured. Set REDIS_URL or REDIS_HOST")
            sys.exit(1)
        
        redis_client = redis.Redis(
            host=redis_host,
            port=redis_port,
            password=redis_pass,
            decode_responses=True
        )
        logger.info(f"Connected to Redis at {redis_host}:{redis_port}")
    
    try:
        # Test connection
        redis_client.ping()
    except Exception as e:
        logger.error(f"Failed to connect to Redis: {e}")
        sys.exit(1)
    
    # Create and run worker
    worker = AudioWorker(redis_client, duration_minutes=args.duration)
    
    try:
        worker.run()
        sys.exit(0)
    except KeyboardInterrupt:
        logger.info("Worker interrupted by user")
        sys.exit(1)
    except Exception as e:
        logger.error(f"Worker failed: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main() 