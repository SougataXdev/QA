"""
main.py — FastAPI app, routes, and job endpoints.

POST /process → Enqueues extraction job, returns job_id + poll_url.
GET /jobs/{job_id} → Returns current job status/results.
GET /health → Health check.

Error handling:
  - CORRUPTED_PDF / NO_TEXT_LAYER → 400 on preflight (in worker)
  - JOB_NOT_FOUND → 404
  - All pipeline errors handled in worker, not here.
"""

from __future__ import annotations

import json
import logging
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, File, HTTPException, Query, UploadFile
from fastapi.middleware.cors import CORSMiddleware

from pdf_engine.config import REDIS_URL
from pdf_engine.models import JobCreatedResponse, JobResponse

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────
# Lifespan
# ─────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup / shutdown lifecycle."""
    logger.info("PDF QA Extraction Engine starting up")
    yield
    # Shutdown: close Redis pool if it was initialized
    global _redis_pool
    if _redis_pool is not None:
        await _redis_pool.close()
        _redis_pool = None
    logger.info("PDF QA Extraction Engine shut down")


# ─────────────────────────────────────────────
# App
# ─────────────────────────────────────────────

app = FastAPI(
    title="PDF QA Extraction Engine",
    description=(
        "Production-grade PDF extraction and comparison engine. "
        "Extracts perfectly ordered, clean text from multi-column corporate PDFs "
        "and compares it mathematically against live DOM text."
    ),
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ─────────────────────────────────────────────
# Redis helper (lazy init)
# ─────────────────────────────────────────────

_redis_pool = None


async def _get_redis():
    """Lazy-init Redis connection."""
    global _redis_pool
    if _redis_pool is None:
        import redis.asyncio as aioredis
        _redis_pool = aioredis.from_url(REDIS_URL, decode_responses=True)
    return _redis_pool


async def _get_arq_pool():
    """Get ARQ redis pool for job enqueue."""
    from arq import create_pool
    from arq.connections import RedisSettings

    url = REDIS_URL.replace("redis://", "")
    parts = url.split(":")
    host = parts[0] if parts[0] else "localhost"
    port = int(parts[1]) if len(parts) > 1 else 6379
    return await create_pool(RedisSettings(host=host, port=port))


# ─────────────────────────────────────────────
# Routes
# ─────────────────────────────────────────────

@app.get("/health")
async def health():
    """Health check endpoint."""
    return {"status": "healthy", "engine": "pdf-qa-extraction", "version": "1.0.0"}


@app.post("/process", status_code=202, response_model=JobCreatedResponse)
async def process(
    file: UploadFile = File(..., description="PDF file to process"),
    url: str = Query(..., description="Target URL to scrape for DOM comparison"),
    crop_top: float = Query(0.0, ge=0.0, le=1.0, description="Top crop ratio"),
    crop_bottom: float = Query(1.0, ge=0.0, le=1.0, description="Bottom crop ratio"),
    crop_left: float = Query(0.0, ge=0.0, le=1.0, description="Left crop ratio"),
    crop_right: float = Query(1.0, ge=0.0, le=1.0, description="Right crop ratio"),
    page_range_start: int = Query(0, ge=0, description="First page (0-indexed, inclusive)"),
    page_range_end: int = Query(-1, description="Last page (0-indexed, exclusive). -1 = all."),
):
    """
    Submit a PDF for extraction and comparison against a live URL.

    Returns a job_id for polling results. The job runs asynchronously
    via the ARQ worker.
    """
    job_id = str(uuid.uuid4())
    file_bytes = await file.read()

    if not file_bytes:
        raise HTTPException(status_code=400, detail="Empty file uploaded")

    # Validate file looks like a PDF
    if not file_bytes[:5] == b'%PDF-':
        raise HTTPException(
            status_code=400,
            detail="Uploaded file does not appear to be a valid PDF",
        )

    # Validate crop values
    if crop_top >= crop_bottom:
        raise HTTPException(
            status_code=400,
            detail=f"crop_top ({crop_top}) must be less than crop_bottom ({crop_bottom})",
        )
    if crop_left >= crop_right:
        raise HTTPException(
            status_code=400,
            detail=f"crop_left ({crop_left}) must be less than crop_right ({crop_right})",
        )

    # Store initial job status
    redis = await _get_redis()
    await redis.set(
        f"job:{job_id}",
        json.dumps({"status": "QUEUED", "progress": 0}),
    )

    # Enqueue job
    try:
        arq_pool = await _get_arq_pool()
        await arq_pool.enqueue_job(
            "run_pipeline",
            job_id,
            file_bytes,
            url,
            crop_top,
            crop_bottom,
            crop_left,
            crop_right,
            page_range_start,
            page_range_end,
        )
        await arq_pool.close()
    except Exception as exc:
        logger.error("Failed to enqueue job %s: %s", job_id, exc)
        await redis.set(
            f"job:{job_id}",
            json.dumps({
                "status": "FAILED",
                "error": f"QUEUE_ERROR: {str(exc)}",
            }),
        )
        raise HTTPException(
            status_code=503,
            detail="Job queue unavailable. Please try again later.",
        )

    logger.info("Job %s queued: url=%s pages=%d-%d", job_id, url, page_range_start, page_range_end)

    return JobCreatedResponse(
        job_id=job_id,
        poll_url=f"/jobs/{job_id}",
    )


@app.get("/jobs/{job_id}")
async def get_job(job_id: str):
    """
    Poll job status and results.

    Returns the current state of the job. When complete,
    includes full comparison results, boilerplate list,
    stitch flags, and stitch log.
    """
    redis = await _get_redis()
    data = await redis.get(f"job:{job_id}")

    if not data:
        raise HTTPException(status_code=404, detail="Job not found")

    return json.loads(data)

