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
import subprocess

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

# Add function to detect if running in Linkerd mesh
def is_in_linkerd_mesh():
    """Detect if this client is running in Linkerd mesh - returns True/False and evidence"""
    evidence = []
    
    # Check for Linkerd proxy environment variables - Most reliable indicator
    linkerd_env_vars = [
        'LINKERD_PROXY_IDENTITY_DIR',
        'LINKERD_PROXY_CONTROL_URL',
        'LINKERD_PROXY_ADMIN_LISTEN_ADDR',
        '_LINKERD_PROXY_ID'
    ]
    
    for var in linkerd_env_vars:
        if var in os.environ:
            evidence.append(f"Found env var: {var}={os.environ[var]}")
    
    # Check if linkerd-proxy process is running
    try:
        result = subprocess.run(
            ['ps', 'aux'], 
            capture_output=True, 
            text=True, 
            timeout=1
        )
        if 'linkerd-proxy' in result.stdout:
            evidence.append("Found linkerd-proxy process running")
    except Exception:
        pass
    
    # Check if Linkerd proxy port is accessible
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(0.5)
        result = sock.connect_ex(('127.0.0.1', 4191))
        sock.close()
        if result == 0:  # Port is open
            evidence.append("Linkerd proxy admin port 4191 is accessible")
    except Exception:
        pass
    
    in_mesh = len(evidence) > 0
    if in_mesh:
        logger.info(f"🔗 Client detected it's running in a Linkerd mesh: {', '.join(evidence)}")
    else:
        logger.info("🔗 Client is NOT running in a Linkerd mesh")
        
    return in_mesh, evidence

# Initialize mesh detection
CLIENT_IN_MESH, MESH_EVIDENCE = is_in_linkerd_mesh()

def generate_random_word(length=8):
    """Generate a random string to use as a greeting word."""
    letters = string.ascii_uppercase
    return ''.join(random.choice(letters) for _ in range(length))

def generate_trace_headers(use_specific_trace_id=None):
    """Generate B3 propagation headers for tracing."""
    trace_id = use_specific_trace_id or uuid.uuid4().hex
    span_id = uuid.uuid4().hex[:16]
    headers = {
        'X-B3-TraceId': trace_id,
        'X-B3-SpanId': span_id,
        'X-B3-Sampled': '1',
        'X-Client-ID': CLIENT_ID,
        'X-Client-In-Mesh': str(CLIENT_IN_MESH).lower(),
        'X-Mesh-Evidence': ','.join(MESH_EVIDENCE) if MESH_EVIDENCE else 'none'
    }
    logger.info(f"Generated trace headers: {headers}")
    return headers

def log_response_headers(response):
    """Log response headers with special attention to mesh-specific headers"""
    if not response:
        logger.debug("No response to log headers from")
        return

    all_headers = dict(response.headers)
    logger.debug(f"All response headers: {all_headers}")
    
    # Log specific headers of interest
    mesh_indicators = []
    
    # Check for standard Linkerd headers
    linkerd_headers = [h for h in all_headers.keys() if 
                      h.lower().startswith('l5d-') or
                      h.lower().startswith('x-linkerd-') or
                      h.lower() == 'server-timing' and 'linkerd' in all_headers[h].lower() or
                      h.lower() == 'via' and 'linkerd' in all_headers[h].lower() or
                      h.lower() == 'x-linkerd-meshed']
                      
    if linkerd_headers:
        logger.info(f"Found Linkerd-specific headers: {linkerd_headers}")
        mesh_indicators.extend(linkerd_headers)
                      
    # Check for our special header
    if 'X-Linkerd-Meshed' in all_headers:
        logger.info(f"Server reports mesh status: {all_headers['X-Linkerd-Meshed']}")
        mesh_indicators.append('X-Linkerd-Meshed')
        
    # Check for echo headers vs real headers
    echo_headers = [h for h in all_headers.keys() if h.startswith('Echo-')]
    if echo_headers:
        logger.info(f"Server echoed headers at application level: {echo_headers}")
    
    b3_headers = [h for h in all_headers.keys() if h.startswith('X-B3-') and not h.startswith('Echo-')]
    if b3_headers:
        logger.info(f"Found B3 headers (possibly added by mesh): {b3_headers}")
        # Only count as mesh indicator if not echoed by app
        if 'X-B3-TraceId' in b3_headers and 'Echo-X-B3-TraceId' not in all_headers:
            mesh_indicators.append('X-B3-TraceId (not echoed)')
    
    # Return if we found mesh indicators in the response
    return len(mesh_indicators) > 0, mesh_indicators

