"""
storage/opensearch_client.py — OpenSearch Client & Storage Layer
=================================================================

PURPOSE:
    Provides a managed OpenSearch client and the store_log() function
    that the consumer calls to persist analyzed log entries.

HOW SEARCH SYSTEMS WORK:
    Unlike a relational database (rows in tables), OpenSearch stores
    documents in an "inverted index" — similar to a book's back-of-book index.

    When you index the message "Connection timeout after 30s":
      - The analyzer tokenizes it: ["connection", "timeout", "after", "30s"]
      - Each token maps to the document ID in the inverted index
      - Searching for "timeout" instantly finds all documents containing it

    This is why OpenSearch can search millions of logs in milliseconds
    — it doesn't scan every document; it looks up tokens in the index.

WHY INDEXING IS IMPORTANT:
    1. Speed:  O(1) token lookup vs O(n) full scan
    2. Relevance: TF-IDF scoring ranks results by relevance
    3. Aggregation: count by service, severity distribution, time histograms
    4. Near-real-time: new docs become searchable within 1 second

USAGE:
    from storage.opensearch_client import store_log, get_client

    # Store a log with analysis
    store_log(log_entry, analysis_result)

    # Direct client access for advanced queries
    client = get_client()
    results = client.search(index="logs", body=query)
"""

import logging
from datetime import datetime, timezone
from typing import Optional

from opensearchpy import OpenSearch, exceptions as os_exceptions

from config.settings import settings
from storage.schemas import get_index_body

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logger = logging.getLogger("storage")


# ---------------------------------------------------------------------------
# Client singleton
# ---------------------------------------------------------------------------
_client: Optional[OpenSearch] = None


def get_client() -> OpenSearch:
    """
    Get or create the OpenSearch client singleton.

    WHY SINGLETON?
        The OpenSearch client manages an internal HTTP connection pool.
        Creating a new client per request wastes connections and adds
        latency. A singleton reuses the pool across the application.

    Returns:
        An initialized OpenSearch client instance.
    """
    global _client

    if _client is not None:
        return _client

    logger.info(
        f"Initializing OpenSearch client: "
        f"http://{settings.OPENSEARCH_HOST}:{settings.OPENSEARCH_PORT}"
    )

    _client = OpenSearch(
        hosts=[{
            "host": settings.OPENSEARCH_HOST,
            "port": settings.OPENSEARCH_PORT,
        }],
        http_compress=True,       # Compress request/response bodies
        use_ssl=False,            # No SSL in dev (security disabled)
        verify_certs=False,       # No cert verification in dev
        timeout=30,               # Request timeout in seconds
        max_retries=3,            # Retry failed requests
        retry_on_timeout=True,    # Retry on timeout errors
    )

    # Verify connection
    try:
        info = _client.info()
        logger.info(
            f"✅ Connected to OpenSearch "
            f"v{info['version']['number']} "
            f"(cluster: {info['cluster_name']})"
        )
    except Exception as e:
        logger.error(f"❌ Failed to connect to OpenSearch: {e}")
        _client = None
        raise

    return _client


# ---------------------------------------------------------------------------
# Index management
# ---------------------------------------------------------------------------
def ensure_index_exists(index_name: str = None) -> bool:
    """
    Create the logs index if it doesn't already exist.

    This is idempotent — safe to call on every startup.
    The index is created with the schema defined in storage/schemas.py.

    Args:
        index_name: Index name. Defaults to settings.OPENSEARCH_INDEX.

    Returns:
        True if the index exists (created or already existed).
    """
    index_name = index_name or settings.OPENSEARCH_INDEX
    client = get_client()

    try:
        if client.indices.exists(index=index_name):
            logger.info(f"Index '{index_name}' already exists.")
            return True

        # Create index with explicit mapping
        client.indices.create(
            index=index_name,
            body=get_index_body(),
        )
        logger.info(f"✅ Created index '{index_name}' with schema.")
        return True

    except os_exceptions.RequestError as e:
        # Handle race condition — another process may have created it
        if "resource_already_exists_exception" in str(e):
            logger.info(f"Index '{index_name}' created by another process.")
            return True
        logger.error(f"Failed to create index '{index_name}': {e}")
        raise

    except Exception as e:
        logger.error(f"Failed to ensure index '{index_name}': {e}", exc_info=True)
        raise


