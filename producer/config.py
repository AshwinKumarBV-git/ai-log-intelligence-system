"""
producer/config.py — Producer-Specific Configuration
=====================================================

Defines the log templates, service names, and message patterns
used by the producer to generate realistic log entries.

WHY A SEPARATE CONFIG?
    The central config/settings.py handles infrastructure (hosts, ports).
    This file handles domain-specific data — the "vocabulary" of logs.
    Keeping them separate means you can change log patterns without
    touching connection settings, and vice versa.
"""

# ---------------------------------------------------------------------------
# Simulated microservice names
# ---------------------------------------------------------------------------
# These represent a realistic microservice architecture.
# The producer randomly picks from this list for each log entry.
SERVICE_NAMES = [
    "auth-service",
    "payment-gateway",
    "user-api",
    "order-service",
    "notification-service",
    "inventory-service",
    "search-service",
    "analytics-engine",
]

# ---------------------------------------------------------------------------
# Log levels with weighted probabilities
# ---------------------------------------------------------------------------
# Realistic distribution: most logs are INFO/DEBUG, errors are rare.
# Format: (level, weight)  — higher weight = more frequent
LOG_LEVELS = [
    ("DEBUG",    20),
    ("INFO",     50),
    ("WARNING",  15),
    ("ERROR",    10),
    ("CRITICAL",  5),
]

# ---------------------------------------------------------------------------
# Message templates per log level
# ---------------------------------------------------------------------------
# Each level has domain-realistic messages. The producer picks randomly
# within the chosen level. This makes analysis patterns detectable
# by the consumer's rule engine.
LOG_MESSAGES = {
    "DEBUG": [
        "Cache hit for key user_session_{id}",
        "Database query executed in {latency}ms",
        "Request payload size: {size} bytes",
        "Connection pool status: {active}/{total} active",
        "Feature flag 'dark_mode' evaluated to {flag}",
    ],
    "INFO": [
        "User {user} logged in successfully",
        "Order {order_id} placed successfully — total: ${amount}",
        "Health check passed — uptime: {uptime}s",
        "Email notification sent to {email}",
        "Payment processed for transaction {txn_id}",
        "Inventory updated: item {item_id} — stock: {stock}",
        "Search query completed in {latency}ms — {results} results",
    ],
    "WARNING": [
        "High memory usage detected: {memory}% — threshold: 80%",
        "API response time degraded: {latency}ms (SLA: 200ms)",
        "Rate limit approaching for client {client_id}: {count}/1000",
        "Certificate expiry warning: {days} days remaining",
        "Disk usage at {disk}% on volume /data",
        "Retry attempt {attempt}/3 for downstream service call",
    ],
    "ERROR": [
        "Connection timeout after 30s to database primary",
        "Failed to process payment: card declined for txn {txn_id}",
        "NullPointerException in UserService.getProfile()",
        "HTTP 503 from downstream inventory-service",
        "Message deserialization failed: invalid JSON payload",
        "Authentication failed for user {user}: invalid credentials",
    ],
    "CRITICAL": [
        "Database connection pool exhausted — all 50 connections in use",
        "Disk full on /data volume — writes halted",
        "Out of memory error — heap usage at 98%",
        "Circuit breaker OPEN for payment-gateway — 50 consecutive failures",
        "SSL certificate expired for api.production.internal",
    ],
}

# ---------------------------------------------------------------------------
# Placeholder value ranges (for template rendering)
# ---------------------------------------------------------------------------
PLACEHOLDER_RANGES = {
    "id":        (1000, 9999),
    "latency":   (1, 5000),
    "size":      (64, 65536),
    "active":    (1, 50),
    "total":     (50, 50),
    "flag":      None,          # Boolean — handled specially
    "user":      None,          # String — handled specially
    "order_id":  (100000, 999999),
    "amount":    (10, 2500),
    "uptime":    (1, 864000),
    "email":     None,          # String — handled specially
    "txn_id":    (100000, 999999),
    "item_id":   (1, 5000),
    "stock":     (0, 1000),
    "results":   (0, 500),
    "memory":    (75, 99),
    "client_id": (1, 100),
    "count":     (800, 999),
    "days":      (1, 30),
    "disk":      (85, 99),
    "attempt":   (1, 3),
}

# Sample data for string placeholders
SAMPLE_USERS = ["alice", "bob", "charlie", "diana", "eve", "frank"]
SAMPLE_EMAILS = [
    "alice@example.com", "bob@company.io", "charlie@startup.dev",
    "diana@enterprise.co", "eve@service.net",
]
