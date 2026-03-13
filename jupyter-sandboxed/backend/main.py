import os
import re
import time
import logging
from datetime import datetime
from typing import Dict, List, Optional

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel

from porter_sandbox_api_client import Client
from porter_sandbox_api_client.api.sandboxes import create_sandbox, get_sandbox, delete_sandbox, get_sandbox_logs
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

LOG_PREFIX_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T[\d:.]+Z\s+\w+\s+\w+\s+")


class CreateSessionRequest(BaseModel):
    iam_role_arn: Optional[str] = None
    domain: Optional[str] = None


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


class LogsResponse(BaseModel):
    logs: List[str]


@app.post("/api/sessions", response_model=SessionResponse)
async def create_session(body: Optional[CreateSessionRequest] = None):
    iam_role_arn = (body.iam_role_arn if body and body.iam_role_arn else DEFAULT_IAM_ROLE_ARN) or None
    domain = (body.domain if body and body.domain else None)
    logger.debug("Creating session with iam_role_arn=%s, domain=%s, image=%s, namespace=%s", iam_role_arn, domain, JUPYTER_IMAGE, SANDBOX_NAMESPACE)

    networking = NetworkingConfig(port=8888)
    if domain:
        networking = NetworkingConfig(port=8888, domains=[domain])
        logger.debug("Using domain: %s", domain)

    spec = SandboxSpec(
        image=JUPYTER_IMAGE,
        command=["start-notebook.sh"],
        args=[
            "--NotebookApp.token=''",
            "--NotebookApp.password=''",
            "--NotebookApp.allow_origin='*'",
        ],
        networking=networking,
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

    if domain:
        jupyter_url = f"https://{domain}/lab"
    else:
        jupyter_url = f"http://sandbox-{sandbox_id}-svc.{SANDBOX_NAMESPACE}.svc.cluster.local:8888/lab"

    logger.info("Session ready: sandbox_id=%s, jupyter_url=%s", sandbox_id, jupyter_url)
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


@app.get("/api/sessions/{session_id}/logs", response_model=LogsResponse)
async def get_session_logs(session_id: str):
    if session_id not in sessions:
        raise HTTPException(status_code=404, detail="Session not found")

    try:
        response = get_sandbox_logs.sync(id=session_id, client=sandbox_client)
        raw_lines = response.logs if hasattr(response, "logs") and response.logs else []
        cleaned = [LOG_PREFIX_RE.sub("", line) for line in raw_lines]
        return LogsResponse(logs=cleaned)
    except Exception as e:
        logger.error("Failed to fetch logs for session %s: %s", session_id, e)
        return LogsResponse(logs=[f"Error fetching logs: {e}"])


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