# ---------------------------------------------------------------------------
# Store log — the main function the consumer calls
# ---------------------------------------------------------------------------
def store_log(log_entry: dict, analysis: Optional[dict] = None) -> str:
    """
    Store a log entry with its analysis result in OpenSearch.

    This function:
      1. Ensures the index exists (idempotent)
      2. Builds the document (log + analysis + metadata)
      3. Indexes it in OpenSearch
      4. Returns the document ID

    Args:
        log_entry: Parsed log dict with keys: timestamp, service, level, message
        analysis:  Analysis result dict (may be None if analysis was disabled/failed)

    Returns:
        The OpenSearch document ID of the stored log.

    Raises:
        Exception: If storage fails after retries.
    """
    client = get_client()
    index_name = settings.OPENSEARCH_INDEX

    # Ensure index exists (idempotent — no-op if already created)
    ensure_index_exists(index_name)

    # Build the document — merge log, analysis, and metadata
    document = {
        # Original log fields
        "timestamp": log_entry.get("timestamp"),
        "service": log_entry.get("service"),
        "level": log_entry.get("level"),
        "message": log_entry.get("message"),

        # Analysis results (nested object)
        "analysis": analysis or {
            "issue": "not_analyzed",
            "severity": "unknown",
            "suggested_fix": "Analysis was not performed.",
            "analyzer": "none",
            "matched_rule": None,
            "confidence": 0.0,
        },

        # Pipeline metadata
        "ingested_at": datetime.now(timezone.utc).isoformat(),
    }

    try:
        # Index the document — OpenSearch auto-generates a unique _id
        response = client.index(
            index=index_name,
            body=document,
            refresh="wait_for",  # Make doc immediately searchable (dev mode)
        )

        doc_id = response.get("_id", "unknown")
        logger.info(
            f"📥 Stored log [{log_entry.get('level')}] "
            f"from {log_entry.get('service')} "
            f"→ index='{index_name}', id={doc_id}"
        )
        return doc_id

    except os_exceptions.ConnectionError as e:
        logger.error(f"OpenSearch connection error: {e}")
        raise
    except os_exceptions.RequestError as e:
        logger.error(f"OpenSearch request error: {e}")
        raise
    except Exception as e:
        logger.error(f"Failed to store log: {e}", exc_info=True)
        raise


# ---------------------------------------------------------------------------
# Utility functions (used by API in Step 8)
# ---------------------------------------------------------------------------
def get_all_logs(size: int = 100) -> list[dict]:
    """
    Retrieve the most recent logs from OpenSearch.

    Args:
        size: Maximum number of logs to return (default: 100).

    Returns:
        List of log documents (newest first).
    """
    client = get_client()
    index_name = settings.OPENSEARCH_INDEX

    try:
        if not client.indices.exists(index=index_name):
            logger.warning(f"Index '{index_name}' does not exist yet.")
            return []

        response = client.search(
            index=index_name,
            body={
                "query": {"match_all": {}},
                "sort": [{"timestamp": {"order": "desc"}}],
                "size": size,
            },
        )

        hits = response.get("hits", {}).get("hits", [])
        logs = [
            {"id": hit["_id"], **hit["_source"]}
            for hit in hits
        ]

        logger.info(f"Retrieved {len(logs)} logs from '{index_name}'.")
        return logs

    except Exception as e:
        logger.error(f"Failed to retrieve logs: {e}", exc_info=True)
        return []


def search_logs(query_text: str, size: int = 50) -> list[dict]:
    """
    Full-text search across log messages.

    Uses OpenSearch's multi_match query to search across the
    message field and analysis.suggested_fix field.

    Args:
        query_text: Search query string (e.g., "timeout", "memory").
        size: Maximum results to return.

    Returns:
        List of matching log documents, ranked by relevance.
    """
    client = get_client()
    index_name = settings.OPENSEARCH_INDEX

    try:
        if not client.indices.exists(index=index_name):
            logger.warning(f"Index '{index_name}' does not exist yet.")
            return []

        response = client.search(
            index=index_name,
            body={
                "query": {
                    "multi_match": {
                        "query": query_text,
                        "fields": [
                            "message^3",                # Boost message matches 3x
                            "analysis.suggested_fix",   # Also search fixes
                            "analysis.issue",           # And issue types
                            "service",                  # And service names
                        ],
                        "type": "best_fields",
                        "fuzziness": "AUTO",  # Tolerate typos
                    }
                },
                "sort": [
                    {"_score": {"order": "desc"}},      # Most relevant first
                    {"timestamp": {"order": "desc"}},   # Then newest first
                ],
                "size": size,
            },
        )

        hits = response.get("hits", {}).get("hits", [])
        logs = [
            {"id": hit["_id"], "score": hit["_score"], **hit["_source"]}
            for hit in hits
        ]

        logger.info(f"Search '{query_text}' returned {len(logs)} results.")
        return logs

    except Exception as e:
        logger.error(f"Search failed for '{query_text}': {e}", exc_info=True)
        return []


# ---------------------------------------------------------------------------
# Self-test
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)

    print("=" * 60)
    print("OPENSEARCH STORAGE SELF-TEST")
    print("=" * 60)

    # Test 1: Connect
    print("\n1. Testing connection...")
    client = get_client()
    print("   ✅ Connected!")

    # Test 2: Create index
    print("\n2. Ensuring index exists...")
    ensure_index_exists()
    print("   ✅ Index ready!")

    # Test 3: Store a test log
    print("\n3. Storing a test log...")
    test_log = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "service": "test-service",
        "level": "INFO",
        "message": "Storage self-test — this is a test log entry",
    }
    test_analysis = {
        "issue": "none_detected",
        "severity": "low",
        "suggested_fix": "No issues — this is a test.",
        "analyzer": "self_test",
        "matched_rule": None,
        "confidence": 1.0,
    }
    doc_id = store_log(test_log, test_analysis)
    print(f"   ✅ Stored with ID: {doc_id}")

    # Test 4: Retrieve logs
    print("\n4. Retrieving all logs...")
    logs = get_all_logs(size=5)
    print(f"   ✅ Retrieved {len(logs)} logs.")
    for log in logs:
        print(f"      [{log.get('level')}] {log.get('service')}: {log.get('message', '')[:50]}")

    # Test 5: Search logs
    print("\n5. Searching for 'test'...")
    results = search_logs("test", size=5)
    print(f"   ✅ Found {len(results)} results.")

    print("\n" + "=" * 60)
    print("✅ All storage tests passed!")
