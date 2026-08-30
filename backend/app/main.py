from pathlib import Path
from contextlib import asynccontextmanager
import logging
from fastapi import FastAPI, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from app.core.config import settings
from app.api.v1.router import api_v1_router
from app.db.init_db import init_db

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger("fastshop.main")

# Resolve frontend path dynamically
def get_frontend_dir() -> Path | None:
    candidates = [
        Path(__file__).resolve().parent.parent.parent / "frontend",
        Path(__file__).resolve().parent.parent / "frontend",
        Path.cwd() / "frontend",
        Path.cwd() / "ShopFast" / "frontend",
    ]
    for p in candidates:
        if p.exists() and (p / "index.html").exists():
            return p
    return None

frontend_dir = get_frontend_dir()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application startup & shutdown lifespan events."""
    logger.info(f"Starting {settings.PROJECT_NAME} v{settings.VERSION}...")
    # Initialize DB & Seed Data
    try:
        await init_db()
        logger.info("Database and product catalog initialized successfully.")
    except Exception as e:
        logger.error(f"Error during DB initialization: {e}", exc_info=True)
    
    yield
    
    logger.info(f"Shutting down {settings.PROJECT_NAME}...")


app = FastAPI(
    title=settings.PROJECT_NAME,
    version=settings.VERSION,
    description="FastAPI Backend for FASTSHOP AI Retail Checkout & Queue Intelligence.",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc"
)

# CORS Configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include v1 API Router and /api compatibility alias
app.include_router(api_v1_router, prefix=settings.API_V1_STR)
app.include_router(api_v1_router, prefix="/api")


@app.get("/health", tags=["Health"])
async def health_check():
    """Health check endpoint for Render / Kubernetes / Cloud Run container monitoring."""
    return {
        "status": "healthy",
        "service": settings.PROJECT_NAME,
        "version": settings.VERSION,
        "environment": settings.ENVIRONMENT
    }


@app.get("/", tags=["Frontend"])
async def root():
    """Serves the FASTSHOP Customer Web App or API welcome page."""
    if frontend_dir and (frontend_dir / "index.html").exists():
        return FileResponse(frontend_dir / "index.html", media_type="text/html")
    return {
        "message": "Welcome to FASTSHOP AI API",
        "documentation": "/docs",
        "version": settings.VERSION
    }


# Mount static directory if available
if frontend_dir and frontend_dir.exists():
    app.mount("/static", StaticFiles(directory=str(frontend_dir)), name="static")

