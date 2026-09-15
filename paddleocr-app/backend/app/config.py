import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    port: int
    paddleocr_url: str
    ocr_timeout_seconds: float
    ocr_attempts: int
    s3_bucket: str
    s3_prefix: str
    local_data_dir: str
    default_chunk_pages: int
    default_concurrency: int
    job_concurrency: int
    restructure_pages: bool
    max_upload_bytes: int


def load_settings() -> Settings:
    env = os.environ
    return Settings(
        port=int(env.get("PORT", "8080")),
        paddleocr_url=env.get("PADDLEOCR_URL", "http://localhost:8118"),
        ocr_timeout_seconds=float(env.get("OCR_TIMEOUT_SECONDS", "900")),
        ocr_attempts=int(env.get("OCR_ATTEMPTS", "3")),
        s3_bucket=env.get("S3_BUCKET", ""),
        s3_prefix=env.get("S3_PREFIX", "paddleocr-app"),
        local_data_dir=env.get("LOCAL_DATA_DIR", "./data"),
        default_chunk_pages=int(env.get("DEFAULT_CHUNK_PAGES", "50")),
        default_concurrency=int(env.get("DEFAULT_CONCURRENCY", "2")),
        job_concurrency=int(env.get("JOB_CONCURRENCY", "1")),
        restructure_pages=env.get("RESTRUCTURE_PAGES", "true").lower() in ("1", "true", "yes"),
        max_upload_bytes=int(env.get("MAX_UPLOAD_BYTES", str(512 * 1024 * 1024))),
    )
