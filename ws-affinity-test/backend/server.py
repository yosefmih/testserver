import asyncio
import io
import json
import os
import signal
import socket
import logging
import uuid
import wave
import struct
import math
from pathlib import Path
from aiohttp import web

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

HOSTNAME = socket.gethostname()
STATIC_DIR = Path(__file__).parent / 'static'

# Global state
sessions: dict[str, set[web.WebSocketResponse]] = {}
voice_calls: dict[str, web.WebSocketResponse] = {}
shutdown_event = asyncio.Event()
accepting_new_connections = True


def get_or_create_session_id(request) -> tuple[str, bool]:
    session_id = request.cookies.get('SESSION_ID')
    if session_id:
        return session_id, False
    return str(uuid.uuid4()), True


def generate_robotic_speech(text: str, sample_rate: int = 16000) -> bytes:
    """
    Generate robotic speech using mathematical synthesis.
    This creates a simple "speaking" effect using frequency modulation.
    Inspired by 6.003 Signals and Systems!
    """
    # Parameters for robotic voice
    base_freq = 150  # Base frequency in Hz (like a robot voice)
    words = text.split()

    audio_data = []

    for word in words:
        # Each character contributes to the sound
        word_samples = []
        for i, char in enumerate(word.lower()):
            if char.isalpha():
                # Map character to frequency offset (a=0, z=25)
                char_offset = ord(char) - ord('a')
                freq = base_freq + char_offset * 8  # Vary frequency by character

                # Duration based on character (vowels longer)
                duration = 0.12 if char in 'aeiou' else 0.08
                num_samples = int(sample_rate * duration)

                for j in range(num_samples):
                    t = j / sample_rate
                    # Add some frequency modulation for robotic effect
                    mod = 1 + 0.1 * math.sin(2 * math.pi * 5 * t)  # 5Hz tremolo
                    # Generate sample with harmonics
                    sample = 0.5 * math.sin(2 * math.pi * freq * mod * t)
                    sample += 0.25 * math.sin(2 * math.pi * freq * 2 * mod * t)  # 2nd harmonic
                    sample += 0.125 * math.sin(2 * math.pi * freq * 3 * mod * t)  # 3rd harmonic

                    # Apply envelope (attack/decay)
                    envelope = min(j / (num_samples * 0.1), 1.0) * min((num_samples - j) / (num_samples * 0.1), 1.0)
                    word_samples.append(int(sample * envelope * 32767 * 0.5))

        audio_data.extend(word_samples)
        # Add pause between words
        audio_data.extend([0] * int(sample_rate * 0.15))

    # Convert to bytes (16-bit PCM)
    audio_bytes = struct.pack(f'<{len(audio_data)}h', *audio_data)

    # Wrap in WAV format
    wav_buffer = io.BytesIO()
    with wave.open(wav_buffer, 'wb') as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)  # 16-bit
        wav_file.setframerate(sample_rate)
        wav_file.writeframes(audio_bytes)

    return wav_buffer.getvalue()


async def websocket_handler(request):
    if not accepting_new_connections:
        return web.Response(status=503, text="Server shutting down")

    session_id, is_new = get_or_create_session_id(request)
    ws = web.WebSocketResponse()
    if is_new:
        ws.set_cookie('SESSION_ID', session_id, max_age=172800, path='/')
    await ws.prepare(request)

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


async def voice_handler(request):
    """Handle voice synthesis WebSocket - streams robotic TTS audio."""
    if not accepting_new_connections:
        return web.Response(status=503, text="Server shutting down")

    session_id, _ = get_or_create_session_id(request)
    ws = web.WebSocketResponse()
    await ws.prepare(request)

    voice_calls[session_id] = ws
    call_start = asyncio.get_event_loop().time()

    logger.info(f"[VOICE] Call started. session_id={session_id} active_calls={len(voice_calls)}")

    await ws.send_json({
        "type": "call_started",
        "hostname": HOSTNAME,
        "session_id": session_id,
        "message": "Voice call connected"
    })

    try:
        async for msg in ws:
            if shutdown_event.is_set():
                await ws.send_json({
                    "type": "shutdown_warning",
                    "hostname": HOSTNAME,
                    "message": "Server shutting down - call may be interrupted"
                })

            if msg.type == web.WSMsgType.TEXT:
                data = json.loads(msg.data)

                if data.get("action") == "speak":
                    text = data.get("text", "Hello, I am a robot.")
                    logger.info(f"[VOICE] Synthesizing: {text[:50]}...")

                    # Generate robotic speech
                    audio_wav = generate_robotic_speech(text)

                    # Stream audio in chunks (simulate real-time)
                    chunk_size = 4096
                    total_chunks = len(audio_wav) // chunk_size + 1

                    for i in range(0, len(audio_wav), chunk_size):
                        if shutdown_event.is_set():
                            await ws.send_json({
                                "type": "interrupted",
                                "hostname": HOSTNAME,
                                "message": "Audio interrupted - server shutting down",
                                "chunks_sent": i // chunk_size,
                                "total_chunks": total_chunks
                            })
                            break

                        chunk = audio_wav[i:i + chunk_size]
                        await ws.send_bytes(chunk)

                        # Small delay to simulate real-time streaming
                        await asyncio.sleep(0.05)
                    else:
                        # Completed successfully
                        await ws.send_json({
                            "type": "speech_complete",
                            "hostname": HOSTNAME,
                            "message": f"Finished speaking: {text[:30]}...",
                            "duration_ms": int((asyncio.get_event_loop().time() - call_start) * 1000)
                        })

                elif data.get("action") == "ping":
                    call_duration = asyncio.get_event_loop().time() - call_start
                    await ws.send_json({
                        "type": "pong",
                        "hostname": HOSTNAME,
                        "call_duration_s": round(call_duration, 1),
                        "shutdown_pending": shutdown_event.is_set()
                    })

            elif msg.type == web.WSMsgType.ERROR:
                logger.error(f"[VOICE] Error: {ws.exception()}")

    finally:
        call_duration = asyncio.get_event_loop().time() - call_start
        del voice_calls[session_id]
        logger.info(f"[VOICE] Call ended. session_id={session_id} duration={call_duration:.1f}s active_calls={len(voice_calls)}")

    return ws


