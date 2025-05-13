from http.server import HTTPServer, BaseHTTPRequestHandler
import json
import time
import threading
import signal
import logging
from collections import defaultdict
import random
import uuid
import socket
import os
import traceback
import subprocess
import shutil

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Get hostname for pod identification
HOSTNAME = socket.gethostname()

# Add function to detect if running in Linkerd mesh
def is_in_linkerd_mesh():
    """Detect if this server is running in Linkerd mesh"""
    # Check for Linkerd proxy environment variables
    linkerd_env_vars = [
        'LINKERD_PROXY_IDENTITY_DIR',
        'LINKERD_PROXY_CONTROL_URL',
        'LINKERD_PROXY_ADMIN_LISTEN_ADDR',
        '_LINKERD_PROXY_ID'
    ]
    for var in linkerd_env_vars:
        if var in os.environ:
            return True
    
    # Check if linkerd-proxy process is running
    try:
        result = subprocess.run(
            ['ps', 'aux'], 
            capture_output=True, 
            text=True, 
            timeout=1
        )
        if 'linkerd-proxy' in result.stdout:
            return True
    except Exception:
        pass
    
    # Check if Linkerd proxy port is accessible (default 4191 for admin API)
    try:
        import socket
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(0.5)
        result = sock.connect_ex(('127.0.0.1', 4191))
        sock.close()
        if result == 0:  # Port is open
            return True
    except Exception:
        pass
        
    return False

# Initialize mesh detection
RUNNING_IN_MESH = is_in_linkerd_mesh()
if RUNNING_IN_MESH:
    logger.info("🔗 Server detected it's running in a Linkerd mesh")
else:
    logger.info("🔗 Server is NOT running in a Linkerd mesh")

