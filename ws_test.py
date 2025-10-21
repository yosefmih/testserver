#!/usr/bin/env python3
"""
WebSocket stress testing and reliability script.
Tests connection stability, message throughput, and failure scenarios.
"""

import asyncio
import websockets
import json
import time
import argparse
import signal
import sys
from datetime import datetime
from collections import defaultdict

class WebSocketTester:
    def __init__(self, url, endpoint):
        self.url = url + endpoint
        self.endpoint = endpoint
        self.stats = {
            'connected_at': None,
            'disconnected_at': None,
            'messages_sent': 0,
            'messages_received': 0,
            'errors': 0,
            'reconnects': 0,
            'last_message_time': None,
            'message_gaps': []
        }
        self.running = True
        self.ws = None
        
    def format_duration(self, seconds):
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        secs = int(seconds % 60)
        if hours > 0:
            return f"{hours}h {minutes}m {secs}s"
        elif minutes > 0:
            return f"{minutes}m {secs}s"
        else:
            return f"{secs}s"
    
    def print_stats(self):
        if self.stats['connected_at']:
            uptime = time.time() - self.stats['connected_at']
            print(f"\n{'='*60}")
            print(f"Connection Stats - {datetime.now().strftime('%H:%M:%S')}")
            print(f"{'='*60}")
            print(f"Endpoint:          {self.endpoint}")
            print(f"Uptime:            {self.format_duration(uptime)}")
            print(f"Messages Sent:     {self.stats['messages_sent']}")
            print(f"Messages Received: {self.stats['messages_received']}")
            print(f"Errors:            {self.stats['errors']}")
            print(f"Reconnects:        {self.stats['reconnects']}")
            
            if self.stats['message_gaps']:
                avg_gap = sum(self.stats['message_gaps']) / len(self.stats['message_gaps'])
                max_gap = max(self.stats['message_gaps'])
                print(f"Avg Message Gap:   {avg_gap:.2f}s")
                print(f"Max Message Gap:   {max_gap:.2f}s (⚠️ possible timeout issue)")
            print(f"{'='*60}\n")
    
    async def connect_and_run(self, test_mode):
        """Main connection and testing loop with auto-reconnect"""
        while self.running:
            try:
                print(f"🔌 Connecting to {self.url}...")
                async with websockets.connect(self.url) as websocket:
                    self.ws = websocket
                    self.stats['connected_at'] = time.time()
                    print(f"✅ Connected to {self.url}")
                    
                    if test_mode == 'echo':
                        await self.test_echo(websocket)
                    elif test_mode == 'stream':
                        await self.test_stream(websocket)
                    elif test_mode == 'chat':
                        await self.test_chat(websocket)
                    elif test_mode == 'stress':
                        await self.test_stress(websocket)
                    
            except websockets.exceptions.ConnectionClosed as e:
                print(f"❌ Connection closed: {e}")
                self.stats['errors'] += 1
                self.stats['disconnected_at'] = time.time()
                self.print_stats()
                
                if self.running:
                    self.stats['reconnects'] += 1
                    print(f"🔄 Reconnecting in 5 seconds... (attempt {self.stats['reconnects']})")
                    await asyncio.sleep(5)
                    self.stats['connected_at'] = None
                    
            except Exception as e:
                print(f"❌ Error: {e}")
                self.stats['errors'] += 1
                if self.running:
                    print("🔄 Reconnecting in 5 seconds...")
                    await asyncio.sleep(5)
    
    async def test_echo(self, websocket):
        """Send periodic messages and expect echoes back"""
        print("📤 Starting echo test - sending message every 5 seconds")
        
        receive_task = asyncio.create_task(self.receive_messages(websocket))
        send_task = asyncio.create_task(self.send_periodic_messages(websocket, interval=5))
        
        await asyncio.gather(receive_task, send_task)
    
    async def test_stream(self, websocket):
        """Just listen for server-pushed messages"""
        print("📥 Starting stream test - listening for server messages")
        
        await self.receive_messages(websocket)
    
    async def test_chat(self, websocket):
        """Send chat messages periodically"""
        print("💬 Starting chat test")
        
        receive_task = asyncio.create_task(self.receive_messages(websocket))
        send_task = asyncio.create_task(self.send_chat_messages(websocket, interval=10))
        
        await asyncio.gather(receive_task, send_task)
    
    async def test_stress(self, websocket):
        """Send messages as fast as possible to test throughput"""
        print("⚡ Starting stress test - rapid fire messages")
        
        receive_task = asyncio.create_task(self.receive_messages(websocket))
        send_task = asyncio.create_task(self.send_periodic_messages(websocket, interval=0.1))
        
        await asyncio.gather(receive_task, send_task)
    
    async def receive_messages(self, websocket):
        """Receive and log messages"""
        last_print_time = time.time()
        
        async for message in websocket:
            now = time.time()
            self.stats['messages_received'] += 1
            
            # Track message gaps to detect timeouts
            if self.stats['last_message_time']:
                gap = now - self.stats['last_message_time']
                self.stats['message_gaps'].append(gap)
                
                # Warn if gap is suspiciously long (potential timeout/reconnect)
                if gap > 60:
                    print(f"⚠️  Large gap detected: {gap:.1f}s since last message")
            
            self.stats['last_message_time'] = now
            
            # Print stats every 30 seconds
            if now - last_print_time > 30:
                self.print_stats()
                last_print_time = now
            
            # Parse and log message
            try:
                data = json.loads(message)
                msg_type = data.get('type', 'unknown')
                if msg_type == 'welcome':
                    print(f"👋 {data.get('message')}")
                elif msg_type == 'heartbeat':
                    counter = data.get('counter')
                    print(f"💓 Heartbeat #{counter}", end='\r')
                elif msg_type == 'echo':
                    print(f"🔄 Echo received")
                elif msg_type == 'system':
                    print(f"🔔 System: {data.get('message')}")
                elif msg_type == 'chat':
                    print(f"💬 Chat from {data.get('client_id')}: {data.get('message')}")
            except json.JSONDecodeError:
                print(f"📨 Raw message: {message[:100]}")
    
    async def send_periodic_messages(self, websocket, interval=5):
        """Send messages at regular intervals"""
        counter = 0
        while self.running:
            await asyncio.sleep(interval)
            counter += 1
            message = f"Test message #{counter} at {datetime.now().isoformat()}"
            await websocket.send(message)
            self.stats['messages_sent'] += 1
            if interval >= 1:  # Only print for non-stress tests
                print(f"📤 Sent: {message}")
    
    async def send_chat_messages(self, websocket, interval=10):
        """Send chat-formatted messages"""
        counter = 0
        while self.running:
            await asyncio.sleep(interval)
            counter += 1
            message = json.dumps({
                "message": f"Chat message #{counter} from tester"
            })
            await websocket.send(message)
            self.stats['messages_sent'] += 1
            print(f"💬 Sent chat message #{counter}")
    
    def stop(self):
        """Stop the tester gracefully"""
        print("\n🛑 Stopping tester...")
        self.running = False
        self.print_stats()

