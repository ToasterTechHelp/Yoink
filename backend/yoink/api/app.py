"""FastAPI application factory with lifespan management."""

import asyncio
import logging
import os
import shutil
from contextlib import asynccontextmanager
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from supabase import create_client

from yoink.api.jobs import JobStore
from yoink.api.worker import ExtractionWorker
from yoink.extractor import LayoutExtractor

load_dotenv()

logger = logging.getLogger(__name__)

JOB_DATA_DIR = os.environ.get("YOINK_JOB_DATA_DIR", "./job_data")
UPLOAD_DIR = os.environ.get("YOINK_UPLOAD_DIR", "./uploads")
STATIC_DIR = os.environ.get("YOINK_STATIC_DIR", "./static")
DB_PATH = os.environ.get("YOINK_DB_PATH", "yoink_jobs.db")
CLEANUP_INTERVAL_SECONDS = 3600  # 1 hour

SUPABASE_URL = os.environ.get("SUPABASE_URL", "")
SUPABASE_SERVICE_ROLE_KEY = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")


async def _cleanup_loop(job_store: JobStore) -> None:
    """Periodically clean up jobs older than 12 hours."""
    while True:
        try:
            await asyncio.sleep(CLEANUP_INTERVAL_SECONDS)
            old_jobs = await job_store.get_old_job_paths(max_age_hours=12)
            for job in old_jobs:
                ExtractionWorker.cleanup_job_files(job.get("upload_path"), job.get("result_path"))
                guest_dir = Path(STATIC_DIR, "guest", job.get("id", ""))
                if guest_dir.exists():
                    shutil.rmtree(guest_dir, ignore_errors=True)
            count = await job_store.cleanup_old_jobs(max_age_hours=12)
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
    Path(STATIC_DIR).mkdir(parents=True, exist_ok=True)
    Path(STATIC_DIR, "guest").mkdir(parents=True, exist_ok=True)

    # Init Supabase client (service_role for backend operations)
    supabase = None
    if SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY:
        supabase = create_client(SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY)
        logger.info("Supabase client initialized")
    else:
        logger.warning("Supabase credentials not set — user features disabled")

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
        supabase=supabase,
        supabase_url=SUPABASE_URL,
    )
    worker.start()

    # Start cleanup loop
    cleanup_task = asyncio.create_task(_cleanup_loop(job_store))

    # Store shared state on app
    app.state.job_store = job_store
    app.state.worker = worker
    app.state.extractor = extractor
    app.state.supabase = supabase
    app.state.supabase_url = SUPABASE_URL

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

    # Mount static files for guest component images
    Path(STATIC_DIR).mkdir(parents=True, exist_ok=True)
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

    # Import and mount routes
    from yoink.api.routes import router
    app.include_router(router, prefix="/api/v1")

    return app


app = create_app()