class MetricsCollector:
    def __init__(self):
        self.request_count = defaultdict(int)  # Track requests by path
        self.status_codes = defaultdict(int)   # Track response status codes
        self.request_durations = []            # Track request durations
        self.last_collection_time = time.time()
        self.tracing_ids = set()               # Track unique trace IDs
        self.client_calls = defaultdict(int)   # Track calls from different clients
        
        # Initialize demo business metrics with some default values
        self.demo_metrics = {
            'sidekiq_queue_length': 42,
            'pending_audio_calls': 7,
            'active_websocket_connections': 1723,
            'cache_hit_ratio_percent': 94,
            'ai_inference_latency_ms': 150
        }
        # Simulate some changes over time
        self.update_thread = threading.Thread(target=self._update_demo_metrics, daemon=True)
        self.update_thread.start()

    def _update_demo_metrics(self):
        """Simulate changing metrics values"""
        while True:
            self.demo_metrics['sidekiq_queue_length'] += random.randint(-5, 8)
            self.demo_metrics['pending_audio_calls'] += random.randint(-2, 3)
            self.demo_metrics['active_websocket_connections'] += random.randint(-10, 15)
            self.demo_metrics['cache_hit_ratio_percent'] = min(100, max(50, 
                self.demo_metrics['cache_hit_ratio_percent'] + random.randint(-2, 2)))
            self.demo_metrics['ai_inference_latency_ms'] = max(50, min(500,
                self.demo_metrics['ai_inference_latency_ms'] + random.randint(-10, 15)))
            
            # Keep values positive
            for key in self.demo_metrics:
                self.demo_metrics[key] = max(0, self.demo_metrics[key])
            
            time.sleep(5)  # Update every 5 seconds

    def record_request(self, path, status_code, duration, headers=None):
        self.request_count[path] += 1
        self.status_codes[status_code] += 1
        self.request_durations.append(duration)
        
        # Track tracing data
        if headers and 'X-B3-TraceId' in headers:
            self.tracing_ids.add(headers['X-B3-TraceId'])
            
        # Track client calls
        if headers and 'X-Client-ID' in headers:
            self.client_calls[headers['X-Client-ID']] += 1

    def get_metrics(self):
        # Calculate average request duration
        avg_duration = sum(self.request_durations) / len(self.request_durations) if self.request_durations else 0
        
        metrics = []
        
        # Add help and type information
        metrics.extend([
            "# HELP http_requests_total Total number of HTTP requests by path",
            "# TYPE http_requests_total counter",
        ])
        
        # Request counts by path
        for path, count in self.request_count.items():
            metrics.append(f'http_requests_total{{path="{path}"}} {count}')
        
        # Status code counts
        metrics.extend([
            "# HELP response_status_total Total number of HTTP responses by status code",
            "# TYPE response_status_total counter",
        ])
        for status, count in self.status_codes.items():
            metrics.append(f'response_status_total{{code="{status}"}} {count}')
        
        # Average request duration
        metrics.extend([
            "# HELP request_duration_seconds Average request duration in seconds",
            "# TYPE request_duration_seconds gauge",
            f"request_duration_seconds {avg_duration:.3f}",
        ])
        
        # Server status metrics
        metrics.extend([
            "# HELP ready Server ready status",
            "# TYPE ready gauge",
            f"ready {1 if SimpleHandler.is_ready else 0}",
            "# HELP shutting_down Server shutdown status",
            "# TYPE shutting_down gauge",
            f"shutting_down {1 if SimpleHandler.is_shutting_down else 0}",
        ])
        
        # Add service mesh testing metrics
        metrics.extend([
            "# HELP unique_trace_ids_count Number of unique trace IDs received",
            "# TYPE unique_trace_ids_count gauge",
            f"unique_trace_ids_count {len(self.tracing_ids)}",
            
            "# HELP hostname Pod hostname",
            "# TYPE hostname gauge",
            f'hostname{{name="{HOSTNAME}"}} 1',
            
            "# HELP error_rate_percent Percentage of responses that are errors (configurable)",
            "# TYPE error_rate_percent gauge",
            f"error_rate_percent {SimpleHandler.error_rate_percent}",
            
            "# HELP latency_injection_ms Additional latency injected into responses (ms)",
            "# TYPE latency_injection_ms gauge",
            f"latency_injection_ms {SimpleHandler.latency_injection_ms}",
        ])
        
        # Client calls metrics
        metrics.extend([
            "# HELP client_calls_total Total number of calls from each client",
            "# TYPE client_calls_total counter",
        ])
        for client_id, count in self.client_calls.items():
            metrics.append(f'client_calls_total{{client_id="{client_id}"}} {count}')
        
        # Add demo business metrics
        metrics.extend([
            "# HELP sidekiq_queue_length Current length of Sidekiq queue",
            "# TYPE sidekiq_queue_length gauge",
            f"sidekiq_queue_length {self.demo_metrics['sidekiq_queue_length']}",
            
            "# HELP pending_audio_calls Number of pending audio calls",
            "# TYPE pending_audio_calls gauge",
            f"pending_audio_calls {self.demo_metrics['pending_audio_calls']}",
            
            "# HELP active_websocket_connections Number of active WebSocket connections",
            "# TYPE active_websocket_connections gauge",
            f"active_websocket_connections {self.demo_metrics['active_websocket_connections']}",
            
            "# HELP cache_hit_ratio_percent Cache hit ratio in percentage",
            "# TYPE cache_hit_ratio_percent gauge",
            f"cache_hit_ratio_percent {self.demo_metrics['cache_hit_ratio_percent']}",
            
            "# HELP ai_inference_latency_ms AI model inference latency in milliseconds",
            "# TYPE ai_inference_latency_ms gauge",
            f"ai_inference_latency_ms {self.demo_metrics['ai_inference_latency_ms']}"
        ])
        
        return "\n".join(metrics)