async def narrate_handler(request):
    """HTTP endpoint to trigger voice narration - tests session affinity!"""
    session_id = request.cookies.get('SESSION_ID')

    try:
        data = await request.json()
        text = data.get("text", "")
    except Exception:
        text = await request.text()

    logger.info(f"[NARRATE] Received for session_id={session_id}: {text[:50]}...")

    # Check if this session has an active voice call on THIS pod
    voice_ws = voice_calls.get(session_id)

    if not voice_ws:
        logger.warning(f"[NARRATE] No voice call found for session {session_id} on this pod")
        return web.json_response({
            "status": "error",
            "hostname": HOSTNAME,
            "session_id": session_id,
            "error": "No active voice call on this pod",
            "hint": "Voice WebSocket may be on a different pod - affinity issue?"
        }, status=404)

    # Generate and stream audio
    try:
        audio_wav = generate_robotic_speech(text)
        chunk_size = 4096
        total_chunks = len(audio_wav) // chunk_size + 1
        chunks_sent = 0

        for i in range(0, len(audio_wav), chunk_size):
            if shutdown_event.is_set():
                await voice_ws.send_json({
                    "type": "interrupted",
                    "hostname": HOSTNAME,
                    "message": "Audio interrupted - server shutting down",
                    "chunks_sent": chunks_sent,
                    "total_chunks": total_chunks
                })
                break

            chunk = audio_wav[i:i + chunk_size]
            await voice_ws.send_bytes(chunk)
            chunks_sent += 1
            await asyncio.sleep(0.05)  # Simulate real-time
        else:
            await voice_ws.send_json({
                "type": "speech_complete",
                "hostname": HOSTNAME,
                "message": f"Finished speaking: {text[:30]}...",
                "source": "http_narrate"
            })

        return web.json_response({
            "status": "ok",
            "hostname": HOSTNAME,
            "session_id": session_id,
            "text_length": len(text),
            "chunks_sent": chunks_sent,
            "total_chunks": total_chunks
        })

    except Exception as e:
        logger.error(f"[NARRATE] Error streaming audio: {e}")
        return web.json_response({
            "status": "error",
            "hostname": HOSTNAME,
            "error": str(e)
        }, status=500)


async def send_handler(request):
    session_id = request.cookies.get('SESSION_ID')

    try:
        data = await request.json()
        message = data.get("message", "")
    except Exception:
        message = await request.text()

    logger.info(f"[HTTP] Received message for session_id={session_id}: {message}")

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
        "total_websockets": total_ws,
        "active_voice_calls": len(voice_calls),
        "shutdown_pending": shutdown_event.is_set()
    })


async def index_handler(request):
    return web.FileResponse(STATIC_DIR / 'index.html')


async def graceful_shutdown(app):
    """Handle graceful shutdown - warn clients, drain connections."""
    global accepting_new_connections

    logger.info("[SHUTDOWN] Initiating graceful shutdown...")
    accepting_new_connections = False
    shutdown_event.set()

    # Warn all connected clients
    warning_payload = {
        "type": "shutdown_warning",
        "hostname": HOSTNAME,
        "message": "Server shutting down in 30 seconds"
    }

    # Warn regular WebSocket sessions
    for session_id, ws_set in sessions.items():
        for ws in list(ws_set):
            try:
                await ws.send_json(warning_payload)
            except Exception:
                pass

    # Warn voice calls
    for session_id, ws in voice_calls.items():
        try:
            await ws.send_json({
                **warning_payload,
                "message": "CALL WILL BE INTERRUPTED - Server shutting down"
            })
        except Exception:
            pass

    logger.info(f"[SHUTDOWN] Warned {len(sessions)} sessions and {len(voice_calls)} voice calls")

    # Wait for grace period (let ongoing calls complete)
    grace_period = int(os.environ.get('SHUTDOWN_GRACE_SECONDS', 10))
    logger.info(f"[SHUTDOWN] Waiting {grace_period}s for connections to drain...")
    await asyncio.sleep(grace_period)

    # Force close remaining connections
    for session_id, ws_set in sessions.items():
        for ws in list(ws_set):
            try:
                await ws.close(code=1012, message=b"Server restarting")
            except Exception:
                pass

    for session_id, ws in voice_calls.items():
        try:
            await ws.close(code=1012, message=b"Server restarting")
        except Exception:
            pass

    logger.info("[SHUTDOWN] Shutdown complete")


def create_app():
    app = web.Application()
    app.on_shutdown.append(graceful_shutdown)

    app.router.add_get('/ws', websocket_handler)
    app.router.add_get('/voice', voice_handler)
    app.router.add_post('/send', send_handler)
    app.router.add_post('/narrate', narrate_handler)
    app.router.add_get('/status', status_handler)
    app.router.add_get('/', index_handler)
    app.router.add_static('/assets', STATIC_DIR / 'assets')
    return app


if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8080))
    logger.info(f"Starting server on port {port}, hostname: {HOSTNAME}")
    logger.info(f"Serving static files from: {STATIC_DIR}")
    web.run_app(create_app(), host='0.0.0.0', port=port)
