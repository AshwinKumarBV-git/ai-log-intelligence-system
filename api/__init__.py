"""
api — FastAPI REST service for the AI Log Intelligence System.

Usage:
    python -m api.app                                    # Run with default settings
    uvicorn api.app:app --reload --host 0.0.0.0 --port 8000  # Run with uvicorn directly

Endpoints:
    GET /              → Health check
    GET /logs          → Fetch recent logs (with filters)
    GET /logs/search   → Full-text search
    GET /logs/stats    → Aggregated statistics
    GET /logs/{id}     → Single log by ID
    GET /docs          → Swagger UI
"""
