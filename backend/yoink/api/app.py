"""FastAPI application factory with lifespan management."""

import asyncio
import logging
import os
import shutil
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from yoink.api.jobs import JobStore
from yoink.api.worker import ExtractionWorker
from yoink.extractor import LayoutExtractor

logger = logging.getLogger(__name__)

JOB_DATA_DIR = os.environ.get("YOINK_JOB_DATA_DIR", "./job_data")
UPLOAD_DIR = os.environ.get("YOINK_UPLOAD_DIR", "./uploads")
DB_PATH = os.environ.get("YOINK_DB_PATH", "yoink_jobs.db")
CLEANUP_INTERVAL_SECONDS = 3600  # 1 hour


async def _cleanup_loop(job_store: JobStore) -> None:
    """Periodically clean up jobs older than 24 hours."""
    while True:
        try:
            await asyncio.sleep(CLEANUP_INTERVAL_SECONDS)
            old_jobs = await job_store.get_old_job_paths(max_age_hours=24)
            for job in old_jobs:
                ExtractionWorker.cleanup_job_files(job.get("upload_path"), job.get("result_path"))
            count = await job_store.cleanup_old_jobs(max_age_hours=24)
            if count > 0:
                logger.info("Cleanup: removed %d old jobs", count)
        except asyncio.CancelledError:
            break
        except Exception:
            logger.exception("Error in cleanup loop")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage startup/shutdown: load model, init DB, start worker."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )

    # Ensure directories exist
    Path(JOB_DATA_DIR).mkdir(parents=True, exist_ok=True)
    Path(UPLOAD_DIR).mkdir(parents=True, exist_ok=True)

    # Init job store
    job_store = JobStore(db_path=DB_PATH)
    await job_store.init()

    # Load YOLO model (singleton)
    logger.info("Loading YOLO model...")
    extractor = LayoutExtractor()
    logger.info("YOLO model loaded")

    # Start worker
    worker = ExtractionWorker(
        job_store=job_store,
        extractor=extractor,
        output_base_dir=JOB_DATA_DIR,
    )
    worker.start()

    # Start cleanup loop
    cleanup_task = asyncio.create_task(_cleanup_loop(job_store))

    # Store shared state on app
    app.state.job_store = job_store
    app.state.worker = worker
    app.state.extractor = extractor

    yield

    # Shutdown
    cleanup_task.cancel()
    try:
        await cleanup_task
    except asyncio.CancelledError:
        pass
    await worker.stop()
    await job_store.close()
    logger.info("Shutdown complete")


def create_app() -> FastAPI:
    app = FastAPI(
        title="Yoink! API",
        description="Extract components from lecture notes via document layout detection.",
        version="0.2.0",
        lifespan=lifespan,
    )

    # CORS — configurable via env var, defaults to allow all for dev
    allowed_origins = os.environ.get("YOINK_CORS_ORIGINS", "*").split(",")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=allowed_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Import and mount routes
    from yoink.api.routes import router
    app.include_router(router, prefix="/api/v1")

    return app


app = create_app()
