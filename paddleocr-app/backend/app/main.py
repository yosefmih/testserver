import logging
import mimetypes
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles

from .config import Settings, load_settings
from .jobs import Job, JobStore, new_job
from .ocr import PaddleOCRClient
from .pdf import count_pages
from .storage import open_storage
from .worker import Worker

STATIC_DIR = Path(__file__).parent / "static"

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = load_settings()
    storage = open_storage(settings)
    store = JobStore(storage)
    await store.load()
    ocr = PaddleOCRClient(settings.paddleocr_url, settings.ocr_timeout_seconds)
    worker = Worker(settings, storage, store, ocr)
    await worker.start()
    app.state.settings = settings
    app.state.storage = storage
    app.state.store = store
    app.state.ocr = ocr
    app.state.worker = worker
    yield
    await worker.stop()
    await ocr.aclose()


app = FastAPI(title="PaddleOCR document service", lifespan=lifespan)


@app.get("/api/healthz")
async def healthz(request: Request) -> dict:
    return {"ok": True, "ocrReady": await request.app.state.ocr.ready()}


@app.get("/api/config")
async def config(request: Request) -> dict:
    settings: Settings = request.app.state.settings
    return {
        "paddleocrUrl": settings.paddleocr_url,
        "storage": request.app.state.storage.describe(),
        "defaultChunkPages": settings.default_chunk_pages,
        "defaultConcurrency": settings.default_concurrency,
        "defaultRestructure": settings.restructure_pages,
        "maxUploadBytes": settings.max_upload_bytes,
    }


@app.get("/api/jobs")
async def list_jobs(request: Request) -> list[dict]:
    return [job_view(job) for job in request.app.state.store.list()]


@app.post("/api/jobs", status_code=201)
async def create_job(
    request: Request,
    pdf: UploadFile = File(...),
    chunkPages: int = Form(...),
    concurrency: int = Form(...),
    restructure: bool = Form(False),
) -> dict:
    settings: Settings = request.app.state.settings
    if chunkPages < 1 or concurrency < 1:
        raise HTTPException(400, "chunkPages and concurrency must be at least 1")
    data = await pdf.read()
    if len(data) > settings.max_upload_bytes:
        raise HTTPException(413, f"file exceeds {settings.max_upload_bytes} bytes")
    try:
        pages = count_pages(data)
    except Exception as exc:
        raise HTTPException(400, f"not a readable PDF: {exc}") from exc
    if pages == 0:
        raise HTTPException(400, "PDF has no pages")
    job = new_job(pdf.filename or "document.pdf", pages, chunkPages, concurrency, restructure)
    await request.app.state.storage.put(job.key("input.pdf"), data, "application/pdf")
    await request.app.state.store.save(job)
    request.app.state.worker.enqueue(job.id)
    return job_view(job)


@app.get("/api/jobs/{job_id}")
async def get_job(request: Request, job_id: str) -> dict:
    return job_view(find_job(request, job_id))


@app.delete("/api/jobs/{job_id}", status_code=204)
async def delete_job(request: Request, job_id: str) -> Response:
    job = find_job(request, job_id)
    if job.is_active():
        raise HTTPException(409, "job is still running")
    await request.app.state.store.delete(job.id)
    return Response(status_code=204)


@app.get("/api/jobs/{job_id}/result.md")
async def result_markdown(request: Request, job_id: str) -> Response:
    job = find_job(request, job_id)
    data = await read_result(request, job, "result.md")
    return Response(data, media_type="text/markdown; charset=utf-8")


@app.get("/api/jobs/{job_id}/result.zip")
async def result_zip(request: Request, job_id: str) -> Response:
    job = find_job(request, job_id)
    data = await read_result(request, job, "result.zip")
    filename = Path(job.file_name).stem + ".zip"
    return Response(
        data,
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@app.get("/api/jobs/{job_id}/files/{key:path}")
async def job_file(request: Request, job_id: str, key: str) -> Response:
    job = find_job(request, job_id)
    if ".." in key.split("/") or key.startswith("/"):
        raise HTTPException(400, "invalid key")
    storage = request.app.state.storage
    if not await storage.exists(job.key(key)):
        raise HTTPException(404, "no such file")
    media_type = mimetypes.guess_type(key)[0] or "application/octet-stream"
    return Response(await storage.get(job.key(key)), media_type=media_type)


def find_job(request: Request, job_id: str) -> Job:
    job = request.app.state.store.get(job_id)
    if job is None:
        raise HTTPException(404, "no such job")
    return job


async def read_result(request: Request, job: Job, name: str) -> bytes:
    if job.status != "done":
        raise HTTPException(409, f"job is {job.status}")
    return await request.app.state.storage.get(job.key(name))


def job_view(job: Job) -> dict:
    view = job.model_dump(mode="json")
    view["metrics"] = job.metrics().model_dump()
    return view


if STATIC_DIR.is_dir():
    app.mount("/assets", StaticFiles(directory=STATIC_DIR / "assets"), name="assets")

    @app.get("/{path:path}", include_in_schema=False)
    async def spa(path: str) -> FileResponse:
        candidate = STATIC_DIR / path
        if path and candidate.is_file():
            return FileResponse(candidate)
        return FileResponse(STATIC_DIR / "index.html")
