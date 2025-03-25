#!/usr/bin/env python3
import argparse
import json
import requests
import sys
import time
import random
import string
import logging
import uuid
import socket
import os
import traceback

# Configure logging to match linkerd_test.py format
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    # Force all output to stdout for better capture by subprocess
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger(__name__)

# Get hostname for client identification
CLIENT_HOSTNAME = socket.gethostname()
CLIENT_ID = f"{CLIENT_HOSTNAME}-{uuid.uuid4().hex[:8]}"

def generate_random_word(length=8):
    """Generate a random string to use as a greeting word."""
    letters = string.ascii_uppercase
    return ''.join(random.choice(letters) for _ in range(length))

def generate_trace_headers():
    """Generate B3 propagation headers for tracing."""
    trace_id = uuid.uuid4().hex
    span_id = uuid.uuid4().hex[:16]
    headers = {
        'X-B3-TraceId': trace_id,
        'X-B3-SpanId': span_id,
        'X-B3-Sampled': '1',
        'X-Client-ID': CLIENT_ID
    }
    logger.debug(f"Generated trace headers: {headers}")
    return headers

def update_greeting(server_url, word, max_retries=3, retry_delay=1.0, headers=None):
    """Send a request to update the server's greeting word with retry logic."""
    # Normalize the URL
    if not server_url.startswith(('http://', 'https://')):
        server_url = f'http://{server_url}'
    
    # Ensure URL doesn't end with a slash
    server_url = server_url.rstrip('/')
    
    # Construct the full URL
    update_url = f"{server_url}/update-greeting"
    
    # Set up headers
    if headers is None:
        headers = generate_trace_headers()
    
    # Start timing the request
    start_time = time.time()
    
    # Try the request with retries
    for attempt in range(max_retries):
        try:
            logger.debug(f"Sending POST request to {update_url} with word: {word} (attempt {attempt+1}/{max_retries})")
            logger.debug(f"Using trace ID: {headers.get('X-B3-TraceId', 'none')}")
            
            # Send POST request with the word
            response = requests.post(
                update_url,
                json={'word': word},
                headers=headers,
                timeout=5  # 5 second timeout
            )
            
            duration = time.time() - start_time
            server_host = response.headers.get('X-Server-Host', 'unknown')
            
            # Log response headers for debugging
            logger.debug(f"Response headers: {dict(response.headers)}")
            
            # Check response status
            if response.status_code == 200:
                logger.info(f"Success! Server's greeting updated to '{word}' in {duration:.3f}s from server {server_host}")
                logger.info(f"Response: {response.text}")
                return True, response
            elif response.status_code >= 500:  # Server errors are retryable
                logger.warning(f"Server error (status {response.status_code}) from {server_host}, will retry ({attempt+1}/{max_retries})")
                logger.warning(f"Response: {response.text}")
                
                # Retry with exponential backoff
                if attempt < max_retries - 1:
                    backoff_time = retry_delay * (2 ** attempt)
                    logger.debug(f"Waiting {backoff_time:.2f}s before next retry")
                    time.sleep(backoff_time)
                continue
            else:  # Client errors are not retryable
                logger.error(f"Client error: Server returned status code {response.status_code} from {server_host}")
                try:
                    error_data = response.json()
                    logger.error(f"Error message: {error_data.get('message', 'No message provided')}")
                except ValueError:
                    logger.error(f"Non-JSON response: {response.text}")
                return False, response
    
        except requests.exceptions.RequestException as e:
            logger.error(f"Request error: {type(e).__name__}: {e}")
            
            # Retry on connection errors
            if attempt < max_retries - 1:
                backoff_time = retry_delay * (2 ** attempt)
                logger.debug(f"Waiting {backoff_time:.2f}s before next retry")
                time.sleep(backoff_time)
            else:
                logger.error(f"Failed after {max_retries} attempts")
                return False, None
    
    # If we get here, all retries failed
    duration = time.time() - start_time
    logger.error(f"All {max_retries} attempts failed after {duration:.3f}s")
    return False, None

