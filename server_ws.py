import asyncio
import json
import logging
import os
import socket
import time
from collections import Counter, deque
from datetime import datetime, timezone
from http import HTTPStatus
from urllib.parse import parse_qs, urlsplit

import websockets
from websockets.server import serve
from dotenv import load_dotenv

load_dotenv(".env")

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

HOSTNAME = socket.gethostname()
SERVER_STARTED_AT = datetime.now(timezone.utc).isoformat()

DURATION_BUCKETS = [
    ("lt_1m", 60),
    ("1m_5m", 300),
    ("5m_15m", 900),
    ("15m_60m", 3600),
    ("gte_1h", float("inf")),
]


class ConnectionTracker:
    def __init__(self):
        self.next_id = 0
        self.active = {}
        self.closed = deque(maxlen=1000)
        self.total_opened = 0
        self.close_codes = Counter()
        self.durations = Counter()

    def open(self, path, params, remote):
        self.next_id += 1
        self.total_opened += 1
        record = {
            "conn_id": self.next_id,
            "path": path,
            "params": {k: v[0] for k, v in params.items()},
            "remote": str(remote),
            "connected_at": datetime.now(timezone.utc).isoformat(),
            "connected_monotonic": time.monotonic(),
            "msgs_in": 0,
            "msgs_out": 0,
            "bytes_in": 0,
            "bytes_out": 0,
        }
        self.active[record["conn_id"]] = record
        logger.info(f"[WS] OPEN conn_id={record['conn_id']} path={path} remote={remote} active={len(self.active)}")
        return record

    def close(self, record, close_code, close_reason):
        self.active.pop(record["conn_id"], None)
        duration = time.monotonic() - record.pop("connected_monotonic")
        record["disconnected_at"] = datetime.now(timezone.utc).isoformat()
        record["duration_seconds"] = round(duration, 2)
        record["close_code"] = close_code
        record["close_reason"] = close_reason or ""
        self.closed.append(record)
        self.close_codes[str(close_code)] += 1
        self.durations[self._bucket(duration)] += 1
        logger.info(f"[WS] CLOSE {json.dumps(record)}")

    def _bucket(self, duration):
        for label, upper in DURATION_BUCKETS:
            if duration < upper:
                return label
        return DURATION_BUCKETS[-1][0]

    def snapshot(self):
        now = time.monotonic()
        return {
            "hostname": HOSTNAME,
            "server_started_at": SERVER_STARTED_AT,
            "active_connections": len(self.active),
            "total_opened": self.total_opened,
            "close_codes": dict(self.close_codes),
            "duration_buckets": dict(self.durations),
            "active": [
                {**{k: v for k, v in r.items() if k != "connected_monotonic"},
                 "age_seconds": round(now - r["connected_monotonic"], 2)}
                for r in self.active.values()
            ],
            "recent_closed": list(self.closed)[-50:],
        }


tracker = ConnectionTracker()
chat_room_clients = set()


async def websocket_handler(websocket, path):
    parts = urlsplit(path)
    route = parts.path
    params = parse_qs(parts.query)
    record = tracker.open(route, params, websocket.remote_address)

    handlers = {
        "/ws/echo": handle_echo,
        "/ws/stream": handle_stream,
        "/ws/audio": handle_audio,
        "/ws/chat": handle_chat_room,
    }

    try:
        handler = handlers.get(route)
        if handler is None:
            await websocket.close(4004, f"unknown path {route}")
            return
        await send_json(websocket, record, {
            "type": "welcome",
            "path": route,
            "conn_id": record["conn_id"],
            "hostname": HOSTNAME,
            "server_time": datetime.now(timezone.utc).isoformat(),
        })
        await handler(websocket, record, params)
    except websockets.exceptions.ConnectionClosed:
        pass
    except Exception:
        logger.exception(f"[WS] handler error conn_id={record['conn_id']}")
    finally:
        tracker.close(record, websocket.close_code, websocket.close_reason)


async def send_json(websocket, record, payload):
    data = json.dumps(payload)
    await websocket.send(data)
    record["msgs_out"] += 1
    record["bytes_out"] += len(data)


def param(params, name, cast, default):
    values = params.get(name)
    if not values:
        return default
    try:
        return cast(values[0])
    except (ValueError, TypeError):
        return default


def lifetime_reached(record, lifetime):
    return lifetime > 0 and time.monotonic() - record["connected_monotonic"] >= lifetime


async def handle_echo(websocket, record, params):
    async for message in websocket:
        record["msgs_in"] += 1
        record["bytes_in"] += len(message)
        if isinstance(message, bytes):
            await websocket.send(message)
            record["msgs_out"] += 1
            record["bytes_out"] += len(message)
        else:
            await send_json(websocket, record, {
                "type": "echo",
                "original": message,
                "conn_id": record["conn_id"],
                "hostname": HOSTNAME,
                "server_time": datetime.now(timezone.utc).isoformat(),
            })