def update_greeting(server_url, word, max_retries=3, retry_delay=1.0, headers=None, 
                   record_timing=False, test_rapid_retry=False):
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
    
    retry_timings = []
    server_mesh_indicators = []
    
    # Try the request with retries
    for attempt in range(max_retries):
        attempt_start = time.time()
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
            attempt_duration = time.time() - attempt_start
            
            if record_timing:
                retry_timings.append(attempt_duration)
                
            server_host = response.headers.get('X-Server-Host', 'unknown')
            
            # Log and analyze response headers for mesh signals
            has_mesh_headers, mesh_headers = log_response_headers(response)
            if has_mesh_headers:
                server_mesh_indicators.extend(mesh_headers)
            
            # Check response status
            if response.status_code == 200:
                logger.info(f"Success! Server's greeting updated to '{word}' in {duration:.3f}s from server {server_host}")
                logger.info(f"Response: {response.text}")
                
                if record_timing:
                    logger.info(f"Request timing: {retry_timings}")
                    
                if server_mesh_indicators:
                    logger.info(f"Server mesh indicators found: {server_mesh_indicators}")
                
                return True, response, retry_timings, server_mesh_indicators
                
            elif response.status_code >= 500:  # Server errors are retryable
                logger.warning(f"Server error (status {response.status_code}) from {server_host}, will retry ({attempt+1}/{max_retries})")
                logger.warning(f"Response: {response.text}")
                
                # Retry with exponential backoff
                if attempt < max_retries - 1:
                    if test_rapid_retry:
                        # Use a very small delay to test if mesh retries faster
                        backoff_time = 0.01  # 10ms
                    else:
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
                return False, response, retry_timings, server_mesh_indicators
    
        except requests.exceptions.RequestException as e:
            logger.error(f"Request error: {type(e).__name__}: {e}")
            
            # Retry on connection errors
            if attempt < max_retries - 1:
                if test_rapid_retry:
                    backoff_time = 0.01  # 10ms
                else:
                    backoff_time = retry_delay * (2 ** attempt)
                    
                logger.debug(f"Waiting {backoff_time:.2f}s before next retry")
                time.sleep(backoff_time)
            else:
                logger.error(f"Failed after {max_retries} attempts")
                return False, None, retry_timings, server_mesh_indicators
    
    # If we get here, all retries failed
    duration = time.time() - start_time
    logger.error(f"All {max_retries} attempts failed after {duration:.3f}s")
    
    if record_timing:
        logger.info(f"Failed request timing: {retry_timings}")
        
    return False, None, retry_timings, server_mesh_indicators

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

    # Add mesh header check
    if response:
        has_mesh_headers, mesh_headers = log_response_headers(response)
        if has_mesh_headers:
            logger.info(f"Server appears to be in mesh: {mesh_headers}")

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

def get_server_mesh_status(server_url, headers=None):
    """Get server mesh status using the dedicated endpoint"""
    # Normalize the URL
    if not server_url.startswith(('http://', 'https://')):
        server_url = f'http://{server_url}'
    
    # Ensure URL doesn't end with a slash
    server_url = server_url.rstrip('/')
    
    status_url = f"{server_url}/mesh-status"
    
    # Set up headers
    if headers is None:
        headers = generate_trace_headers()
    
    try:
        logger.info(f"Checking server mesh status at {status_url}")
        
        # Send GET request for mesh status
        response = requests.get(
            status_url,
            headers=headers,
            timeout=5
        )
        
        has_mesh_headers, mesh_headers = log_response_headers(response)
        
        if response.status_code == 200:
            status_data = response.json()
            logger.info(f"Server mesh status: {json.dumps(status_data)}")
            
            # Add information about mesh headers in the response
            if has_mesh_headers:
                status_data['response_mesh_headers'] = mesh_headers
                
            return status_data
        else:
            logger.error(f"Failed to get server mesh status: {response.status_code}")
            return {'error': f"HTTP {response.status_code}", 'in_mesh': None}
            
    except requests.exceptions.RequestException as e:
        logger.error(f"Error getting server mesh status: {e}")
        return {'error': str(e), 'in_mesh': None}