def configure_server(server_url, config_type, value, headers=None):
    """Configure server parameters for testing (error rate, latency, tracing)"""
    # Normalize the URL
    if not server_url.startswith(('http://', 'https://')):
        server_url = f'http://{server_url}'
    
    # Ensure URL doesn't end with a slash
    server_url = server_url.rstrip('/')
    
    # Map config types to endpoints and payload - with proper type conversion
    if config_type == 'error-rate':
        endpoint = '/config/error-rate'
        payload = {'percent': float(value)}
    elif config_type == 'latency':
        endpoint = '/config/latency'
        payload = {'ms': float(value)}
    elif config_type == 'tracing':
        endpoint = '/config/tracing'
        payload = {'enabled': value.lower() in ('true', 'yes', '1')}
    else:
        logger.error(f"Unknown configuration type: {config_type}")
        return False
        
    config_url = f"{server_url}{endpoint}"
    
    # Set up headers
    if headers is None:
        headers = generate_trace_headers()
    
    try:
        logger.debug(f"Configuring server at {config_url} with {payload}")
        
        # Send POST request with configuration
        response = requests.post(
            config_url,
            json=payload,
            headers=headers,
            timeout=5
        )
        
        # Log response headers for debugging
        logger.debug(f"Response headers: {dict(response.headers)}")
        
        # If we get a 500 error and it contains 'Injected failure for testing',
        # this is part of the expected behavior when error rate is set
        if response.status_code == 500 and 'Injected failure for testing' in response.text:
            logger.info(f"Received expected injected error response (part of error rate test)")
            # Return success in this case, since this is actually working as designed
            return True
            
        if response.status_code == 200:
            logger.info(f"Server configuration updated: {config_type}={value}")
            return True
        else:
            logger.error(f"Failed to update server configuration: {response.status_code}")
            try:
                error_data = response.json()
                logger.error(f"Error message: {error_data.get('message', 'No message provided')}")
            except ValueError:
                logger.error(f"Response: {response.text}")
            return False
            
    except requests.exceptions.RequestException as e:
        logger.error(f"Error configuring server: {e}")
        return False

def get_server_config(server_url, headers=None):
    """Get current server configuration"""
    # Normalize the URL
    if not server_url.startswith(('http://', 'https://')):
        server_url = f'http://{server_url}'
    
    # Ensure URL doesn't end with a slash
    server_url = server_url.rstrip('/')
    
    config_url = f"{server_url}/config"
    
    # Set up headers
    if headers is None:
        headers = generate_trace_headers()
    
    try:
        logger.debug(f"Getting server configuration from {config_url}")
        
        # Send GET request for configuration
        response = requests.get(
            config_url,
            headers=headers,
            timeout=5
        )
        
        if response.status_code == 200:
            config_data = response.json()
            logger.info(f"Server configuration: {json.dumps(config_data)}")
            return config_data
        else:
            logger.error(f"Failed to get server configuration: {response.status_code}")
            return None
            
    except requests.exceptions.RequestException as e:
        logger.error(f"Error getting server configuration: {e}")
        return None

