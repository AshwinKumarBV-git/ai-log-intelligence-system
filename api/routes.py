"""
api/routes.py — API Route Definitions
=======================================

Defines all REST endpoints for the AI Log Intelligence System.

WHY SEPARATE ROUTES FROM APP?
    Separating route definitions from the app factory follows the
    "single responsibility" principle:
      - routes.py: Business logic for each endpoint
      - app.py:    Application lifecycle (startup, shutdown, middleware)
    This makes routes independently testable and the app easier to configure.

ENDPOINTS:
    GET  /                  → Health check
    GET  /logs              → Fetch recent logs (with optional filters)
    GET  /logs/search       → Full-text search across logs
    GET  /logs/stats        → Aggregated statistics (severity distribution, etc.)
    GET  /logs/{log_id}     → Fetch a single log by ID
"""

import logging
from typing import Optional

from fastapi import APIRouter, HTTPException, Query

from storage.opensearch_client import (
    get_all_logs,
    search_logs,
    get_client,
    ensure_index_exists,
)
from config.settings import settings

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logger = logging.getLogger("api.routes")

# ---------------------------------------------------------------------------
# Router instance — mounted by app.py
# ---------------------------------------------------------------------------
router = APIRouter()


# ---------------------------------------------------------------------------
# GET / — Health check
# ---------------------------------------------------------------------------
@router.get(
    "/",
    tags=["health"],
    summary="Health check",
    description="Returns service status and connectivity to RabbitMQ and OpenSearch.",
)
async def health_check():
    """
    Health check endpoint — verifies the API is running and
    can reach OpenSearch.

    Returns:
        dict with status, service name, and OpenSearch connectivity.
    """
    opensearch_ok = False
    opensearch_version = "unknown"

    try:
        client = get_client()
        info = client.info()
        opensearch_ok = True
        opensearch_version = info.get("version", {}).get("number", "unknown")
    except Exception as e:
        logger.warning(f"OpenSearch health check failed: {e}")

    return {
        "status": "healthy" if opensearch_ok else "degraded",
        "service": "ai-log-intelligence-api",
        "opensearch": {
            "connected": opensearch_ok,
            "version": opensearch_version,
            "url": settings.OPENSEARCH_URL,
        },
    }


# ---------------------------------------------------------------------------
# GET /logs — Fetch recent logs
# ---------------------------------------------------------------------------
@router.get(
    "/logs",
    tags=["logs"],
    summary="Fetch recent logs",
    description=(
        "Retrieves the most recent log entries from OpenSearch. "
        "Supports optional filtering by service name and log level."
    ),
)
async def fetch_logs(
    size: int = Query(
        default=50,
        ge=1,
        le=500,
        description="Number of logs to return (1-500)",
    ),
    service: Optional[str] = Query(
        default=None,
        description="Filter by service name (e.g., 'auth-service')",
    ),
    level: Optional[str] = Query(
        default=None,
        description="Filter by log level (DEBUG, INFO, WARNING, ERROR, CRITICAL)",
    ),
    severity: Optional[str] = Query(
        default=None,
        description="Filter by analysis severity (low, medium, high, critical)",
    ),
):
    """
    Fetch recent logs with optional filters.

    WHY THIS ENDPOINT?
        This is the primary data endpoint for dashboards and monitoring UIs.
        A frontend can poll this every few seconds to show a live log stream.

    Args:
        size:     Maximum number of logs to return.
        service:  Filter by microservice name.
        level:    Filter by log level.
        severity: Filter by analysis severity.

    Returns:
        dict with total count and list of log entries.
    """
    try:
        client = get_client()
        index_name = settings.OPENSEARCH_INDEX

        # Check if index exists
        if not client.indices.exists(index=index_name):
            return {"total": 0, "logs": [], "message": "No logs indexed yet."}

        # Build dynamic query with filters
        must_clauses = []

        if service:
            must_clauses.append({"term": {"service": service}})
        if level:
            must_clauses.append({"term": {"level": level.upper()}})
        if severity:
            must_clauses.append({"term": {"analysis.severity": severity.lower()}})

        # Use match_all if no filters, bool query if filters present
        if must_clauses:
            query = {"bool": {"must": must_clauses}}
        else:
            query = {"match_all": {}}

        response = client.search(
            index=index_name,
            body={
                "query": query,
                "sort": [{"timestamp": {"order": "desc"}}],
                "size": size,
            },
        )

        hits = response.get("hits", {})
        total = hits.get("total", {}).get("value", 0)
        logs = [
            {"id": hit["_id"], **hit["_source"]}
            for hit in hits.get("hits", [])
        ]

        logger.info(f"GET /logs — returned {len(logs)}/{total} logs.")
        return {
            "total": total,
            "returned": len(logs),
            "logs": logs,
        }

    except Exception as e:
        logger.error(f"Failed to fetch logs: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to fetch logs: {str(e)}")