class SimpleHandler(BaseHTTPRequestHandler):
    # Class variables
    is_ready = False
    is_shutting_down = False
    metrics = MetricsCollector()
    greeting_word = "MAN"  # Default greeting word
    
    # Service mesh testing properties
    error_rate_percent = 0   # % of requests that return 500 errors
    latency_injection_ms = 0  # Additional latency to inject
    trace_propagation = True  # Whether to propagate tracing headers
    
    # Mesh status - this is determined at startup
    in_mesh = RUNNING_IN_MESH

    def log_request_info(self, status_code, duration):
        """Log information about the request"""
        client_ip = self.client_address[0]
        method = self.command
        path = self.path
        
        # Extract tracing headers for logging
        trace_id = self.headers.get('X-B3-TraceId', 'none')
        span_id = self.headers.get('X-B3-SpanId', 'none')
        
        logger.info(f"Request: {client_ip} - {method} {path} - Status: {status_code} - Duration: {duration:.3f}s - TraceID: {trace_id} - SpanID: {span_id}")
        
        # Record metrics
        self.metrics.record_request(path, status_code, duration, dict(self.headers))

    def handle_request(self, handler_func):
        """Wrapper to measure request duration and handle logging"""
        start_time = time.time()
        status_code = handler_func()
        duration = time.time() - start_time
        self.log_request_info(status_code, duration)
        return status_code

    def send_json_response(self, status_code, data):
        """Helper method to send JSON response"""
        # Apply artificial latency if configured
        if SimpleHandler.latency_injection_ms > 0:
            time.sleep(SimpleHandler.latency_injection_ms / 1000.0)
            
        # Set response headers
        self.send_response(status_code)
        self.send_header('Content-type', 'application/json')
        self.send_header('X-Server-Host', HOSTNAME)
        
        # Add Linkerd-specific headers if we're in the mesh
        # These will ONLY be present if actually in mesh
        if SimpleHandler.in_mesh:
            self.send_header('X-Linkerd-Meshed', 'true')
            self.send_header('Server-Mesh-ID', os.environ.get('_LINKERD_PROXY_ID', 'unknown'))
        
        # Propagate tracing headers if enabled
        # We only do this in "echo mode" to help test distinguish app-level vs mesh-level
        if SimpleHandler.trace_propagation and 'X-B3-TraceId' in self.headers:
            for header in ['X-B3-TraceId', 'X-B3-SpanId', 'X-B3-ParentSpanId', 'X-B3-Sampled']:
                if header in self.headers:
                    # Add "Echo-" prefix to make it clear this is application-level echo
                    # not mesh-level propagation
                    self.send_header(f'Echo-{header}', self.headers[header])
        
        self.end_headers()
        self.wfile.write(json.dumps(data).encode('utf-8'))
        return status_code

    @classmethod
    def prepare_server(cls, delay_seconds=10):
        """Simulate server preparation period"""
        logger.info(f"Server preparing.... will be ready in {delay_seconds} seconds")
        time.sleep(delay_seconds)
        logger.info("Server preparation complete")
        cls.is_ready = True

    @classmethod
    def start_shutdown(cls):
        """Mark server as shutting down"""
        logger.info("Received SIGTERM, starting graceful shutdown")
        cls.is_shutting_down = True
        cls.is_ready = False

    def do_GET(self):
        start_time = time.time()
        
        if self.is_shutting_down:
            self.send_json_response(503, {'status': 'shutting down'})
            self.log_request_info(503, time.time() - start_time)
            return

        # Random failure injection based on error rate
        if random.randint(1, 100) <= SimpleHandler.error_rate_percent:
            self.send_json_response(500, {'status': 'error', 'message': 'Injected failure for testing'})
            self.log_request_info(500, time.time() - start_time)
            return

        if self.path == '/healthz':
            status_code = self.send_json_response(200, {'status': 'healthy'})
        
        elif self.path == '/readyz':
            if self.is_ready:
                status_code = self.send_json_response(200, {'status': 'ready'})
            else:
                status_code = self.send_json_response(503, {'status': 'not ready'})
        
        elif self.path == '/config':
            # Return current configuration
            status_code = self.send_json_response(200, {
                'greeting_word': self.greeting_word,
                'error_rate_percent': self.error_rate_percent,
                'latency_injection_ms': self.latency_injection_ms,
                'trace_propagation': self.trace_propagation,
                'hostname': HOSTNAME,
                'in_mesh': self.in_mesh
            })
            
        # Add a mesh-specific endpoint
        elif self.path == '/mesh-status':
            mesh_info = {
                'in_mesh': self.in_mesh,
                'hostname': HOSTNAME,
                'mesh_env_vars': {
                    var: os.environ.get(var, 'not present')
                    for var in [
                        'LINKERD_PROXY_IDENTITY_DIR',
                        'LINKERD_PROXY_CONTROL_URL',
                        'LINKERD_PROXY_ADMIN_LISTEN_ADDR',
                        '_LINKERD_PROXY_ID'
                    ]
                }
            }
            
            # Check if we can access the Linkerd proxy API (only available if in mesh)
            try:
                import urllib.request
                req = urllib.request.Request('http://localhost:4191/ready')
                req.add_header('User-Agent', 'python-mesh-test')
                with urllib.request.urlopen(req, timeout=0.5) as response:
                    mesh_info['proxy_ready'] = response.read().decode('utf-8').strip() == 'proxy is ready'
            except Exception as e:
                mesh_info['proxy_ready'] = False
                mesh_info['proxy_error'] = str(e)
                
            status_code = self.send_json_response(200, mesh_info)
            
        # Add a special endpoint that doesn't echo headers
        elif self.path == '/no-echo':
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.send_header('X-Server-Host', HOSTNAME)
            
            # Only add mesh headers if in mesh - never echo client headers here
            if SimpleHandler.in_mesh:
                self.send_header('X-Linkerd-Meshed', 'true')
            
            self.end_headers()
            self.wfile.write(json.dumps({
                'status': 'success',
                'echo_disabled': True,
                'in_mesh': self.in_mesh
            }).encode('utf-8'))
            status_code = 200
            
        elif self.path == '/download':
            file_path = 'large_file.dat'
            if os.path.exists(file_path):
                try:
                    with open(file_path, 'rb') as f:
                        # Get file stats using the valid file descriptor
                        fs = os.fstat(f.fileno())

                        # Send headers *before* sending the body
                        self.send_response(200)
                        self.send_header('Content-type', 'application/octet-stream')
                        self.send_header('Content-Disposition', f'attachment; filename="{os.path.basename(file_path)}"')
                        self.send_header("Content-Length", str(fs.st_size))
                        self.end_headers()

                        # Stream the file content using the same file object
                        shutil.copyfileobj(f, self.wfile)

                    status_code = 200 # Mark success

                except Exception as e:
                    logger.error(f"Error during file download {file_path}: {e}\n{traceback.format_exc()}")
                    # We might not be able to send a proper error response if headers were partially sent
                    # Best effort: Log it. The connection will likely be broken.
                    status_code = 500 # For logging purposes
            else:
                status_code = self.send_json_response(404, {'status': 'error', 'message': 'Large file not found'})
            
        else:
            if self.is_ready:
                # Apply artificial latency if configured
                if SimpleHandler.latency_injection_ms > 0:
                    time.sleep(SimpleHandler.latency_injection_ms / 1000.0)
                    
                self.send_response(200)
                self.send_header('Content-type', 'text/html')
                self.send_header('X-Server-Host', HOSTNAME)
                
                # Add Linkerd-specific headers if we're in the mesh
                if SimpleHandler.in_mesh:
                    self.send_header('X-Linkerd-Meshed', 'true')
                
                # Propagate tracing headers if enabled
                if SimpleHandler.trace_propagation and 'X-B3-TraceId' in self.headers:
                    for header in ['X-B3-TraceId', 'X-B3-SpanId', 'X-B3-ParentSpanId', 'X-B3-Sampled']:
                        if header in self.headers:
                            # Add "Echo-" prefix to make it clear this is application-level echo
                            self.send_header(f'Echo-{header}', self.headers[header])
                
                self.end_headers()
                self.wfile.write(f"<html><body><h1>ADINAS, {self.greeting_word}!</h1><p>From: {HOSTNAME}</p><p>In Mesh: {self.in_mesh}</p></body></html>".encode('utf-8'))
                status_code = 200
            else:
                status_code = self.send_json_response(503, {'status': 'server is initializing'})

        self.log_request_info(status_code, time.time() - start_time)
    
    def do_POST(self):
        start_time = time.time()
        
        if self.is_shutting_down:
            status_code = self.send_json_response(503, {'status': 'shutting down'})
            self.log_request_info(status_code, time.time() - start_time)
            return
            
        if not self.is_ready:
            status_code = self.send_json_response(503, {'status': 'server is initializing'})
            self.log_request_info(status_code, time.time() - start_time)
            return
            
        # Random failure injection based on error rate
        if random.randint(1, 100) <= SimpleHandler.error_rate_percent:
            self.send_json_response(500, {'status': 'error', 'message': 'Injected failure for testing'})
            self.log_request_info(500, time.time() - start_time)
            return
            
        # Get request content
        content_length = int(self.headers.get('Content-Length', 0))
        post_data = self.rfile.read(content_length).decode('utf-8') if content_length > 0 else '{}'
            
        try:
            data = json.loads(post_data)
            
            # Process POST request to update greeting word
            if self.path == '/update-greeting':
                if 'word' in data and isinstance(data['word'], str) and data['word'].strip():
                    # Update the class variable to change greeting for all instances
                    SimpleHandler.greeting_word = data['word'].strip()
                    status_code = self.send_json_response(200, {
                        'status': 'success', 
                        'message': f'Greeting updated to: {SimpleHandler.greeting_word}',
                        'hostname': HOSTNAME
                    })
                else:
                    status_code = self.send_json_response(400, {
                        'status': 'error',
                        'message': 'Invalid request: "word" field is required and must be a non-empty string'
                    })
            
            # Configure error rate
            elif self.path == '/config/error-rate':
                if 'percent' in data and isinstance(data['percent'], (int, float)) and 0 <= data['percent'] <= 100:
                    SimpleHandler.error_rate_percent = data['percent']
                    status_code = self.send_json_response(200, {
                        'status': 'success',
                        'message': f'Error rate updated to: {SimpleHandler.error_rate_percent}%',
                        'hostname': HOSTNAME
                    })
                else:
                    status_code = self.send_json_response(400, {
                        'status': 'error',
                        'message': 'Invalid request: "percent" field must be a number between 0 and 100'
                    })
            
            # Configure latency injection
            elif self.path == '/config/latency':
                if 'ms' in data and isinstance(data['ms'], (int, float)) and data['ms'] >= 0:
                    SimpleHandler.latency_injection_ms = data['ms']
                    status_code = self.send_json_response(200, {
                        'status': 'success',
                        'message': f'Latency injection updated to: {SimpleHandler.latency_injection_ms}ms',
                        'hostname': HOSTNAME
                    })
                else:
                    status_code = self.send_json_response(400, {
                        'status': 'error',
                        'message': 'Invalid request: "ms" field must be a non-negative number'
                    })
                    
            # Configure tracing behavior
            elif self.path == '/config/tracing':
                if 'enabled' in data and isinstance(data['enabled'], bool):
                    SimpleHandler.trace_propagation = data['enabled']
                    status_code = self.send_json_response(200, {
                        'status': 'success',
                        'message': f'Trace propagation {"enabled" if SimpleHandler.trace_propagation else "disabled"}',
                        'hostname': HOSTNAME
                    })
                else:
                    status_code = self.send_json_response(400, {
                        'status': 'error',
                        'message': 'Invalid request: "enabled" field must be a boolean'
                    })
            else:
                status_code = self.send_json_response(404, {'status': 'not found'})
                
        except json.JSONDecodeError:
            status_code = self.send_json_response(400, {
                'status': 'error',
                'message': 'Invalid JSON format'
            })
            
        self.log_request_info(status_code, time.time() - start_time)

