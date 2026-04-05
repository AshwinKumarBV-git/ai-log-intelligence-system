"""
api/app.py — FastAPI Application Factory
==========================================

PURPOSE:
    Creates and configures the FastAPI application with:
      - CORS middleware (allows frontend access)
      - Startup/shutdown lifecycle events
      - Route mounting
      - API metadata (title, version, docs)

WHY APIs ARE NEEDED:
    The data pipeline (Producer → Queue → Consumer → OpenSearch) processes
    logs, but no human or frontend can access them without an API.
    This REST API is the bridge between the storage layer and:
      1. Frontend dashboards (React, Vue, etc.)
      2. Alerting systems (PagerDuty, Slack bots)
      3. CLI tools and scripts
      4. Other microservices that need log data

HOW THIS CONNECTS TO FRONTEND:
    A frontend dashboard would:
      - Poll GET /logs every 5s for a live log stream
      - Use GET /logs/search for the search bar
      - Use GET /logs/stats for charts (severity pie, level histogram)
      - Use GET /logs/{id} for log detail modals

USAGE:
    # Development
    python -m api.app
    # or
    uvicorn api.app:app --reload --host 0.0.0.0 --port 8000

    # API docs
    http://localhost:8000/docs      (Swagger UI)
    http://localhost:8000/redoc     (ReDoc)
"""

import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from config.settings import settings
from api.routes import router
from storage.opensearch_client import get_client, ensure_index_exists

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("api")

# ---------------------------------------------------------------------------
# FastAPI application
# ---------------------------------------------------------------------------
app = FastAPI(
    title="AI Log Intelligence System",
    description=(
        "AIOps Lite — A distributed log analysis system that ingests logs "
        "via RabbitMQ, analyzes them with rule-based (and optionally LLM) "
        "engines, stores results in OpenSearch, and exposes them via REST API."
    ),
    version="1.0.0",
    docs_url="/docs",         # Swagger UI
    redoc_url="/redoc",       # ReDoc
    openapi_url="/openapi.json",
)

# ---------------------------------------------------------------------------
# CORS middleware — allows frontend apps on different origins to call the API
# ---------------------------------------------------------------------------
# In production, restrict origins to your actual frontend domain.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],           # Allow all origins in dev
    allow_credentials=True,
    allow_methods=["*"],           # Allow all HTTP methods
    allow_headers=["*"],           # Allow all headers
)

# ---------------------------------------------------------------------------
# Lifecycle events
# ---------------------------------------------------------------------------
@app.on_event("startup")
async def on_startup():
    """
    Called once when the API server starts.

    Initializes the OpenSearch client and ensures the index exists.
    This catches connection issues early (fail-fast) rather than
    returning 500 errors on the first request.
    """
    logger.info("=" * 60)
    logger.info("🚀 AI Log Intelligence — API Starting")
    logger.info(f"   OpenSearch: {settings.OPENSEARCH_URL}")
    logger.info(f"   Index:      {settings.OPENSEARCH_INDEX}")
    logger.info(f"   API docs:   http://{settings.API_HOST}:{settings.API_PORT}/docs")
    logger.info("=" * 60)

    try:
        get_client()
        ensure_index_exists()
        logger.info("✅ OpenSearch connection verified and index ready.")
    except Exception as e:
        logger.error(f"⚠️ OpenSearch not available at startup: {e}")
        logger.warning("API will start but some endpoints may return errors.")


@app.on_event("shutdown")
async def on_shutdown():
    """Called once when the API server shuts down."""
    logger.info("🛑 API shutting down.")


# ---------------------------------------------------------------------------
# Mount routes
# ---------------------------------------------------------------------------
app.include_router(router)

# Log all registered routes at import time
for route in app.routes:
    if hasattr(route, "methods"):
        methods = ",".join(route.methods)
        logger.info(f"  📌 {methods:8s} {route.path}")


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    import uvicorn

    logger.info("Starting uvicorn server...")
    uvicorn.run(
        "api.app:app",
        host=settings.API_HOST,
        port=settings.API_PORT,
        reload=True,          # Auto-reload on code changes (dev only)
        log_level="info",
    )
