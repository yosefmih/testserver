import os
import time
from datetime import datetime
from typing import Dict, List

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel

from porter_sandbox_api_client import Client
from porter_sandbox_api_client.api.sandboxes import create_sandbox, get_sandbox, delete_sandbox
from porter_sandbox_api_client.models import SandboxSpec, NetworkingConfig, SandboxSpecEnv

SANDBOX_API_URL = os.environ.get("SANDBOX_API_URL", "http://sandbox-central.kube-system.svc.cluster.local")
WILDCARD_DOMAIN = os.environ.get("WILDCARD_DOMAIN", "sandbox.withporter.run")
JUPYTER_IMAGE = os.environ.get("JUPYTER_IMAGE", "jupyter/scipy-notebook")
TTL_SECONDS = int(os.environ.get("TTL_SECONDS", "3600"))

app = FastAPI(title="Jupyter Sandbox Platform")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

sessions: Dict[str, dict] = {}

client = Client(base_url=SANDBOX_API_URL)


class SessionResponse(BaseModel):
    session_id: str
    jupyter_url: str
    status: str
    created_at: str


class SessionListResponse(BaseModel):
    sessions: List[SessionResponse]


class DeleteResponse(BaseModel):
    success: bool


@app.post("/api/sessions", response_model=SessionResponse)
async def create_session():
    spec = SandboxSpec(
        image=JUPYTER_IMAGE,
        command=["start-notebook.sh"],
        args=[
            "--NotebookApp.token=''",
            "--NotebookApp.password=''",
            "--NotebookApp.allow_origin='*'",
        ],
        networking=NetworkingConfig(
            port=8888,
            wildcard_subdomain=WILDCARD_DOMAIN,
        ),
        ttl_seconds=TTL_SECONDS,
        env=SandboxSpecEnv.from_dict({"JUPYTER_ENABLE_LAB": "yes"}),
    )

    response = create_sandbox.sync(client=client, body=spec)

    if hasattr(response, "id"):
        sandbox_id = response.id
    else:
        raise HTTPException(status_code=500, detail=f"Failed to create sandbox: {response}")

    deadline = time.time() + 60
    status = "creating"
    while time.time() < deadline:
        status_response = get_sandbox.sync(id=sandbox_id, client=client)
        if hasattr(status_response, "phase"):
            status = status_response.phase
            if status == "running":
                break
            elif status in ("failed", "cancelled"):
                raise HTTPException(status_code=500, detail=f"Sandbox failed to start: {status}")
        time.sleep(1)

    jupyter_url = f"https://{sandbox_id}.{WILDCARD_DOMAIN}"
    created_at = datetime.utcnow().isoformat() + "Z"

    sessions[sandbox_id] = {
        "session_id": sandbox_id,
        "jupyter_url": jupyter_url,
        "status": status,
        "created_at": created_at,
    }

    return SessionResponse(
        session_id=sandbox_id,
        jupyter_url=jupyter_url,
        status=status,
        created_at=created_at,
    )


@app.get("/api/sessions", response_model=SessionListResponse)
async def list_sessions():
    updated_sessions = []
    to_remove = []

    for sandbox_id, session in sessions.items():
        try:
            status_response = get_sandbox.sync(id=sandbox_id, client=client)
            if hasattr(status_response, "phase"):
                session["status"] = status_response.phase
                if status_response.phase in ("succeeded", "failed", "cancelled"):
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
        delete_sandbox.sync(id=session_id, client=client)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to delete sandbox: {e}")

    sessions.pop(session_id, None)
    return DeleteResponse(success=True)


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
