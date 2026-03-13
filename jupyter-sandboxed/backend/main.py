import asyncio
import os
import time
import logging
from datetime import datetime
from typing import Dict, List, Optional

import httpx
import websockets
from fastapi import FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, Response
from pydantic import BaseModel

from porter_sandbox_api_client import Client
from porter_sandbox_api_client.api.sandboxes import create_sandbox, get_sandbox, delete_sandbox
from porter_sandbox_api_client.models import SandboxSpec, SandboxSpecEnv, NetworkingConfig

LOG_LEVEL = os.environ.get("LOG_LEVEL", "DEBUG").upper()
logging.basicConfig(
    level=getattr(logging, LOG_LEVEL, logging.DEBUG),
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

SANDBOX_API_URL = os.environ.get("SANDBOX_API_URL", "http://sandbox-central.kube-system.svc.cluster.local")
SANDBOX_NAMESPACE = os.environ.get("SANDBOX_NAMESPACE", "default")
JUPYTER_IMAGE = os.environ.get("JUPYTER_IMAGE", "jupyter/scipy-notebook")
TTL_SECONDS = int(os.environ.get("TTL_SECONDS", "3600"))
DEFAULT_IAM_ROLE_ARN = os.environ.get("IAM_ROLE_ARN", "")

app = FastAPI(title="Jupyter Sandbox Platform")

logger.info(
    "Starting Jupyter Sandbox Platform: sandbox_api=%s namespace=%s image=%s ttl=%d log_level=%s",
    SANDBOX_API_URL, SANDBOX_NAMESPACE, JUPYTER_IMAGE, TTL_SECONDS, LOG_LEVEL,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

sessions: Dict[str, dict] = {}

sandbox_client = Client(base_url=SANDBOX_API_URL)

proxy_http_client = httpx.AsyncClient(timeout=30.0)


def sandbox_internal_url(sandbox_id: str) -> str:
    return f"http://sandbox-{sandbox_id}-svc.{SANDBOX_NAMESPACE}.svc.cluster.local:8888"


class CreateSessionRequest(BaseModel):
    iam_role_arn: Optional[str] = None


class SessionResponse(BaseModel):
    session_id: str
    jupyter_url: str
    status: str
    created_at: str
    iam_role_arn: Optional[str] = None


class SessionListResponse(BaseModel):
    sessions: List[SessionResponse]


class DeleteResponse(BaseModel):
    success: bool


@app.post("/api/sessions", response_model=SessionResponse)
async def create_session(body: Optional[CreateSessionRequest] = None):
    iam_role_arn = (body.iam_role_arn if body and body.iam_role_arn else DEFAULT_IAM_ROLE_ARN) or None
    logger.debug("Creating session with iam_role_arn=%s, image=%s, namespace=%s", iam_role_arn, JUPYTER_IMAGE, SANDBOX_NAMESPACE)

    spec = SandboxSpec(
        image=JUPYTER_IMAGE,
        command=["start-notebook.sh"],
        args=[
            "--NotebookApp.token=''",
            "--NotebookApp.password=''",
            "--NotebookApp.allow_origin='*'",
        ],
        networking=NetworkingConfig(port=8888),
        ttl_seconds=TTL_SECONDS,
        env=SandboxSpecEnv.from_dict({"JUPYTER_ENABLE_LAB": "yes"}),
        iam_role_arn=iam_role_arn,
    )

    logger.debug("Sending create_sandbox request to %s", SANDBOX_API_URL)
    response = create_sandbox.sync(client=sandbox_client, body=spec)
    logger.debug("create_sandbox response: %s", response)

    if not hasattr(response, "id"):
        raise HTTPException(status_code=500, detail=f"Failed to create sandbox: {response}")

    sandbox_id = response.id
    logger.info("Sandbox created with id=%s, waiting for running state", sandbox_id)

    deadline = time.time() + 60
    status = "creating"
    while time.time() < deadline:
        status_response = get_sandbox.sync(id=sandbox_id, client=sandbox_client)
        if hasattr(status_response, "phase"):
            phase = status_response.phase
            status = phase.value if hasattr(phase, "value") else str(phase)
            logger.debug("Sandbox %s phase=%s", sandbox_id, status)
            if status == "running":
                break
            elif status in ("failed", "cancelled"):
                raise HTTPException(status_code=500, detail=f"Sandbox failed to start: {status}")
        time.sleep(1)

    jupyter_url = f"/sandbox/{sandbox_id}/lab"
    logger.info("Session ready: sandbox_id=%s, jupyter_url=%s, internal_url=%s", sandbox_id, jupyter_url, sandbox_internal_url(sandbox_id))
    created_at = datetime.utcnow().isoformat() + "Z"

    sessions[sandbox_id] = {
        "session_id": sandbox_id,
        "jupyter_url": jupyter_url,
        "status": status,
        "created_at": created_at,
        "iam_role_arn": iam_role_arn,
    }

    return SessionResponse(
        session_id=sandbox_id,
        jupyter_url=jupyter_url,
        status=status,
        created_at=created_at,
        iam_role_arn=iam_role_arn,
    )


@app.get("/api/sessions", response_model=SessionListResponse)
async def list_sessions():
    updated_sessions = []
    to_remove = []

    for sandbox_id, session in sessions.items():
        try:
            status_response = get_sandbox.sync(id=sandbox_id, client=sandbox_client)
            if hasattr(status_response, "phase"):
                phase = status_response.phase
                session["status"] = phase.value if hasattr(phase, "value") else str(phase)
                if session["status"] in ("succeeded", "failed", "cancelled"):
                    to_remove.append(sandbox_id)
                    continue
            updated_sessions.append(SessionResponse(**session))
        except Exception:
            to_remove.append(sandbox_id)

    for sandbox_id in to_remove:
        sessions.pop(sandbox_id, None)

    return SessionListResponse(sessions=updated_sessions)


@app.delete("/api/sessions/{session_id}", response_model=DeleteResponse)
async def terminate_session(session_id: str):
    if session_id not in sessions:
        raise HTTPException(status_code=404, detail="Session not found")

    try:
        delete_sandbox.sync(id=session_id, client=sandbox_client)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to delete sandbox: {e}")

    sessions.pop(session_id, None)
    return DeleteResponse(success=True)


@app.api_route(
    "/sandbox/{sandbox_id}/{path:path}",
    methods=["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS", "HEAD"],
)
async def proxy_to_sandbox(sandbox_id: str, path: str, request: Request):
    logger.debug("HTTP proxy request: method=%s sandbox_id=%s path=%s query=%s", request.method, sandbox_id, path, request.url.query)
    logger.debug("Known sessions: %s", list(sessions.keys()))

    if sandbox_id not in sessions:
        logger.warning("Session not found for sandbox_id=%s", sandbox_id)
        raise HTTPException(status_code=404, detail="Session not found")

    target_url = f"{sandbox_internal_url(sandbox_id)}/{path}"
    if request.url.query:
        target_url += f"?{request.url.query}"

    logger.debug("Proxying to target_url=%s", target_url)

    body = await request.body()

    headers = dict(request.headers)
    headers.pop("host", None)

    try:
        resp = await proxy_http_client.request(
            method=request.method,
            url=target_url,
            content=body,
            headers=headers,
        )
        logger.debug("Upstream response: status=%d content_length=%d", resp.status_code, len(resp.content))
    except httpx.ConnectError as e:
        logger.error("Failed to connect to sandbox %s at %s: %s", sandbox_id, target_url, e)
        raise HTTPException(status_code=502, detail="Sandbox not reachable")

    response_headers = dict(resp.headers)
    response_headers.pop("transfer-encoding", None)
    response_headers.pop("content-encoding", None)
    response_headers.pop("content-length", None)

    return Response(
        content=resp.content,
        status_code=resp.status_code,
        headers=response_headers,
    )


@app.websocket("/sandbox/{sandbox_id}/{path:path}")
async def proxy_websocket(websocket: WebSocket, sandbox_id: str, path: str):
    logger.debug("WebSocket proxy request: sandbox_id=%s path=%s query=%s", sandbox_id, path, websocket.url.query)

    if sandbox_id not in sessions:
        logger.warning("WebSocket: session not found for sandbox_id=%s", sandbox_id)
        await websocket.close(code=4004)
        return

    await websocket.accept()

    ws_target = sandbox_internal_url(sandbox_id).replace("http://", "ws://")
    ws_url = f"{ws_target}/{path}"
    if websocket.url.query:
        ws_url += f"?{websocket.url.query}"

    logger.debug("WebSocket proxying to %s", ws_url)

    try:
        async with websockets.connect(ws_url) as upstream:

            async def client_to_upstream():
                try:
                    while True:
                        data = await websocket.receive_bytes()
                        await upstream.send(data)
                except WebSocketDisconnect:
                    await upstream.close()

            async def upstream_to_client():
                try:
                    async for message in upstream:
                        if isinstance(message, bytes):
                            await websocket.send_bytes(message)
                        else:
                            await websocket.send_text(message)
                except Exception:
                    await websocket.close()

            await asyncio.gather(client_to_upstream(), upstream_to_client())
    except Exception as e:
        logger.error("WebSocket proxy error for sandbox %s: %s", sandbox_id, e)
        try:
            await websocket.close()
        except Exception:
            pass


@app.get("/health")
async def health():
    return {"status": "healthy"}


static_dir = os.path.join(os.path.dirname(__file__), "..", "static")
if os.path.exists(static_dir):
    app.mount("/assets", StaticFiles(directory=os.path.join(static_dir, "assets")), name="assets")

    @app.get("/")
    async def serve_index():
        return FileResponse(os.path.join(static_dir, "index.html"))

    @app.get("/{full_path:path}")
    async def serve_spa(full_path: str):
        file_path = os.path.join(static_dir, full_path)
        if os.path.exists(file_path) and os.path.isfile(file_path):
            return FileResponse(file_path)
        return FileResponse(os.path.join(static_dir, "index.html"))
