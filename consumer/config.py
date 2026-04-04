"""
consumer/config.py — Consumer-Specific Configuration
=====================================================

Defines consumer behavior settings — retry policies, prefetch counts,
and processing pipeline configuration.

WHY SEPARATE FROM CENTRAL CONFIG?
    Infrastructure settings (hosts, ports) live in config/settings.py.
    Consumer behavior (how many messages to prefetch, what to do on
    failure) is domain logic that only the consumer cares about.
"""

# ---------------------------------------------------------------------------
# Prefetch configuration
# ---------------------------------------------------------------------------
# How many unacknowledged messages the broker will deliver at once.
# Setting to 1 = process one message at a time (safe default).
# Increase for throughput if processing is idempotent and fast.
PREFETCH_COUNT = 1

# ---------------------------------------------------------------------------
# Retry / Error handling
# ---------------------------------------------------------------------------
# Maximum times to retry processing a single message before dead-lettering
MAX_PROCESSING_RETRIES = 3

# Whether to requeue a message that fails processing
# True  = message goes back to the queue (risk of infinite loop if poison message)
# False = message is discarded or dead-lettered (safer)
REQUEUE_ON_FAILURE = False

# ---------------------------------------------------------------------------
# Processing pipeline flags
# ---------------------------------------------------------------------------
# Enable/disable individual pipeline stages (useful for debugging)
ENABLE_ANALYSIS = True
ENABLE_STORAGE = True