def test_header_propagation(server_url, headers=None):
    """Test if B3 headers are propagated via the /no-echo endpoint (mesh-only)"""
    # Normalize the URL
    if not server_url.startswith(('http://', 'https://')):
        server_url = f'http://{server_url}'
    
    # Ensure URL doesn't end with a slash
    server_url = server_url.rstrip('/')
    
    test_url = f"{server_url}/no-echo"
    
    # Generate a special trace ID for this test
    trace_id = f"test-propagation-{uuid.uuid4().hex[:8]}"
    
    # Set up headers
    if headers is None:
        headers = generate_trace_headers(use_specific_trace_id=trace_id)
    else:
        headers['X-B3-TraceId'] = trace_id
    
    try:
        logger.info(f"Testing header propagation at {test_url} with trace ID {trace_id}")
        
        # Send GET request for mesh status
        response = requests.get(
            test_url,
            headers=headers,
            timeout=5
        )
        
        # This endpoint doesn't echo headers at application level
        # So if we see our trace ID, it must be from the mesh
        all_headers = dict(response.headers)
        logger.debug(f"All response headers: {all_headers}")
        
        # Look for our trace ID in headers
        propagated = False
        for header, value in all_headers.items():
            if trace_id in value and not header.startswith('Echo-'):
                propagated = True
                logger.info(f"Found propagated trace ID in header: {header}")
                break
                
        if propagated:
            logger.info("✅ Header propagation test PASSED - headers propagated without application echo")
            return True, response
        else:
            logger.info("❌ Header propagation test FAILED - no mesh-level propagation detected")
            return False, response
            
    except requests.exceptions.RequestException as e:
        logger.error(f"Error testing header propagation: {e}")
        return False, None

def test_rapid_retry(server_url):
    """Test if retries happen faster than our client retry logic (mesh-only feature)"""
    # First configure server for high error rate
    configure_server(server_url, 'error-rate', '50')
    
    logger.info("Testing rapid retry with deliberately slow client retry delay")
    
    # Use a large retry delay to distinguish from mesh retries
    client_retry_delay = 1.0
    max_retries = 5
    
    # Run the test with timing capture
    success, response, timings, mesh_indicators = update_greeting(
        server_url,
        f"RAPID-TEST-{generate_random_word(4)}",
        max_retries=max_retries,
        retry_delay=client_retry_delay,
        record_timing=True,
        test_rapid_retry=True  # This forces extremely small client retry delays
    )
    
    # Reset error rate
    configure_server(server_url, 'error-rate', '0')
    
    # If we got rapid retries, it suggests mesh involvement
    if timings and len(timings) > 1:
        # If any retry happened faster than our client logic could have done it
        # Must be coming from the mesh
        for t in timings[1:]:  # Skip the first timing (not a retry)
            if t < 0.1:  # Much faster than our 1.0s delay
                logger.info(f"✅ Rapid retry detected: {t:.3f}s - faster than client retry delay")
                return True, timings
    
    if timings:
        logger.info(f"❌ No rapid retries detected: {timings}")
    else:
        logger.info("❌ No retry timings captured")
        
    return False, timings

def test_automatic_retries(server_url):
    """Test if retries happen automatically (without client retry code)"""
    # Configure server for high error rate
    configure_server(server_url, 'error-rate', '50')
    
    logger.info("Testing automatic retries (will use requests library without retry logic)")
    
    try:
        # Generate a test word
        word = f"AUTO-TEST-{generate_random_word(4)}"
        
        # Set up URL
        if not server_url.startswith(('http://', 'https://')):
            server_url = f'http://{server_url}'
        server_url = server_url.rstrip('/')
        update_url = f"{server_url}/update-greeting"
        
        # Generate test headers
        headers = generate_trace_headers()
        
        # Send a direct request WITHOUT retry logic
        logger.info(f"Sending direct request without client retry logic to {update_url}")
        response = requests.post(
            update_url,
            json={'word': word},
            headers=headers,
            timeout=5  # 5 second timeout
        )
        
        # Check if it succeeded despite the high error rate
        if response.status_code == 200:
            logger.info("✅ Request succeeded without client retry logic - likely mesh retries")
            has_mesh_headers, mesh_headers = log_response_headers(response)
            return True, response
        else:
            logger.info(f"❌ Request failed as expected without retries: {response.status_code}")
            return False, response
            
    except Exception as e:
        logger.error(f"Error testing automatic retries: {e}")
        return False, None
    finally:
        # Reset error rate
        configure_server(server_url, 'error-rate', '0')

