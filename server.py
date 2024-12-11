from http.server import HTTPServer, BaseHTTPRequestHandler
import json
import time
import threading
import signal
import logging
from collections import defaultdict
import random

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class MetricsCollector:
    def __init__(self):
        self.request_count = defaultdict(int)  # Track requests by path
        self.status_codes = defaultdict(int)   # Track response status codes
        self.request_durations = []            # Track request durations
        self.last_collection_time = time.time()
        
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

    def record_request(self, path, status_code, duration):
        self.request_count[path] += 1
        self.status_codes[status_code] += 1
        self.request_durations.append(duration)

    def get_metrics(self):
        # Calculate average request duration
        avg_duration = sum(self.request_durations) / len(self.request_durations) if self.request_durations else 0
        
        # Generate Prometheus-style metrics
        metrics = []
        
        # Add help and type information
        metrics.extend([
            "# HELP python_app_http_requests_total Total number of HTTP requests by path",
            "# TYPE python_app_http_requests_total counter",
        ])
        
        # Request counts by path
        for path, count in self.request_count.items():
            metrics.append(f'python_app_http_requests_total{{path="{path}"}} {count}')
        
        # Status code counts
        metrics.extend([
            "# HELP python_app_response_status_total Total number of HTTP responses by status code",
            "# TYPE python_app_response_status_total counter",
        ])
        for status, count in self.status_codes.items():
            metrics.append(f'python_app_response_status_total{{code="{status}"}} {count}')
        
        # Average request duration
        metrics.extend([
            "# HELP python_app_request_duration_seconds Average request duration in seconds",
            "# TYPE python_app_request_duration_seconds gauge",
            f"python_app_request_duration_seconds {avg_duration:.3f}",
        ])
        
        # Server status metrics
        metrics.extend([
            "# HELP python_app_ready Server ready status",
            "# TYPE python_app_ready gauge",
            f"python_app_ready {1 if SimpleHandler.is_ready else 0}",
            "# HELP python_app_shutting_down Server shutdown status",
            "# TYPE python_app_shutting_down gauge",
            f"python_app_shutting_down {1 if SimpleHandler.is_shutting_down else 0}",
        ])
        
        # Add demo business metrics
        metrics.extend([
            "# HELP python_app_sidekiq_queue_length Current length of Sidekiq queue",
            "# TYPE python_app_sidekiq_queue_length gauge",
            f"python_app_sidekiq_queue_length {self.demo_metrics['sidekiq_queue_length']}",
            
            "# HELP python_app_pending_audio_calls Number of pending audio calls",
            "# TYPE python_app_pending_audio_calls gauge",
            f"python_app_pending_audio_calls {self.demo_metrics['pending_audio_calls']}",
            
            "# HELP python_app_active_websocket_connections Number of active WebSocket connections",
            "# TYPE python_app_active_websocket_connections gauge",
            f"python_app_active_websocket_connections {self.demo_metrics['active_websocket_connections']}",
            
            "# HELP python_app_cache_hit_ratio_percent Cache hit ratio in percentage",
            "# TYPE python_app_cache_hit_ratio_percent gauge",
            f"python_app_cache_hit_ratio_percent {self.demo_metrics['cache_hit_ratio_percent']}",
            
            "# HELP python_app_ai_inference_latency_ms AI model inference latency in milliseconds",
            "# TYPE python_app_ai_inference_latency_ms gauge",
            f"python_app_ai_inference_latency_ms {self.demo_metrics['ai_inference_latency_ms']}"
        ])
        
        return "\n".join(metrics)

class SimpleHandler(BaseHTTPRequestHandler):
    # Class variables
    is_ready = False
    is_shutting_down = False
    metrics = MetricsCollector()

    def log_request_info(self, status_code, duration):
        """Log information about the request"""
        client_ip = self.client_address[0]
        method = self.command
        path = self.path
        logger.info(f"Request: {client_ip} - {method} {path} - Status: {status_code} - Duration: {duration:.3f}s")
        # Record metrics
        self.metrics.record_request(path, status_code, duration)

    def handle_request(self, handler_func):
        """Wrapper to measure request duration and handle logging"""
        start_time = time.time()
        status_code = handler_func()
        duration = time.time() - start_time
        self.log_request_info(status_code, duration)
        return status_code

    def send_json_response(self, status_code, data):
        """Helper method to send JSON response"""
        self.send_response(status_code)
        self.send_header('Content-type', 'application/json')
        self.end_headers()
        self.wfile.write(json.dumps(data).encode('utf-8'))
        return status_code

    @classmethod
    def prepare_server(cls, delay_seconds=10):
        """Simulate server preparation period"""
        logger.info(f"Server preparing... will be ready in {delay_seconds} seconds")
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

        if self.path == '/healthz':
            status_code = self.send_json_response(200, {'status': 'healthy'})
        
        elif self.path == '/readyz':
            if self.is_ready:
                status_code = self.send_json_response(200, {'status': 'ready'})
            else:
                status_code = self.send_json_response(503, {'status': 'not ready'})
        
        else:
            if self.is_ready:
                self.send_response(200)
                self.send_header('Content-type', 'text/html')
                self.end_headers()
                self.wfile.write(b"<html><body><h1>Hello, Third!</h1></body></html>")
                status_code = 200
            else:
                status_code = self.send_json_response(503, {'status': 'server is initializing'})

        self.log_request_info(status_code, time.time() - start_time)

class MetricsServer(HTTPServer):
    def __init__(self, metrics_collector, server_address, handler_class):
        self.metrics_collector = metrics_collector
        super().__init__(server_address, handler_class)

class MetricsHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == '/metrics':
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

    # Set up SIGTERM handler
    signal.signal(signal.SIGTERM, lambda signum, frame: handle_sigterm(signum, frame, httpd))

    try:
        httpd.serve_forever()
    finally:
        httpd.server_close()

if __name__ == '__main__':
    run(startup_delay=10)  # 10 seconds preparation time
