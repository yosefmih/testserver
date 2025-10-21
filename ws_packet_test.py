#!/usr/bin/env python3
"""
Low-level WebSocket packet analyzer.
Shows all frames including ping/pong and control frames.
"""

import asyncio
import websockets
import argparse
import signal
import sys
from datetime import datetime
import struct
import logging

class WebSocketPacketAnalyzer:
    def __init__(self, url, endpoint, verbose=False):
        self.url = url + endpoint
        self.endpoint = endpoint
        self.running = True
        self.connection_start = None
        self.last_activity = None
        self.verbose = verbose
        self.frame_count = {
            'text': 0,
            'binary': 0,
            'ping': 0,
            'pong': 0,
            'close': 0,
            'other': 0
        }
        
        if verbose:
            # Enable websockets library debug logging
            logging.basicConfig(
                level=logging.DEBUG,
                format='[%(asctime)s] [%(name)s] %(levelname)s: %(message)s'
            )
            logging.getLogger('websockets').setLevel(logging.DEBUG)
        
    def log(self, message, frame_type=None):
        """Log with timestamp and time since connection"""
        now = datetime.now()
        timestamp = now.strftime('%H:%M:%S.%f')[:-3]
        
        if self.connection_start:
            elapsed = (now - self.connection_start).total_seconds()
            since_last = (now - self.last_activity).total_seconds() if self.last_activity else 0
            self.last_activity = now
            
            type_emoji = {
                'text': '📝',
                'binary': '🔢',
                'ping': '🏓',
                'pong': '🏓',
                'close': '🚪',
                'other': '❓'
            }
            emoji = type_emoji.get(frame_type, '📦')
            
            print(f"[{timestamp}] [{elapsed:6.1f}s] [+{since_last:5.2f}s] {emoji} {message}")
        else:
            print(f"[{timestamp}] {message}")
    
    def print_stats(self):
        """Print current frame statistics"""
        print(f"\n{'='*70}")
        print(f"Frame Statistics")
        print(f"{'='*70}")
        for frame_type, count in self.frame_count.items():
            if count > 0:
                print(f"  {frame_type.capitalize():10s}: {count}")
        print(f"{'='*70}\n")
    
    async def connect_with_raw_frames(self):
        """Connect and intercept all frames including ping/pong"""
        try:
            print(f"🔌 Connecting to {self.url}")
            print(f"⚙️  Using websockets library version: {websockets.__version__}")
            print(f"📊 This will show ALL frames including ping/pong\n")
            
            # Connect with custom ping settings to see what's happening
            ping_interval = 20  # Default
            ping_timeout = 20
            
            print(f"🏓 Ping interval: {ping_interval}s")
            print(f"⏱️  Ping timeout: {ping_timeout}s\n")
            
            async with websockets.connect(
                self.url,
                ping_interval=ping_interval,
                ping_timeout=ping_timeout
            ) as websocket:
                self.connection_start = datetime.now()
                self.last_activity = self.connection_start
                self.log("✅ Connection established", "other")
                
                # Monkey-patch to intercept ping/pong
                original_pong = websocket.pong
                original_ping = websocket.ping
                
                async def logged_pong(data=b""):
                    self.frame_count['pong'] += 1
                    self.log(f"PONG sent (response to ping) - data: {data.hex() if data else '(empty)'}", "pong")
                    return await original_pong(data)
                
                async def logged_ping(data=b""):
                    self.frame_count['ping'] += 1
                    self.log(f"PING sent by client - data: {data.hex() if data else '(empty)'}", "ping")
                    return await original_ping(data)
                
                websocket.pong = logged_pong
                websocket.ping = logged_ping
                
                # Monitor for incoming messages
                async for message in websocket:
                    self.frame_count['text'] += 1
                    
                    # Try to parse as JSON for prettier output
                    try:
                        import json
                        data = json.loads(message)
                        msg_type = data.get('type', 'unknown')
                        
                        if msg_type == 'welcome':
                            self.log(f"TEXT frame - Welcome message", "text")
                        elif msg_type == 'heartbeat':
                            counter = data.get('counter', '?')
                            self.log(f"TEXT frame - Heartbeat #{counter}", "text")
                        elif msg_type == 'echo':
                            self.log(f"TEXT frame - Echo response", "text")
                        else:
                            self.log(f"TEXT frame - Type: {msg_type}", "text")
                    except:
                        self.log(f"TEXT frame - Length: {len(message)} bytes", "text")
                    
        except websockets.exceptions.ConnectionClosed as e:
            elapsed = (datetime.now() - self.connection_start).total_seconds() if self.connection_start else 0
            reason = e.reason if e.reason else "(no reason provided)"
            self.log(f"❌ Connection closed after {elapsed:.1f}s - Code: {e.code}, Reason: {reason}", "close")
            self.frame_count['close'] += 1
            
            print(f"\n{'='*70}")
            print(f"CONNECTION CLOSED ANALYSIS")
            print(f"{'='*70}")
            print(f"Duration: {elapsed:.1f}s")
            print(f"Close Code: {e.code}")
            print(f"Reason: {reason}")
            if e.code == 1006:
                print(f"Code 1006 = Abnormal Closure (no close frame, likely timeout/network issue)")
            print(f"{'='*70}\n")
        except Exception as e:
            self.log(f"❌ Error: {e}", "other")
        finally:
            self.print_stats()
    
    async def connect_with_disabled_pings(self):
        """Connect with pings disabled to test timeout behavior"""
        try:
            print(f"🔌 Connecting to {self.url}")
            print(f"🚫 PINGS DISABLED - Testing raw timeout behavior")
            print(f"⚙️  Using websockets library version: {websockets.__version__}")
            print(f"📊 Will log status every 10s to show connection is alive\n")
            
            async with websockets.connect(
                self.url,
                ping_interval=None,  # Disable automatic pings
                ping_timeout=None
            ) as websocket:
                self.connection_start = datetime.now()
                self.last_activity = self.connection_start
                self.log("✅ Connection established (NO PINGS)", "other")
                self.log("⏳ Waiting silently to test timeout...", "other")
                self.log("📍 Expected: Connection should drop at 60s (nginx) or 350s (NLB)", "other")
                
                # Create a task to log alive status every 10s and test connection at milestones
                async def status_logger():
                    milestones_tested = set()
                    while self.running:
                        await asyncio.sleep(10)
                        elapsed = (datetime.now() - self.connection_start).total_seconds()
                        self.log(f"💚 Still alive - no activity, no pings, no timeouts (elapsed: {elapsed:.0f}s)", "other")
                        
                        # Test connection at key milestones by sending an echo message
                        # Use 10s buffer to ensure timeout should have triggered
                        milestone = None
                        if 360 <= elapsed < 370 and 350 not in milestones_tested:
                            milestone = 350
                            milestone_name = "350s NLB timeout (+10s buffer)"
                        elif 510 <= elapsed < 520 and 500 not in milestones_tested:
                            milestone = 500
                            milestone_name = "500s nginx timeout (+10s buffer)"
                        
                        if milestone:
                            milestones_tested.add(milestone)
                            self.log(f"⚠️  Past {milestone_name} - still connected! Sending test message...", "other")
                            try:
                                test_msg = f"Test message at {elapsed:.0f}s to verify connection is alive"
                                await websocket.send(test_msg)
                                self.log(f"📤 Test message sent to buffer - waiting to see if connection responds...", "other")
                                # Give it a moment to detect if connection is actually dead
                                await asyncio.sleep(0.5)
                                self.log(f"✅ No immediate error - connection appears alive (or half-open)", "other")
                            except Exception as e:
                                self.log(f"❌ Failed to send test message: {e} - connection is dead", "other")
                                raise
                
                # Create task for receiving messages
                async def receive_loop():
                    async for message in websocket:
                        self.frame_count['text'] += 1
                        try:
                            import json
                            data = json.loads(message)
                            msg_type = data.get('type', 'unknown')
                            self.log(f"TEXT frame - Type: {msg_type}", "text")
                        except:
                            self.log(f"TEXT frame - Length: {len(message)} bytes", "text")
                
                # Run both tasks
                await asyncio.gather(status_logger(), receive_loop())
                    
        except websockets.exceptions.ConnectionClosed as e:
            elapsed = (datetime.now() - self.connection_start).total_seconds() if self.connection_start else 0
            reason = e.reason if e.reason else "(no reason provided)"
            self.log(f"❌ Connection closed after {elapsed:.1f}s - Code: {e.code}, Reason: {reason}", "close")
            self.frame_count['close'] += 1
            
            # Provide detailed analysis of when connection closed
            print(f"\n{'='*70}")
            print(f"CONNECTION CLOSED ANALYSIS")
            print(f"{'='*70}")
            print(f"Duration: {elapsed:.1f}s")
            print(f"Close Code: {e.code}")
            print(f"Reason: {reason}")
            
            if e.code == 1006:
                print(f"Code 1006 = Abnormal Closure (no close frame, likely timeout/network issue)")
            
            # Detect specific timeouts
            if 59 <= elapsed <= 61:
                print(f"\n⚠️  TIMEOUT AT 60s - NGINX proxy_read_timeout")
            elif 295 <= elapsed <= 305:
                print(f"\n⚠️  TIMEOUT AT 300s - NGINX proxy_read_timeout (5min)")
            elif 345 <= elapsed <= 355:
                print(f"\n⚠️  TIMEOUT AT 350s - NLB idle timeout")
            elif 3595 <= elapsed <= 3605:
                print(f"\n⚠️  TIMEOUT AT 3600s - 1 hour timeout")
            elif elapsed > 400:
                print(f"\n✅ Connection lasted {elapsed:.0f}s - Long-lived connection succeeded")
            
            print(f"{'='*70}\n")
        except Exception as e:
            self.log(f"❌ Error: {e}", "other")
        finally:
            self.print_stats()
    
    async def connect_and_send_manual_pings(self, interval=30):
        """Connect and manually send pings at custom intervals"""
        try:
            print(f"🔌 Connecting to {self.url}")
            print(f"🏓 Will manually send PING every {interval}s\n")
            
            async with websockets.connect(
                self.url,
                ping_interval=None,  # Disable automatic pings
                ping_timeout=None
            ) as websocket:
                self.connection_start = datetime.now()
                self.last_activity = self.connection_start
                self.log("✅ Connection established", "other")
                
                # Create tasks for receiving and pinging
                async def receive_loop():
                    async for message in websocket:
                        self.frame_count['text'] += 1
                        try:
                            import json
                            data = json.loads(message)
                            msg_type = data.get('type', 'unknown')
                            self.log(f"TEXT frame - Type: {msg_type}", "text")
                        except:
                            self.log(f"TEXT frame - Length: {len(message)} bytes", "text")
                
                async def ping_loop():
                    while self.running:
                        await asyncio.sleep(interval)
                        try:
                            pong_waiter = await websocket.ping()
                            self.frame_count['ping'] += 1
                            self.log(f"PING sent manually (interval={interval}s)", "ping")
                            await pong_waiter  # Wait for pong response
                            self.frame_count['pong'] += 1
                            self.log(f"PONG received", "pong")
                        except Exception as e:
                            self.log(f"Ping failed: {e}", "other")
                            break
                
                await asyncio.gather(receive_loop(), ping_loop())
                    
        except websockets.exceptions.ConnectionClosed as e:
            elapsed = (datetime.now() - self.connection_start).total_seconds() if self.connection_start else 0
            reason = e.reason if e.reason else "(no reason provided)"
            self.log(f"❌ Connection closed after {elapsed:.1f}s - Code: {e.code}, Reason: {reason}", "close")
            self.frame_count['close'] += 1
            
            print(f"\n{'='*70}")
            print(f"CONNECTION CLOSED ANALYSIS")
            print(f"{'='*70}")
            print(f"Duration: {elapsed:.1f}s")
            print(f"Close Code: {e.code}")
            print(f"Reason: {reason}")
            if e.code == 1006:
                print(f"Code 1006 = Abnormal Closure (no close frame, likely timeout/network issue)")
            print(f"{'='*70}\n")
        except Exception as e:
            self.log(f"❌ Error: {e}", "other")
        finally:
            self.print_stats()
    
    def stop(self):
        """Stop the analyzer gracefully"""
        print("\n🛑 Stopping analyzer...")
        self.running = False