class MetricsServer(HTTPServer):
    def __init__(self, metrics_collector, server_address, handler_class):
        self.metrics_collector = metrics_collector
        super().__init__(server_address, handler_class)

class MetricsHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == '/api/metrics':
            self.send_response(200)
            self.send_header('Content-type', 'text/plain')
            self.end_headers()
            # Get metrics from the shared collector
            metrics = self.server.metrics_collector.get_metrics()
            self.wfile.write(metrics.encode('utf-8'))
        else:
            self.send_response(404)
            self.send_header('Content-type', 'text/plain')
            self.end_headers()
            self.wfile.write(b'Not Found')

def handle_sigterm(signum, frame, server):
    """Handle SIGTERM signal"""
    print("\nReceived SIGTERM. Starting graceful shutdown...")
    
    # Mark server as shutting down
    SimpleHandler.start_shutdown()
    
    # Give ongoing requests time to complete (5 seconds)
    time.sleep(5)
    
    # Stop the server
    print("Stopping server...")
    server.shutdown()

def run_metrics_server(metrics_collector, port=9090):
    """Run the metrics server in a separate thread"""
    server = MetricsServer(
        metrics_collector,
        server_address=('', port),
        handler_class=MetricsHandler
    )
    logger.info(f"Metrics server running on port {port}")
    server.serve_forever()