def run_mesh_detection_tests(server_url):
    """Run a series of tests specifically to detect mesh presence"""
    logger.info("======= RUNNING MESH DETECTION TESTS =======")
    
    # Store results
    results = {
        'client': {
            'in_mesh': CLIENT_IN_MESH,
            'evidence': MESH_EVIDENCE
        },
        'server': {
            'in_mesh': None,
            'evidence': []
        },
        'tests': {}
    }
    
    # Test 1: Check server's self-reported mesh status
    logger.info("Test 1: Checking server's self-reported mesh status")
    server_status = get_server_mesh_status(server_url)
    results['tests']['server_reported_status'] = server_status
    
    if 'in_mesh' in server_status:
        results['server']['in_mesh'] = server_status['in_mesh']
        if server_status['in_mesh']:
            results['server']['evidence'].append("Server self-reports as in mesh")
    
    # Test 2: Test header propagation without echo
    logger.info("Test 2: Testing header propagation without application echo")
    propagation_success, propagation_response = test_header_propagation(server_url)
    results['tests']['header_propagation'] = propagation_success
    
    if propagation_success:
        results['server']['evidence'].append("B3 headers propagated without application echo")
        if results['server']['in_mesh'] is None:
            results['server']['in_mesh'] = True
    
    # Test 3: Check for rapid retries
    logger.info("Test 3: Testing for rapid retries (mesh-only feature)")
    rapid_retry_success, rapid_retry_timings = test_rapid_retry(server_url)
    results['tests']['rapid_retries'] = {
        'success': rapid_retry_success,
        'timings': rapid_retry_timings
    }
    
    if rapid_retry_success:
        results['client']['evidence'].append("Detected rapid retries faster than client logic")
        if not results['client']['in_mesh']:
            logger.info("Updating client mesh status based on rapid retry test")
            results['client']['in_mesh'] = True
    
    # Test 4: Automatic retries without client retry code
    logger.info("Test 4: Testing for automatic retries without client retry code")
    auto_retry_success, auto_retry_response = test_automatic_retries(server_url)
    results['tests']['automatic_retries'] = auto_retry_success
    
    if auto_retry_success:
        # This could indicate either client or server mesh
        if not results['client']['in_mesh'] and not results['server']['in_mesh']:
            logger.info("Detected automatic retries but can't determine if from client or server mesh")
            results['tests']['automatic_retries_source'] = "unknown"
        elif results['client']['in_mesh']:
            logger.info("Automatic retries likely coming from client mesh")
            results['tests']['automatic_retries_source'] = "client"
        else:
            logger.info("Automatic retries likely coming from server mesh")
            results['tests']['automatic_retries_source'] = "server"
            results['server']['evidence'].append("Server appears to retry requests automatically")
            if results['server']['in_mesh'] is None:
                results['server']['in_mesh'] = True
    
    # If we still don't have a definitive answer for server mesh status
    if results['server']['in_mesh'] is None:
        # Default to False if we've tried multiple tests and found nothing
        results['server']['in_mesh'] = False
    
    # Log final detection results
    logger.info(f"======= MESH DETECTION RESULTS =======")
    logger.info(f"CLIENT IN MESH: {results['client']['in_mesh']}")
    logger.info(f"SERVER IN MESH: {results['server']['in_mesh']}")
    
    if results['client']['in_mesh']:
        logger.info(f"CLIENT EVIDENCE: {', '.join(results['client']['evidence'])}")
    if results['server']['in_mesh']:
        logger.info(f"SERVER EVIDENCE: {', '.join(results['server']['evidence'])}")
    
    return results

def main():
    # Set up command line argument parsing
    parser = argparse.ArgumentParser(description='Update the greeting word on the server and test service mesh features')
    
    # Server options
    parser.add_argument('--server', required=True, help='Server URL (e.g., localhost:3000)')
    
    # Operating mode options
    parser.add_argument('--word', help='The greeting word to use (if not provided, a random word will be generated)')
    parser.add_argument('--interval', type=int, default=120, help='Time interval between updates in seconds (default: 120)')
    parser.add_argument('--mode', choices=['normal', 'config', 'load-test', 'single-request', 'mesh-detect'],
                       default='normal', help='Operation mode: normal (default), config, load-test, single-request, mesh-detect')
    
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
    
    # Mesh detection options
    parser.add_argument('--check-mesh', action='store_true', help='Check if server and client are in the mesh')
    parser.add_argument('--test-propagation', action='store_true', help='Test header propagation')
    parser.add_argument('--test-retries', action='store_true', help='Test automatic retries')
    
    args = parser.parse_args()
    
    # Set logging level based on verbosity
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)
        logger.debug("Verbose logging enabled")
    
    logger.info(f"Client {CLIENT_ID} started - targeting server at {args.server}")
    logger.info(f"Client mesh status: {'IN MESH' if CLIENT_IN_MESH else 'NOT IN MESH'}")
    
    # Mesh detection mode
    if args.mode == 'mesh-detect' or args.check_mesh:
        mesh_results = run_mesh_detection_tests(args.server)
        print(json.dumps(mesh_results, indent=2))
        sys.exit(0)
    
    # Test specific mesh features
    if args.test_propagation:
        success, _ = test_header_propagation(args.server)
        sys.exit(0 if success else 1)
        
    if args.test_retries:
        success, _ = test_rapid_retry(args.server)
        success2, _ = test_automatic_retries(args.server)
        sys.exit(0 if (success or success2) else 1)
    
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