async def main():
    parser = argparse.ArgumentParser(
        description='WebSocket packet analyzer - shows ALL frames including ping/pong',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Test with default ping behavior (20s interval)
  python ws_packet_test.py wss://example.com/ws/echo
  
  # Test with NO pings to see timeout behavior
  python ws_packet_test.py wss://example.com/ws/echo --no-ping
  
  # Test with custom ping interval
  python ws_packet_test.py wss://example.com/ws/stream --manual-ping 30
  
  # Test echo endpoint (no server pushes, pure idle)
  python ws_packet_test.py wss://example.com/ws/echo --no-ping
        """
    )
    
    parser.add_argument('url', help='Full WebSocket URL including path (e.g., wss://example.com/ws/echo)')
    parser.add_argument('--no-ping', action='store_true', 
                       help='Disable automatic pings to test raw timeout behavior')
    parser.add_argument('--manual-ping', type=int, metavar='SECONDS',
                       help='Manually send ping at this interval (disables automatic pings)')
    parser.add_argument('--verbose', '-v', action='store_true',
                       help='Enable verbose logging (shows all websocket library debug logs)')
    
    args = parser.parse_args()
    
    analyzer = WebSocketPacketAnalyzer(args.url, "", verbose=args.verbose)
    
    # Handle Ctrl+C gracefully
    def signal_handler(sig, frame):
        analyzer.stop()
        sys.exit(0)
    
    signal.signal(signal.SIGINT, signal_handler)
    
    print(f"🚀 WebSocket Packet Analyzer")
    print(f"{'='*70}\n")
    
    if args.no_ping:
        await analyzer.connect_with_disabled_pings()
    elif args.manual_ping:
        await analyzer.connect_and_send_manual_pings(args.manual_ping)
    else:
        await analyzer.connect_with_raw_frames()

if __name__ == '__main__':
    asyncio.run(main())
