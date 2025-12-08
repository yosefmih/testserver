import asyncio
import json
import os
import socket
import logging
import uuid
from pathlib import Path
from aiohttp import web

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

HOSTNAME = socket.gethostname()
STATIC_DIR = Path(__file__).parent / 'static'

# Store WebSocket connections by session_id
# session_id -> set of WebSocketResponse
sessions: dict[str, set[web.WebSocketResponse]] = {}


def get_or_create_session_id(request) -> tuple[str, bool]:
    """Get SESSION_ID from cookie or create a new one."""
    session_id = request.cookies.get('SESSION_ID')
    if session_id:
        return session_id, False
    return str(uuid.uuid4()), True


async def websocket_handler(request):
    session_id, is_new = get_or_create_session_id(request)

    ws = web.WebSocketResponse()
    # Set cookie on WebSocket upgrade response if new session
    if is_new:
        ws.set_cookie('SESSION_ID', session_id, max_age=172800, path='/')
    await ws.prepare(request)

    # Register this WebSocket under the session
    if session_id not in sessions:
        sessions[session_id] = set()
    sessions[session_id].add(ws)

    logger.info(f"[WS] New connection. session_id={session_id} total_sessions={len(sessions)}")

    await ws.send_json({
        "type": "connected",
        "hostname": HOSTNAME,
        "session_id": session_id,
        "message": f"Connected to pod: {HOSTNAME}"
    })

    try:
        async for msg in ws:
            if msg.type == web.WSMsgType.TEXT:
                logger.info(f"[WS] Received from {session_id}: {msg.data}")
            elif msg.type == web.WSMsgType.ERROR:
                logger.error(f"[WS] Error: {ws.exception()}")
    finally:
        sessions[session_id].discard(ws)
        if not sessions[session_id]:
            del sessions[session_id]
        logger.info(f"[WS] Connection closed. session_id={session_id} total_sessions={len(sessions)}")

    return ws


async def send_handler(request):
    session_id = request.cookies.get('SESSION_ID')

    try:
        data = await request.json()
        message = data.get("message", "")
    except Exception:
        message = await request.text()

    logger.info(f"[HTTP] Received message for session_id={session_id}: {message}")

    # Get WebSockets for this session
    ws_set = sessions.get(session_id, set())
    logger.info(f"[HTTP] Broadcasting to {len(ws_set)} WebSocket(s) for session {session_id}")

    payload = {
        "type": "message",
        "hostname": HOSTNAME,
        "session_id": session_id,
        "message": message,
        "ws_count": len(ws_set)
    }

    sent_count = 0
    for ws in list(ws_set):
        try:
            await ws.send_json(payload)
            sent_count += 1
        except Exception as e:
            logger.error(f"[HTTP] Failed to send to WebSocket: {e}")
            ws_set.discard(ws)

    return web.json_response({
        "status": "ok",
        "hostname": HOSTNAME,
        "session_id": session_id,
        "relayed_to": sent_count
    })


async def status_handler(request):
    total_ws = sum(len(ws_set) for ws_set in sessions.values())
    return web.json_response({
        "hostname": HOSTNAME,
        "total_sessions": len(sessions),
        "total_websockets": total_ws
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