async def handle_stream(websocket, record, params):
    interval = param(params, "interval", float, 2.0)
    padding = param(params, "size", int, 0)
    silent = param(params, "silent", int, 0) == 1
    lifetime = param(params, "lifetime", float, 0.0)

    async def sender():
        counter = 0
        while True:
            if lifetime_reached(record, lifetime):
                await websocket.close(1000, "lifetime reached")
                return
            if silent:
                await asyncio.sleep(min(1.0, lifetime) if lifetime > 0 else 1.0)
                continue
            await asyncio.sleep(interval)
            counter += 1
            await send_json(websocket, record, {
                "type": "tick",
                "counter": counter,
                "conn_id": record["conn_id"],
                "hostname": HOSTNAME,
                "server_time": datetime.now(timezone.utc).isoformat(),
                "age_seconds": round(time.monotonic() - record["connected_monotonic"], 2),
                "padding": "x" * padding,
            })

    sender_task = asyncio.create_task(sender())
    try:
        async for message in websocket:
            record["msgs_in"] += 1
            record["bytes_in"] += len(message)
    finally:
        sender_task.cancel()


async def handle_audio(websocket, record, params):
    frame_ms = param(params, "frame_ms", int, 20)
    frame_bytes = param(params, "frame_bytes", int, 640)
    lifetime = param(params, "lifetime", float, 0.0)
    frame = os.urandom(frame_bytes)

    async def sender():
        while True:
            if lifetime_reached(record, lifetime):
                await websocket.close(1000, "lifetime reached")
                return
            await asyncio.sleep(frame_ms / 1000)
            await websocket.send(frame)
            record["msgs_out"] += 1
            record["bytes_out"] += frame_bytes

    sender_task = asyncio.create_task(sender())
    try:
        async for message in websocket:
            record["msgs_in"] += 1
            record["bytes_in"] += len(message)
    finally:
        sender_task.cancel()


async def handle_chat_room(websocket, record, params):
    chat_room_clients.add(websocket)
    try:
        websockets.broadcast(chat_room_clients, json.dumps({
            "type": "system",
            "message": f"conn {record['conn_id']} joined",
            "participants": len(chat_room_clients),
            "hostname": HOSTNAME,
        }))
        async for message in websocket:
            record["msgs_in"] += 1
            record["bytes_in"] += len(message)
            websockets.broadcast(chat_room_clients, json.dumps({
                "type": "chat",
                "conn_id": record["conn_id"],
                "message": message if isinstance(message, str) else "<binary>",
                "hostname": HOSTNAME,
                "server_time": datetime.now(timezone.utc).isoformat(),
            }))
    finally:
        chat_room_clients.discard(websocket)


async def process_request(path, request_headers):
    if request_headers.get("Upgrade", "").lower() == "websocket":
        return None
    route = urlsplit(path).path
    if route in ("/health", "/healthz"):
        return HTTPStatus.OK, [("Content-Type", "text/plain")], b"ok\n"
    if route == "/stats":
        body = json.dumps(tracker.snapshot(), indent=2).encode()
        return HTTPStatus.OK, [("Content-Type", "application/json")], body
    if route == "/":
        body = json.dumps({
            "hostname": HOSTNAME,
            "http_endpoints": ["/health", "/stats"],
            "ws_endpoints": {
                "/ws/echo": "echoes text (as json envelope) and binary (raw)",
                "/ws/stream": "periodic json ticks; params: interval, size, silent, lifetime",
                "/ws/audio": "binary frames at audio cadence; params: frame_ms, frame_bytes, lifetime",
                "/ws/chat": "broadcast room",
            },
        }, indent=2).encode()
        return HTTPStatus.OK, [("Content-Type", "application/json")], body
    return HTTPStatus.NOT_FOUND, [("Content-Type", "text/plain")], b"not found\n"


async def main():
    port = int(os.environ.get("WS_PORT", 8080))
    ping_interval = float(os.environ["WS_PING_INTERVAL"]) if os.environ.get("WS_PING_INTERVAL") else None
    ping_timeout = float(os.environ["WS_PING_TIMEOUT"]) if os.environ.get("WS_PING_TIMEOUT") else None

    logger.info(f"Starting WebSocket server on port {port} (hostname={HOSTNAME})")
    logger.info(f"Protocol pings: interval={ping_interval} timeout={ping_timeout} (unset = disabled, so idle-timeout tests stay pure)")

    async with serve(
        websocket_handler,
        "0.0.0.0",
        port,
        ping_interval=ping_interval,
        ping_timeout=ping_timeout,
        process_request=process_request,
        max_size=2 ** 22,
    ):
        await asyncio.Future()


if __name__ == '__main__':
    asyncio.run(main())
