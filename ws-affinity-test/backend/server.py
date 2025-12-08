import asyncio
import json
import os
import socket
import logging
from pathlib import Path
from aiohttp import web

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

HOSTNAME = socket.gethostname()
websocket_connections: set[web.WebSocketResponse] = set()

STATIC_DIR = Path(__file__).parent / 'static'


async def websocket_handler(request):
    ws = web.WebSocketResponse()
    await ws.prepare(request)

    websocket_connections.add(ws)
    logger.info(f"[WS] New connection. Total: {len(websocket_connections)}")

    await ws.send_json({
        "type": "connected",
        "hostname": HOSTNAME,
        "message": f"Connected to pod: {HOSTNAME}"
    })

    try:
        async for msg in ws:
            if msg.type == web.WSMsgType.TEXT:
                logger.info(f"[WS] Received: {msg.data}")
            elif msg.type == web.WSMsgType.ERROR:
                logger.error(f"[WS] Error: {ws.exception()}")
    finally:
        websocket_connections.discard(ws)
        logger.info(f"[WS] Connection closed. Total: {len(websocket_connections)}")

    return ws


async def send_handler(request):
    try:
        data = await request.json()
        message = data.get("message", "")
    except Exception:
        message = await request.text()

    logger.info(f"[HTTP] Received message: {message}")
    logger.info(f"[HTTP] Broadcasting to {len(websocket_connections)} WebSocket(s)")

    payload = {
        "type": "message",
        "hostname": HOSTNAME,
        "message": message,
        "ws_count": len(websocket_connections)
    }

    for ws in list(websocket_connections):
        try:
            await ws.send_json(payload)
        except Exception as e:
            logger.error(f"[HTTP] Failed to send to WebSocket: {e}")
            websocket_connections.discard(ws)

    return web.json_response({
        "status": "ok",
        "hostname": HOSTNAME,
        "relayed_to": len(websocket_connections)
    })


async def status_handler(request):
    return web.json_response({
        "hostname": HOSTNAME,
        "websocket_connections": len(websocket_connections)
    })


async def index_handler(request):
    return web.FileResponse(STATIC_DIR / 'index.html')


def create_app():
    app = web.Application()
    app.router.add_get('/ws', websocket_handler)
    app.router.add_post('/send', send_handler)
    app.router.add_get('/status', status_handler)
    app.router.add_get('/', index_handler)
    app.router.add_static('/assets', STATIC_DIR / 'assets')
    return app


if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8080))
    logger.info(f"Starting server on port {port}, hostname: {HOSTNAME}")
    logger.info(f"Serving static files from: {STATIC_DIR}")
    web.run_app(create_app(), host='0.0.0.0', port=port)