# ---------------------------------------------------------------------------
# GET /logs/search — Full-text search
# ---------------------------------------------------------------------------
@router.get(
    "/logs/search",
    tags=["logs"],
    summary="Search logs",
    description=(
        "Full-text search across log messages, analysis results, and service names. "
        "Supports fuzzy matching for typo tolerance."
    ),
)
async def search_logs_endpoint(
    q: str = Query(
        ...,
        min_length=1,
        max_length=200,
        description="Search query (e.g., 'timeout', 'memory leak', 'auth-service')",
    ),
    size: int = Query(
        default=50,
        ge=1,
        le=200,
        description="Maximum results to return (1-200)",
    ),
):
    """
    Full-text search across all indexed logs.

    WHY THIS ENDPOINT?
        Enables operators to quickly find specific log patterns:
        - "timeout" → find all timeout-related errors
        - "payment" → find payment processing issues
        - "auth-service" → find all logs from a specific service

    The search uses multi_match with fuzziness for typo tolerance
    and relevance scoring (most relevant results first).

    Args:
        q:    Search query string.
        size: Maximum results to return.

    Returns:
        dict with total matches and ranked results.
    """
    try:
        results = search_logs(query_text=q, size=size)

        logger.info(f"GET /logs/search?q={q} — returned {len(results)} results.")
        return {
            "query": q,
            "total": len(results),
            "results": results,
        }

    except Exception as e:
        logger.error(f"Search failed for '{q}': {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Search failed: {str(e)}")


# ---------------------------------------------------------------------------
# GET /logs/stats — Aggregated statistics
# ---------------------------------------------------------------------------
@router.get(
    "/logs/stats",
    tags=["analytics"],
    summary="Log statistics",
    description="Returns aggregated statistics: counts by level, severity, and service.",
)
async def log_statistics():
    """
    Aggregated log statistics for dashboards.

    Returns severity distribution, log level counts, and top services.
    These aggregations run on the OpenSearch server — efficient even
    on millions of documents.

    Returns:
        dict with total_logs, severity_distribution, level_distribution,
        and top_services.
    """
    try:
        client = get_client()
        index_name = settings.OPENSEARCH_INDEX

        if not client.indices.exists(index=index_name):
            return {
                "total_logs": 0,
                "severity_distribution": {},
                "level_distribution": {},
                "top_services": {},
            }

        response = client.search(
            index=index_name,
            body={
                "size": 0,  # We only want aggregations, not documents
                "aggs": {
                    "severity_distribution": {
                        "terms": {"field": "analysis.severity", "size": 10}
                    },
                    "level_distribution": {
                        "terms": {"field": "level", "size": 10}
                    },
                    "top_services": {
                        "terms": {"field": "service", "size": 20}
                    },
                    "issues_breakdown": {
                        "terms": {"field": "analysis.issue", "size": 20}
                    },
                },
            },
        )

        total = response.get("hits", {}).get("total", {}).get("value", 0)
        aggs = response.get("aggregations", {})

        def _buckets_to_dict(agg_name: str) -> dict:
            """Convert OpenSearch aggregation buckets to {key: count} dict."""
            buckets = aggs.get(agg_name, {}).get("buckets", [])
            return {b["key"]: b["doc_count"] for b in buckets}

        stats = {
            "total_logs": total,
            "severity_distribution": _buckets_to_dict("severity_distribution"),
            "level_distribution": _buckets_to_dict("level_distribution"),
            "top_services": _buckets_to_dict("top_services"),
            "issues_breakdown": _buckets_to_dict("issues_breakdown"),
        }

        logger.info(f"GET /logs/stats — total: {total} logs.")
        return stats

    except Exception as e:
        logger.error(f"Failed to compute stats: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Stats failed: {str(e)}")


# ---------------------------------------------------------------------------
# GET /logs/{log_id} — Fetch single log by ID
# ---------------------------------------------------------------------------
@router.get(
    "/logs/{log_id}",
    tags=["logs"],
    summary="Get log by ID",
    description="Retrieve a single log entry by its OpenSearch document ID.",
)
async def get_log_by_id(log_id: str):
    """
    Fetch a single log entry by its document ID.

    Useful for linking from alerts or dashboards to the full
    log detail view.

    Args:
        log_id: OpenSearch document ID.

    Returns:
        The full log document with analysis results.
    """
    try:
        client = get_client()
        index_name = settings.OPENSEARCH_INDEX

        response = client.get(index=index_name, id=log_id)
        return {
            "id": response["_id"],
            **response["_source"],
        }

    except Exception as e:
        error_msg = str(e)
        if "NotFoundError" in type(e).__name__ or "404" in error_msg:
            raise HTTPException(status_code=404, detail=f"Log '{log_id}' not found.")
        logger.error(f"Failed to fetch log '{log_id}': {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to fetch log: {error_msg}")
