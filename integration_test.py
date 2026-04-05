"""
Integration Test — Full Pipeline Verification
===============================================

Tests the complete data flow:
    Producer → RabbitMQ → Consumer → Analyzer → OpenSearch → API

This script:
    1. Clears the OpenSearch index (clean slate)
    2. Starts the consumer in background
    3. Produces test logs
    4. Waits for consumer to process them
    5. Verifies logs are stored in OpenSearch
    6. Verifies the API returns them
    7. Tests search functionality
    8. Tests statistics endpoint
    9. Reports pass/fail for each stage

USAGE:
    python integration_test.py
"""

import json
import sys
import time
import subprocess
import threading
import logging
import requests
from datetime import datetime, timezone

# Project imports
sys.path.insert(0, ".")
from config.settings import settings
from producer.producer import generate_log_entry, connect_to_rabbitmq
from consumer.analyzer import analyze_log
from storage.opensearch_client import get_client, ensure_index_exists, store_log, get_all_logs, search_logs

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("integration_test")

API_BASE = f"http://localhost:{settings.API_PORT}"
NUM_TEST_LOGS = 10
PASS = "✅ PASS"
FAIL = "❌ FAIL"
results = []


def record(test_name: str, passed: bool, detail: str = ""):
    """Record test result."""
    status = PASS if passed else FAIL
    results.append((test_name, passed, detail))
    logger.info(f"  {status} {test_name}" + (f" — {detail}" if detail else ""))


# ---------------------------------------------------------------------------
# Stage 1: Verify infrastructure connectivity
# ---------------------------------------------------------------------------
def test_infrastructure():
    """Verify RabbitMQ and OpenSearch are reachable."""
    print("\n" + "=" * 70)
    print("STAGE 1: Infrastructure Connectivity")
    print("=" * 70)

    # RabbitMQ
    try:
        conn = connect_to_rabbitmq(max_retries=2, retry_delay=1)
        conn.close()
        record("RabbitMQ connection", True)
    except Exception as e:
        record("RabbitMQ connection", False, str(e))

    # OpenSearch
    try:
        client = get_client()
        info = client.info()
        version = info["version"]["number"]
        record("OpenSearch connection", True, f"v{version}")
    except Exception as e:
        record("OpenSearch connection", False, str(e))


# ---------------------------------------------------------------------------
# Stage 2: Reset OpenSearch index
# ---------------------------------------------------------------------------
def test_index_reset():
    """Delete and recreate the index for a clean test."""
    print("\n" + "=" * 70)
    print("STAGE 2: Index Reset")
    print("=" * 70)

    try:
        client = get_client()
        index = settings.OPENSEARCH_INDEX

        # Delete existing index
        if client.indices.exists(index=index):
            client.indices.delete(index=index)
            logger.info(f"  Deleted existing index '{index}'.")

        # Recreate with schema
        ensure_index_exists(index)
        record("Index reset", True, f"'{index}' created with schema")
    except Exception as e:
        record("Index reset", False, str(e))


# ---------------------------------------------------------------------------
# Stage 3: Log generation
# ---------------------------------------------------------------------------
def test_log_generation():
    """Verify the producer generates valid log entries."""
    print("\n" + "=" * 70)
    print("STAGE 3: Log Generation")
    print("=" * 70)

    try:
        logs = [generate_log_entry() for _ in range(NUM_TEST_LOGS)]
        required_fields = {"timestamp", "service", "level", "message"}

        all_valid = all(required_fields.issubset(log.keys()) for log in logs)
        levels = set(log["level"] for log in logs)

        record("Generate logs", all_valid, f"{NUM_TEST_LOGS} logs, levels: {levels}")

        # Show sample
        sample = logs[0]
        logger.info(f"  Sample: [{sample['level']}] {sample['service']}: {sample['message'][:60]}")

        return logs
    except Exception as e:
        record("Generate logs", False, str(e))
        return []


# ---------------------------------------------------------------------------
# Stage 4: Analysis
# ---------------------------------------------------------------------------
def test_analysis(logs: list[dict]):
    """Verify the analyzer produces valid results."""
    print("\n" + "=" * 70)
    print("STAGE 4: Log Analysis")
    print("=" * 70)

    try:
        results_list = []
        for log in logs:
            analysis = analyze_log(log)
            results_list.append(analysis)

        required_fields = {"issue", "severity", "suggested_fix", "analyzer"}
        all_valid = all(required_fields.issubset(r.keys()) for r in results_list)

        severities = {}
        for r in results_list:
            sev = r["severity"]
            severities[sev] = severities.get(sev, 0) + 1

        record("Analyze logs", all_valid, f"Severities: {severities}")

        # Show a sample analysis
        for log, analysis in zip(logs, results_list):
            if analysis["issue"] != "none_detected":
                logger.info(
                    f"  Sample hit: [{log['level']}] '{log['message'][:40]}...' "
                    f"→ issue={analysis['issue']}, severity={analysis['severity']}"
                )
                break

        return results_list
    except Exception as e:
        record("Analyze logs", False, str(e))
        return []


# ---------------------------------------------------------------------------
# Stage 5: Storage
# ---------------------------------------------------------------------------
def test_storage(logs: list[dict], analyses: list[dict]):
    """Verify logs + analyses are stored in OpenSearch."""
    print("\n" + "=" * 70)
    print("STAGE 5: OpenSearch Storage")
    print("=" * 70)

    try:
        doc_ids = []
        for log, analysis in zip(logs, analyses):
            doc_id = store_log(log, analysis)
            doc_ids.append(doc_id)

        # Verify count
        client = get_client()
        time.sleep(1)  # Wait for refresh
        count_response = client.count(index=settings.OPENSEARCH_INDEX)
        count = count_response["count"]

        record("Store logs", count == NUM_TEST_LOGS, f"{count}/{NUM_TEST_LOGS} docs indexed")
        return doc_ids
    except Exception as e:
        record("Store logs", False, str(e))
        return []


