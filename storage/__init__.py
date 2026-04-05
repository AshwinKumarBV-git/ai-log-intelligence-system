"""
storage — OpenSearch storage layer for log persistence and search.

Usage:
    from storage.opensearch_client import store_log, get_all_logs, search_logs
"""

from storage.opensearch_client import (
    store_log,
    get_all_logs,
    search_logs,
    get_client,
    ensure_index_exists,
)

__all__ = ["store_log", "get_all_logs", "search_logs", "get_client", "ensure_index_exists"]