async def main():
    parser = argparse.ArgumentParser(description='WebSocket stress and reliability tester')
    parser.add_argument('url', help='WebSocket URL (e.g., wss://example.com)')
    parser.add_argument('--endpoint', '-e', 
                       choices=['echo', 'stream', 'chat'],
                       default='stream',
                       help='WebSocket endpoint to test')
    parser.add_argument('--mode', '-m',
                       choices=['echo', 'stream', 'chat', 'stress'],
                       default='stream',
                       help='Test mode (stress = high throughput test)')
    
    args = parser.parse_args()
    
    # Map endpoint to path
    endpoint_paths = {
        'echo': '/ws/echo',
        'stream': '/ws/stream',
        'chat': '/ws/chat'
    }
    
    endpoint = endpoint_paths[args.endpoint]
    tester = WebSocketTester(args.url, endpoint)
    
    # Handle Ctrl+C gracefully
    def signal_handler(sig, frame):
        tester.stop()
        sys.exit(0)
    
    signal.signal(signal.SIGINT, signal_handler)
    
    print(f"🚀 Starting WebSocket tester")
    print(f"   URL: {args.url}{endpoint}")
    print(f"   Mode: {args.mode}")
    print(f"   Press Ctrl+C to stop\n")
    
    await tester.connect_and_run(args.mode)

if __name__ == '__main__':
    asyncio.run(main())