def run(server_class=HTTPServer, handler_class=SimpleHandler, port=3000, startup_delay=10):
    # Get startup_delay from environment if available
    startup_delay = int(os.environ.get('STARTUP_DELAY_SECONDS', startup_delay))
    
    # Read configuration from environment variables
    handler_class.error_rate_percent = float(os.environ.get('ERROR_RATE_PERCENT', '0'))
    handler_class.latency_injection_ms = float(os.environ.get('LATENCY_INJECTION_MS', '0'))
    handler_class.trace_propagation = os.environ.get('TRACE_PROPAGATION', 'true').lower() == 'true'
    
    # Start preparation in a separate thread
    prep_thread = threading.Thread(
        target=handler_class.prepare_server,
        args=(startup_delay,),
        daemon=True
    )
    prep_thread.start()

    # Start the metrics server in a separate thread
    metrics_thread = threading.Thread(
        target=run_metrics_server,
        args=(handler_class.metrics,),
        daemon=True
    )
    metrics_thread.start()

    # Start the main server
    server_address = ('', port)
    httpd = server_class(server_address, handler_class)
    logger.info(f"Main server running on port {port}")
    logger.info(f"Server configuration: error_rate={handler_class.error_rate_percent}%, latency={handler_class.latency_injection_ms}ms, tracing={handler_class.trace_propagation}")

    # Set up SIGTERM handler
    signal.signal(signal.SIGTERM, lambda signum, frame: handle_sigterm(signum, frame, httpd))

    try:
        httpd.serve_forever()
    finally:
        httpd.server_close()

if __name__ == '__main__':
    run(startup_delay=int(os.environ.get('STARTUP_DELAY_SECONDS', 10)))
