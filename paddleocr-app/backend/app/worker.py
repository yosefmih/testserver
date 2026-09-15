import asyncio
import json
import logging
import mimetypes
from dataclasses import dataclass

import httpx

from . import assemble, pdf
from .config import Settings
from .jobs import Chunk, ChunkStatus, Job, JobStatus, JobStore, now
from .ocr import OCRError, PaddleOCRClient, PageResult
from .storage import Storage

log = logging.getLogger(__name__)

RETRY_DELAY_SECONDS = 5


@dataclass
class StoredPage:
    page_number: int
    pruned_result: dict
    markdown: str
    image_keys: list[str]


class Worker:
    def __init__(self, settings: Settings, storage: Storage, store: JobStore, ocr: PaddleOCRClient):
        self._settings = settings
        self._storage = storage
        self._store = store
        self._ocr = ocr
        self._queue: asyncio.Queue[str] = asyncio.Queue()
        self._consumers: list[asyncio.Task] = []

    async def start(self) -> None:
        for job in reversed(self._store.list()):
            if job.is_active():
                await self._requeue(job)
        self._consumers = [
            asyncio.create_task(self._consume(), name=f"ocr-job-consumer-{i}")
            for i in range(self._settings.job_concurrency)
        ]

    async def stop(self) -> None:
        for task in self._consumers:
            task.cancel()
        await asyncio.gather(*self._consumers, return_exceptions=True)

    def enqueue(self, job_id: str) -> None:
        self._queue.put_nowait(job_id)

    async def _requeue(self, job: Job) -> None:
        log.info("job %s was %s at startup, requeuing", job.id, job.status)
        for chunk in job.chunks:
            if chunk.status != ChunkStatus.done:
                chunk.status = ChunkStatus.queued
                chunk.error = None
        job.status = JobStatus.queued
        await self._store.save(job)
        self.enqueue(job.id)

    async def _consume(self) -> None:
        while True:
            job_id = await self._queue.get()
            job = self._store.get(job_id)
            if job is None:
                continue
            try:
                await self._run(job)
            except Exception as exc:
                log.exception("job %s failed", job.id)
                job.status = JobStatus.failed
                job.error = str(exc)[:1000]
                job.finished_at = now()
                await self._store.save(job)

    async def _run(self, job: Job) -> None:
        job.status = JobStatus.running
        job.started_at = now()
        job.finished_at = None
        job.error = None
        await self._store.save(job)
        source = await self._storage.get(job.key("input.pdf"))
        limiter = asyncio.Semaphore(job.concurrency)
        outcomes = await asyncio.gather(
            *(self._run_chunk(job, chunk, source, limiter) for chunk in job.chunks),
            return_exceptions=True,
        )
        failures = [o for o in outcomes if isinstance(o, BaseException)]
        if failures:
            raise RuntimeError(f"{len(failures)} of {len(job.chunks)} chunks failed: {failures[0]}")
        pages = [page for chunk_pages in outcomes for page in chunk_pages]

        job.status = JobStatus.assembling
        await self._store.save(job)
        markdown, method = await self._assemble(job, pages)
        await self._storage.put(job.key("result.md"), markdown.encode(), "text/markdown")
        page_index = [{"page": p.page_number, "markdown": p.markdown, "images": p.image_keys} for p in pages]
        await self._storage.put(job.key("result.pages.json"), json.dumps(page_index).encode(), "application/json")
        images = {}
        for page in pages:
            for key in page.image_keys:
                images[key] = await self._storage.get(job.key(key))
        archive = await asyncio.to_thread(assemble.build_zip, markdown, images)
        await self._storage.put(job.key("result.zip"), archive, "application/zip")

        job.assembled_with = method
        job.status = JobStatus.done
        job.finished_at = now()
        await self._store.save(job)
        log.info("job %s done: %d pages in %.1fs (%s)", job.id, job.pages, job.metrics().elapsed_seconds, method)

    async def _run_chunk(self, job: Job, chunk: Chunk, source: bytes, limiter: asyncio.Semaphore) -> list[StoredPage]:
        if chunk.status == ChunkStatus.done:
            return await self._load_stored_pages(job, chunk)
        async with limiter:
            chunk.status = ChunkStatus.running
            chunk.started_at = now()
            chunk.finished_at = None
            chunk.error = None
            await self._store.save(job)
            try:
                chunk_pdf = await asyncio.to_thread(pdf.extract_pages, source, chunk.first_page, chunk.last_page)
                await self._storage.put(job.key("chunks", str(chunk.index), "input.pdf"), chunk_pdf, "application/pdf")
                results = await self._ocr_with_retries(job, chunk, chunk_pdf)
                if len(results) != chunk.pages:
                    raise OCRError(f"expected {chunk.pages} pages, got {len(results)}")
                stored = await self._store_pages(job, chunk, results)
                chunk.status = ChunkStatus.done
                chunk.finished_at = now()
                await self._store.save(job)
                return stored
            except Exception as exc:
                chunk.status = ChunkStatus.failed
                chunk.finished_at = now()
                chunk.error = str(exc)[:500]
                await self._store.save(job)
                raise

    async def _ocr_with_retries(self, job: Job, chunk: Chunk, chunk_pdf: bytes) -> list[PageResult]:
        while True:
            chunk.attempts += 1
            try:
                return await self._ocr.layout_parsing(chunk_pdf)
            except (OCRError, httpx.HTTPError) as exc:
                if chunk.attempts >= self._settings.ocr_attempts:
                    raise
                log.warning("job %s chunk %d attempt %d failed: %s", job.id, chunk.index, chunk.attempts, exc)
                await self._store.save(job)
                await asyncio.sleep(RETRY_DELAY_SECONDS)

    async def _store_pages(self, job: Job, chunk: Chunk, results: list[PageResult]) -> list[StoredPage]:
        stored = []
        for offset, page in enumerate(results):
            page_number = chunk.first_page + offset
            page = assemble.namespace_images(page_number, page)
            for key, data in page.images.items():
                await self._storage.put(job.key(key), data, mimetypes.guess_type(key)[0] or "image/jpeg")
            stored.append(StoredPage(page_number, page.pruned_result, page.markdown, list(page.images)))
        manifest = [
            {"pageNumber": p.page_number, "prunedResult": p.pruned_result, "markdown": p.markdown, "imageKeys": p.image_keys}
            for p in stored
        ]
        await self._storage.put(job.key("chunks", str(chunk.index), "pages.json"), json.dumps(manifest).encode(), "application/json")
        return stored

    async def _load_stored_pages(self, job: Job, chunk: Chunk) -> list[StoredPage]:
        manifest = json.loads(await self._storage.get(job.key("chunks", str(chunk.index), "pages.json")))
        return [StoredPage(p["pageNumber"], p["prunedResult"], p["markdown"], p["imageKeys"]) for p in manifest]

    async def _assemble(self, job: Job, pages: list[StoredPage]) -> tuple[str, str]:
        if job.restructure:
            try:
                markdown = await self._ocr.restructure_pages([p.pruned_result for p in pages])
                markdown = assemble.relink_images(markdown, [(p.page_number, p.image_keys) for p in pages])
                return markdown, "restructure-pages"
            except (OCRError, httpx.HTTPError) as exc:
                log.warning("job %s: restructure-pages failed (%s), concatenating instead", job.id, exc)
        return assemble.concatenate([p.markdown for p in pages]), "concatenation"