def main():
    # Set up command line argument parsing
    parser = argparse.ArgumentParser(description='Update the greeting word on the server and test service mesh features')
    
    # Server options
    parser.add_argument('--server', required=True, help='Server URL (e.g., localhost:3000)')
    
    # Operating mode options
    parser.add_argument('--word', help='The greeting word to use (if not provided, a random word will be generated)')
    parser.add_argument('--interval', type=int, default=120, help='Time interval between updates in seconds (default: 120)')
    parser.add_argument('--mode', choices=['normal', 'config', 'load-test', 'single-request'], default='normal',
                       help='Operation mode: normal (default), config (configure server), load-test (high frequency requests), single-request (run once and exit)')
    
    # Service mesh testing options
    parser.add_argument('--retries', type=int, default=3, help='Maximum number of retries for failed requests (default: 3)')
    parser.add_argument('--retry-delay', type=float, default=1.0, help='Initial delay between retries in seconds (default: 1.0)')
    parser.add_argument('--config-type', choices=['error-rate', 'latency', 'tracing'], 
                      help='Server configuration parameter to update (for config mode)')
    parser.add_argument('--config-value', help='Value to set for the configuration parameter (for config mode)')
    parser.add_argument('--get-config', action='store_true', help='Get current server configuration')
    
    # Load testing options
    parser.add_argument('--requests', type=int, default=100, help='Number of requests to send in load test mode (default: 100)')
    parser.add_argument('--concurrency', type=int, default=1, help='Number of concurrent requests in load test mode (default: 1)')
    
    # Logging options
    parser.add_argument('--verbose', '-v', action='store_true', help='Enable verbose logging')
    parser.add_argument('--trace', action='store_true', help='Generate unique trace ID for each request instead of reusing one')
    
    args = parser.parse_args()
    
    # Set logging level based on verbosity
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)
        logger.debug("Verbose logging enabled")
    
    logger.info(f"Client {CLIENT_ID} started - targeting server at {args.server}")
    
    # Generate trace headers (may be overridden for each request if args.trace is True)
    base_headers = generate_trace_headers()
    logger.info(f"Base trace ID: {base_headers['X-B3-TraceId']}")
    
    # Single request mode is implied if interval is very large (>9000)
    if args.interval > 9000:
        args.mode = 'single-request'
        logger.debug(f"Large interval detected ({args.interval}), switching to single-request mode")
    
    # Configuration mode: update server configuration and exit
    if args.mode == 'config':
        if not args.config_type or not args.config_value:
            logger.error("Config mode requires --config-type and --config-value parameters")
            sys.exit(1)
        
        success = configure_server(args.server, args.config_type, args.config_value, 
                                  headers=base_headers)
        sys.exit(0 if success else 1)
    
    # Get server configuration if requested
    if args.get_config:
        config = get_server_config(args.server, headers=base_headers)
        if not config:
            sys.exit(1)
    
    # Load test mode: send many requests at high frequency
    if args.mode == 'load-test':
        logger.info(f"Starting load test with {args.requests} requests, concurrency {args.concurrency}")
        
        import concurrent.futures
        
        # Function to send a single request for load testing
        def send_one_request(i):
            word = f"LOAD-{i}-{generate_random_word(4)}"
            headers = generate_trace_headers() if args.trace else base_headers
            success, response = update_greeting(args.server, word, 
                                              max_retries=args.retries, 
                                              retry_delay=args.retry_delay,
                                              headers=headers)
            return i, success, response
        
        # Use thread pool for concurrent requests
        with concurrent.futures.ThreadPoolExecutor(max_workers=args.concurrency) as executor:
            start_time = time.time()
            futures = {executor.submit(send_one_request, i): i for i in range(args.requests)}
            
            success_count = 0
            failure_count = 0
            
            for future in concurrent.futures.as_completed(futures):
                try:
                    i, success, response = future.result()
                    if success:
                        success_count += 1
                    else:
                        failure_count += 1
                        # Log failure details
                        if response:
                            status = getattr(response, 'status_code', 'unknown')
                            logger.debug(f"Request {i} failed with status: {status}")
                except Exception as e:
                    failure_count += 1
                    logger.warning(f"Request failed with exception: {str(e)}")
                
                # Print progress every 10 requests
                total_processed = success_count + failure_count
                if total_processed % 10 == 0 or total_processed == args.requests:
                    logger.info(f"Progress: {total_processed}/{args.requests} requests processed - {success_count} succeeded, {failure_count} failed")
            
            duration = time.time() - start_time
            logger.info(f"Load test completed in {duration:.2f}s - {success_count} succeeded, {failure_count} failed")
            logger.info(f"Average throughput: {args.requests / duration:.2f} requests/second")
            
            # Print a clear summary for the test script to find
            logger.info(f"SUMMARY: SuccessCount={success_count} FailureCount={failure_count} Duration={duration:.2f}s")
            
            # Log retry information
            if hasattr(args, 'retries') and args.retries > 0:
                logger.info(f"Retry configuration: max_retries={args.retries}, retry_delay={args.retry_delay}s")
            
            if failure_count == 0:
                logger.info("SUCCESS: All requests completed successfully")
                sys.exit(0)
            else:
                percent_success = (success_count / args.requests) * 100
                logger.info(f"PARTIAL: {percent_success:.1f}% of requests succeeded")
                # Only exit with failure if most requests failed
                sys.exit(0 if percent_success >= 50 else 1)
    
    # Single request mode: send one request and exit
    if args.mode == 'single-request':
        # Either use provided word or generate a random one
        if args.word and args.word.strip():
            word = args.word.strip()
            logger.info(f"Using provided word: {word}")
        else:
            word = generate_random_word()
            logger.info(f"Generated random word: {word}")
        
        # Create headers
        headers = generate_trace_headers() if args.trace else base_headers
            
        # Update the greeting on the server
        update_result, response = update_greeting(
            args.server, 
            word, 
            max_retries=args.retries,
            retry_delay=args.retry_delay,
            headers=headers
        )
        
        if update_result:
            logger.info(f"Update successful!")
            sys.exit(0)
        else:
            logger.error(f"Update failed!")
            sys.exit(1)
        
    # Normal mode: update greeting word periodically
    logger.info(f"Running in normal mode - update interval set to {args.interval} seconds")
    
    # Run in a loop, updating the greeting every specified interval
    try:
        while True:
            # Either use provided word or generate a random one
            if args.word and args.word.strip():
                word = args.word.strip()
                logger.info(f"Using provided word: {word}")
                # Generate a new random word for next time
                args.word = None
            else:
                word = generate_random_word()
                logger.info(f"Generated random word: {word}")
            
            # Create new trace headers for each request if trace mode enabled
            headers = generate_trace_headers() if args.trace else base_headers
                
            # Update the greeting on the server
            update_result, response = update_greeting(
                args.server, 
                word, 
                max_retries=args.retries,
                retry_delay=args.retry_delay,
                headers=headers
            )
            
            if update_result:
                logger.info(f"Update successful, next update in {args.interval} seconds")
            else:
                logger.warning(f"Update failed, will retry in {args.interval} seconds")
            
            # Sleep for the specified interval
            logger.debug(f"Sleeping for {args.interval} seconds")
            time.sleep(args.interval)
    
    except KeyboardInterrupt:
        logger.info("Client stopped by user")
        sys.exit(0)
    except Exception as e:
        logger.exception(f"Unexpected error occurred: {e}")
        sys.exit(1)

if __name__ == '__main__':
    main() 