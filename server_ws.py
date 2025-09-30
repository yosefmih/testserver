import asyncio
import websockets
from websockets.server import serve
import json
import logging
import socket
import random
import os
from datetime import datetime
from dotenv import load_dotenv

load_dotenv(".env", override=True)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

HOSTNAME = socket.gethostname()

class WSMetrics:
    def __init__(self):
        self.connections = 0
        self.messages_sent = 0
        self.messages_received = 0
        self.connections_by_path = {}

metrics = WSMetrics()

chat_room_clients = set()

async def websocket_handler(websocket, path):
    client_id = id(websocket)
    client_address = websocket.remote_address
    logger.info(f"[WS] New connection from {client_address} (id={client_id}, path={path})")
    
    metrics.connections += 1
    metrics.connections_by_path[path] = metrics.connections_by_path.get(path, 0) + 1
    
    heartbeat_task = None
    try:
        if path == "/ws/echo":
            await handle_echo(websocket, client_id)
        elif path == "/ws/stream":
            heartbeat_task = asyncio.create_task(handle_stream(websocket, client_id))
            await handle_stream_client_messages(websocket, client_id)
        elif path == "/ws/chat":
            await handle_chat_room(websocket, client_id)
        else:
            await websocket.send(json.dumps({
                "type": "error",
                "message": f"Unknown path: {path}. Available: /ws/echo, /ws/stream, /ws/chat"
            }))
            await websocket.close()
    except websockets.exceptions.ConnectionClosed as e:
        logger.info(f"[WS] Connection closed for client {client_id}: {e}")
    except Exception as e:
        logger.error(f"[WS] Error handling websocket {client_id}: {e}")
        import traceback
        logger.error(traceback.format_exc())
    finally:
        if heartbeat_task:
            heartbeat_task.cancel()
        metrics.connections -= 1
        metrics.connections_by_path[path] = max(0, metrics.connections_by_path.get(path, 1) - 1)
        logger.info(f"[WS] Client {client_id} disconnected. Active connections: {metrics.connections}")

async def handle_echo(websocket, client_id):
    await websocket.send(json.dumps({
        "type": "welcome",
        "message": "Echo server - messages will be echoed back",
        "client_id": client_id,
        "hostname": HOSTNAME
    }))
    metrics.messages_sent += 1
    
    async for message in websocket:
        metrics.messages_received += 1
        logger.info(f"[WS-ECHO] Received from {client_id}: {message[:100]}")
        
        response = {
            "type": "echo",
            "original": message,
            "timestamp": datetime.now().isoformat(),
            "hostname": HOSTNAME,
            "client_id": client_id
        }
        await websocket.send(json.dumps(response))
        metrics.messages_sent += 1

async def handle_stream(websocket, client_id):
    await websocket.send(json.dumps({
        "type": "welcome",
        "message": "Stream server - you will receive periodic updates",
        "client_id": client_id,
        "hostname": HOSTNAME
    }))
    metrics.messages_sent += 1
    
    counter = 0
    while True:
        await asyncio.sleep(2)
        counter += 1
        
        message = {
            "type": "heartbeat",
            "counter": counter,
            "timestamp": datetime.now().isoformat(),
            "hostname": HOSTNAME,
            "metrics": {
                "active_connections": metrics.connections,
                "random_value": random.randint(1, 100)
            }
        }
        await websocket.send(json.dumps(message))
        metrics.messages_sent += 1

async def handle_stream_client_messages(websocket, client_id):
    async for message in websocket:
        metrics.messages_received += 1
        logger.info(f"[WS-STREAM] Received from {client_id}: {message[:100]}")

async def handle_chat_room(websocket, client_id):
    chat_room_clients.add(websocket)
    try:
        join_message = {
            "type": "system",
            "message": f"Client {client_id} joined the chat",
            "timestamp": datetime.now().isoformat(),
            "hostname": HOSTNAME,
            "participants": len(chat_room_clients)
        }
        
        websockets.broadcast(chat_room_clients, json.dumps(join_message))
        metrics.messages_sent += len(chat_room_clients)
        
        async for message in websocket:
            metrics.messages_received += 1
            logger.info(f"[WS-CHAT] Message from {client_id}: {message[:100]}")
            
            try:
                data = json.loads(message)
                broadcast_message = {
                    "type": "chat",
                    "client_id": client_id,
                    "message": data.get("message", message),
                    "timestamp": datetime.now().isoformat(),
                    "hostname": HOSTNAME
                }
            except json.JSONDecodeError:
                broadcast_message = {
                    "type": "chat",
                    "client_id": client_id,
                    "message": message,
                    "timestamp": datetime.now().isoformat(),
                    "hostname": HOSTNAME
                }
            
            websockets.broadcast(chat_room_clients, json.dumps(broadcast_message))
            metrics.messages_sent += len(chat_room_clients)
    finally:
        chat_room_clients.remove(websocket)
        leave_message = {
            "type": "system",
            "message": f"Client {client_id} left the chat",
            "timestamp": datetime.now().isoformat(),
            "hostname": HOSTNAME,
            "participants": len(chat_room_clients)
        }
        if chat_room_clients:
            websockets.broadcast(chat_room_clients, json.dumps(leave_message))
            metrics.messages_sent += len(chat_room_clients)

async def main():
    port = int(os.environ.get('WS_PORT', 8080))
    
    logger.info(f"Starting WebSocket server on port {port}")
    logger.info(f"Available endpoints: /ws/echo, /ws/stream, /ws/chat")
    logger.info(f"Ping interval: None (disabled for timeout testing)")
    
    async with serve(
        websocket_handler, 
        "0.0.0.0", 
        port,
        ping_interval=None,
        ping_timeout=None
    ):
        await asyncio.Future()

if __name__ == '__main__':
    asyncio.run(main())