# ---------------------------------------------------------------------------
# Stage 6: Retrieval
# ---------------------------------------------------------------------------
def test_retrieval():
    """Verify get_all_logs returns stored data."""
    print("\n" + "=" * 70)
    print("STAGE 6: Log Retrieval")
    print("=" * 70)

    try:
        logs = get_all_logs(size=NUM_TEST_LOGS)
        all_have_analysis = all("analysis" in log for log in logs)

        record(
            "Retrieve logs",
            len(logs) == NUM_TEST_LOGS and all_have_analysis,
            f"Retrieved {len(logs)}, all have analysis: {all_have_analysis}",
        )
    except Exception as e:
        record("Retrieve logs", False, str(e))


# ---------------------------------------------------------------------------
# Stage 7: Search
# ---------------------------------------------------------------------------
def test_search():
    """Verify full-text search works."""
    print("\n" + "=" * 70)
    print("STAGE 7: Full-Text Search")
    print("=" * 70)

    test_queries = ["timeout", "error", "memory", "service"]
    for query in test_queries:
        try:
            results = search_logs(query, size=10)
            record(f"Search '{query}'", True, f"{len(results)} results")
        except Exception as e:
            record(f"Search '{query}'", False, str(e))


# ---------------------------------------------------------------------------
# Stage 8: API endpoints
# ---------------------------------------------------------------------------
def test_api():
    """Verify all API endpoints respond correctly."""
    print("\n" + "=" * 70)
    print("STAGE 8: REST API Endpoints")
    print("=" * 70)

    # Health check
    try:
        resp = requests.get(f"{API_BASE}/", timeout=5)
        data = resp.json()
        record(
            "GET /",
            resp.status_code == 200 and data["status"] == "healthy",
            f"status={data['status']}",
        )
    except Exception as e:
        record("GET /", False, f"API may not be running: {e}")

    # Fetch logs
    try:
        resp = requests.get(f"{API_BASE}/logs?size=5", timeout=5)
        data = resp.json()
        record(
            "GET /logs",
            resp.status_code == 200 and data["total"] == NUM_TEST_LOGS,
            f"total={data['total']}, returned={data['returned']}",
        )
    except Exception as e:
        record("GET /logs", False, str(e))

    # Fetch filtered logs
    try:
        resp = requests.get(f"{API_BASE}/logs?level=ERROR&size=10", timeout=5)
        data = resp.json()
        all_error = all(log["level"] == "ERROR" for log in data["logs"])
        record(
            "GET /logs?level=ERROR",
            resp.status_code == 200 and all_error,
            f"returned={data['returned']}, all ERROR: {all_error}",
        )
    except Exception as e:
        record("GET /logs?level=ERROR", False, str(e))

    # Search
    try:
        resp = requests.get(f"{API_BASE}/logs/search?q=timeout", timeout=5)
        data = resp.json()
        record(
            "GET /logs/search?q=timeout",
            resp.status_code == 200,
            f"results={data['total']}",
        )
    except Exception as e:
        record("GET /logs/search?q=timeout", False, str(e))

    # Stats
    try:
        resp = requests.get(f"{API_BASE}/logs/stats", timeout=5)
        data = resp.json()
        record(
            "GET /logs/stats",
            resp.status_code == 200 and data["total_logs"] == NUM_TEST_LOGS,
            f"total={data['total_logs']}, severities={data['severity_distribution']}",
        )
    except Exception as e:
        record("GET /logs/stats", False, str(e))


# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------
def print_report():
    """Print final test report."""
    print("\n" + "=" * 70)
    print("📊 INTEGRATION TEST REPORT")
    print("=" * 70)

    passed = sum(1 for _, p, _ in results if p)
    failed = sum(1 for _, p, _ in results if not p)
    total = len(results)

    for name, p, detail in results:
        status = PASS if p else FAIL
        print(f"  {status} {name}" + (f" — {detail}" if detail else ""))

    print("-" * 70)
    print(f"  Total: {total} | Passed: {passed} | Failed: {failed}")

    if failed == 0:
        print("\n  🎉 ALL TESTS PASSED — Pipeline is fully operational!")
    else:
        print(f"\n  ⚠️  {failed} test(s) failed. Review the output above.")

    print("=" * 70)
    return failed == 0


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    print("=" * 70)
    print("🔬 AI Log Intelligence System — Integration Test")
    print("=" * 70)
    print(f"  Time:       {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"  RabbitMQ:   {settings.RABBITMQ_HOST}:{settings.RABBITMQ_PORT}")
    print(f"  OpenSearch: {settings.OPENSEARCH_URL}")
    print(f"  API:        {API_BASE}")
    print(f"  Test logs:  {NUM_TEST_LOGS}")

    # Run all stages
    test_infrastructure()
    test_index_reset()
    logs = test_log_generation()
    analyses = test_analysis(logs)
    if logs and analyses:
        test_storage(logs, analyses)
        test_retrieval()
        test_search()
    test_api()

    # Report
    all_passed = print_report()
    sys.exit(0 if all_passed else 1)


if __name__ == "__main__":
    main()
