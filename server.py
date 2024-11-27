from http.server import HTTPServer, BaseHTTPRequestHandler
import json
import time
import threading
import signal
import logging

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class SimpleHandler(BaseHTTPRequestHandler):
    # Track server readiness state
    is_ready = False
    is_shutting_down = False

    def log_request_info(self, status_code):
        """Log information about the request"""
        client_ip = self.client_address[0]
        method = self.command
        path = self.path
        logger.info(f"Request: {client_ip} - {method} {path} - Status: {status_code}")

    def send_json_response(self, status_code, data):
        """Helper method to send JSON response and log request"""
        self.send_response(status_code)
        self.send_header('Content-type', 'application/json')
        self.end_headers()
        self.wfile.write(json.dumps(data).encode('utf-8'))
        self.log_request_info(status_code)

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
        if self.is_shutting_down:
            self.send_json_response(503, {'status': 'shutting down'})
            return

        if self.path == '/healthz':
            self.send_json_response(200, {'status': 'healthy'})
        
        elif self.path == '/readyz':
            if self.is_ready:
                self.send_json_response(200, {'status': 'ready'})
            else:
                self.send_json_response(503, {'status': 'not ready'})
        
        else:
            if self.is_ready:
                self.send_response(200)
                self.send_header('Content-type', 'text/html')
                self.end_headers()
                self.wfile.write(b"<html><body><h1>Hello, Third!</h1></body></html>")
                self.log_request_info(200)
            else:
                self.send_json_response(503, {'status': 'server is initializing'})

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

def run(server_class=HTTPServer, handler_class=SimpleHandler, port=3000, startup_delay=10):
    # Start preparation in a separate thread
    prep_thread = threading.Thread(
        target=handler_class.prepare_server,
        args=(startup_delay,),
        daemon=True
    )
    prep_thread.start()

    # Start the server
    server_address = ('', port)
    httpd = server_class(server_address, handler_class)
    print(f"Server running on port {port}")

    # Set up SIGTERM handler
    signal.signal(signal.SIGTERM, lambda signum, frame: handle_sigterm(signum, frame, httpd))

    try:
        httpd.serve_forever()
    finally:
        httpd.server_close()

if __name__ == '__main__':
    run(startup_delay=10)  # 10 seconds preparation time
