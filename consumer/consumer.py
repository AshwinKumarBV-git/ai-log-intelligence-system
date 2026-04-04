"""
consumer/consumer.py — Log Consumer (RabbitMQ Subscriber)
==========================================================

PURPOSE:
    Subscribes to the RabbitMQ "logs" queue, processes each message
    through the analysis pipeline, and stores the enriched result
    in OpenSearch. This is the core event-driven processing engine.

ARCHITECTURE:
    ┌──────────────┐       ┌────────────┐       ┌────────────┐       ┌──────────────┐
    │  RabbitMQ    │──AMQP─▶│  Consumer  │──────▶│  Analyzer  │──────▶│  OpenSearch   │
    │  queue: logs │       │  (this)    │       │  (Step 6)  │       │  (Step 7)    │
    └──────────────┘       └────────────┘       └────────────┘       └──────────────┘

EVENT-DRIVEN ARCHITECTURE:
    Unlike polling (check DB every N seconds), the consumer is
    event-driven — RabbitMQ pushes messages to it the moment they
    arrive. This gives:
      - Low latency: logs are processed within milliseconds of arrival
      - Efficiency: no wasted CPU cycles on empty polls
      - Backpressure: prefetch_count limits in-flight messages

CONSUMER PATTERN:
    The consumer uses "manual acknowledgment":
      1. Broker delivers a message
      2. Consumer processes it (analyze → store)
      3. Consumer sends ACK → broker removes the message
      4. If consumer crashes before ACK → broker redelivers to another consumer
    This guarantees at-least-once delivery — no message is silently lost.

USAGE:
    python -m consumer.consumer    # Start consuming (blocks until Ctrl+C)
"""

import json
import sys
import time
import signal
import logging
from typing import Callable

import pika
from pika.exceptions import AMQPConnectionError, AMQPChannelError

# Project imports
from config.settings import settings
from consumer.config import (
    PREFETCH_COUNT,
    MAX_PROCESSING_RETRIES,
    REQUEUE_ON_FAILURE,
    ENABLE_ANALYSIS,
    ENABLE_STORAGE,
)

# ---------------------------------------------------------------------------
# Logging setup
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("consumer")


# ---------------------------------------------------------------------------
# Graceful shutdown handler
# ---------------------------------------------------------------------------
_shutdown_requested = False


def _handle_signal(signum, frame):
    """Handle SIGINT/SIGTERM for graceful shutdown."""
    global _shutdown_requested
    logger.info(f"Received signal {signum} — initiating graceful shutdown...")
    _shutdown_requested = True


signal.signal(signal.SIGINT, _handle_signal)
signal.signal(signal.SIGTERM, _handle_signal)


# ---------------------------------------------------------------------------
# Message processing pipeline
# ---------------------------------------------------------------------------
def _parse_message(body: bytes) -> dict | None:
    """
    Safely parse a JSON message body.

    Returns:
        Parsed dict if valid JSON, None if parsing fails.
    """
    try:
        log_entry = json.loads(body.decode("utf-8"))

        # Validate required fields
        required_fields = {"timestamp", "service", "level", "message"}
        missing = required_fields - set(log_entry.keys())
        if missing:
            logger.warning(f"Message missing required fields: {missing}")
            return None

        return log_entry

    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse JSON: {e}. Body: {body[:200]}")
        return None
    except UnicodeDecodeError as e:
        logger.error(f"Failed to decode message bytes: {e}")
        return None


def _analyze_log(log_entry: dict) -> dict | None:
    """
    Run the log through the analysis pipeline.

    Currently a stub — will be replaced in Step 6 with the
    rule-based analyzer (and later LLM in Step 10).

    Args:
        log_entry: Parsed log dictionary.

    Returns:
        Analysis result dict, or None if analysis is disabled/fails.
    """
    if not ENABLE_ANALYSIS:
        logger.debug("Analysis disabled — skipping.")
        return None

    try:
        # Step 6 will replace this with: from consumer.analyzer import analyze_log
        # For now, use a simple stub that demonstrates the interface
        from consumer.analyzer import analyze_log
        analysis = analyze_log(log_entry)
        return analysis

    except ImportError:
        # Graceful fallback — analyzer not built yet (Step 6)
        logger.debug("Analyzer module not available yet — using stub.")
        return {
            "issue": "pending_analysis",
            "severity": "unknown",
            "suggested_fix": "Analyzer not yet implemented (Step 6).",
        }
    except Exception as e:
        logger.error(f"Analysis failed: {e}", exc_info=True)
        return None


def _store_log(log_entry: dict, analysis: dict | None) -> bool:
    """
    Store the log entry and its analysis in OpenSearch.

    Currently a stub — will be replaced in Step 7 with the
    OpenSearch storage module.

    Args:
        log_entry: Parsed log dictionary.
        analysis:  Analysis result (may be None if analysis failed/disabled).

    Returns:
        True if storage succeeded, False otherwise.
    """
    if not ENABLE_STORAGE:
        logger.debug("Storage disabled — skipping.")
        return True

    try:
        # Step 7 will replace this with: from storage.opensearch_client import store_log
        from storage.opensearch_client import store_log
        store_log(log_entry, analysis)
        return True

    except ImportError:
        # Graceful fallback — storage not built yet (Step 7)
        logger.debug("Storage module not available yet — logging to console.")
        logger.info(f"📦 [STUB STORE] {json.dumps(log_entry)}")
        return True
    except Exception as e:
        logger.error(f"Storage failed: {e}", exc_info=True)
        return False


def process_message(log_entry: dict) -> bool:
    """
    Full processing pipeline for a single log entry.

    Pipeline: Parse → Analyze → Store

    Args:
        log_entry: Parsed log dictionary.

    Returns:
        True if the entire pipeline succeeded, False otherwise.
    """
    # Stage 1: Analyze
    analysis = _analyze_log(log_entry)

    if analysis:
        logger.info(
            f"🔍 Analysis: severity={analysis.get('severity', 'N/A')}, "
            f"issue={analysis.get('issue', 'N/A')}"
        )

    # Stage 2: Store
    stored = _store_log(log_entry, analysis)

    if not stored:
        logger.warning("Storage failed — message will be NACKed.")
        return False

    return True


# ---------------------------------------------------------------------------
# RabbitMQ connection with retry logic
# ---------------------------------------------------------------------------
def connect_to_rabbitmq(max_retries: int = 5, retry_delay: int = 3) -> pika.BlockingConnection:
    """
    Establish a connection to RabbitMQ with exponential backoff retry.

    Args:
        max_retries: Maximum number of connection attempts.
        retry_delay: Initial delay between retries (doubles each attempt).

    Returns:
        An active pika.BlockingConnection.

    Raises:
        AMQPConnectionError: If all retry attempts are exhausted.
    """
    credentials = pika.PlainCredentials(
        username=settings.RABBITMQ_USER,
        password=settings.RABBITMQ_PASSWORD,
    )
    parameters = pika.ConnectionParameters(
        host=settings.RABBITMQ_HOST,
        port=settings.RABBITMQ_PORT,
        credentials=credentials,
        heartbeat=600,
        blocked_connection_timeout=300,
    )

    for attempt in range(1, max_retries + 1):
        try:
            logger.info(
                f"Connecting to RabbitMQ at {settings.RABBITMQ_HOST}:{settings.RABBITMQ_PORT} "
                f"(attempt {attempt}/{max_retries})..."
            )
            connection = pika.BlockingConnection(parameters)
            logger.info("✅ Connected to RabbitMQ successfully!")
            return connection

        except AMQPConnectionError as e:
            if attempt == max_retries:
                logger.critical(
                    f"❌ Failed to connect after {max_retries} attempts. Error: {e}"
                )
                raise

            wait_time = retry_delay * (2 ** (attempt - 1))
            logger.warning(
                f"Connection attempt {attempt} failed: {e}. "
                f"Retrying in {wait_time}s..."
            )
            time.sleep(wait_time)


# ---------------------------------------------------------------------------
# Callback — called for every message received from RabbitMQ
# ---------------------------------------------------------------------------
def on_message_received(channel, method, properties, body):
    """
    Callback invoked by pika for each incoming message.

    This is the heart of the event-driven consumer:
      1. Parse the message
      2. Process it (analyze + store)
      3. ACK on success → broker removes the message
      4. NACK on failure → broker discards or requeues

    Args:
        channel:    The pika channel object.
        method:     Delivery metadata (delivery_tag, routing_key, etc.).
        properties: Message properties (content_type, delivery_mode, etc.).
        body:       Raw message bytes.
    """
    delivery_tag = method.delivery_tag

    logger.info(f"📩 Received message [tag={delivery_tag}]")

    # Stage 1: Parse
    log_entry = _parse_message(body)
    if log_entry is None:
        # Invalid message — ACK it to remove from queue (it will never parse correctly)
        logger.warning(f"Discarding unparseable message [tag={delivery_tag}]")
        channel.basic_ack(delivery_tag=delivery_tag)
        return

    logger.info(
        f"📋 [{log_entry['level']}] {log_entry['service']}: "
        f"{log_entry['message'][:80]}"
    )

    # Stage 2: Process (analyze + store)
    try:
        success = process_message(log_entry)

        if success:
            # ACK — tell broker to remove the message from the queue
            channel.basic_ack(delivery_tag=delivery_tag)
            logger.info(f"✅ Message [tag={delivery_tag}] processed and ACKed.")
        else:
            # NACK — processing failed
            channel.basic_nack(
                delivery_tag=delivery_tag,
                requeue=REQUEUE_ON_FAILURE,
            )
            action = "requeued" if REQUEUE_ON_FAILURE else "discarded"
            logger.warning(f"❌ Message [tag={delivery_tag}] NACKed ({action}).")

    except Exception as e:
        logger.error(f"Unhandled error processing message [tag={delivery_tag}]: {e}", exc_info=True)
        channel.basic_nack(delivery_tag=delivery_tag, requeue=False)


# ---------------------------------------------------------------------------
# Main consumer loop
# ---------------------------------------------------------------------------
def start_consuming():
    """
    Main entry point — connects to RabbitMQ and begins consuming.

    This function blocks until:
      - Ctrl+C is pressed (SIGINT)
      - SIGTERM is received
      - The RabbitMQ connection drops

    The consumer automatically reconnects on connection loss.
    """
    while not _shutdown_requested:
        try:
            connection = connect_to_rabbitmq()
            channel = connection.channel()

            # Declare queue (idempotent — must match producer's declaration)
            channel.queue_declare(queue=settings.RABBITMQ_QUEUE, durable=True)

            # Prefetch — limits how many unACKed messages are in-flight
            # This provides backpressure: if consumer is slow, broker holds back
            channel.basic_qos(prefetch_count=PREFETCH_COUNT)

            # Register the callback
            channel.basic_consume(
                queue=settings.RABBITMQ_QUEUE,
                on_message_callback=on_message_received,
                auto_ack=False,  # Manual ACK — we control when messages are removed
            )

            logger.info(f"👂 Waiting for messages on queue '{settings.RABBITMQ_QUEUE}'...")
            logger.info("   Press Ctrl+C to stop.")

            # Start consuming (blocks here)
            channel.start_consuming()

        except KeyboardInterrupt:
            logger.info("Keyboard interrupt — stopping consumer.")
            if 'channel' in locals() and channel.is_open:
                channel.stop_consuming()
            break

        except AMQPConnectionError as e:
            if _shutdown_requested:
                break
            logger.error(f"Connection lost: {e}. Reconnecting in 5s...")
            time.sleep(5)

        except Exception as e:
            if _shutdown_requested:
                break
            logger.error(f"Unexpected error: {e}. Reconnecting in 5s...", exc_info=True)
            time.sleep(5)

        finally:
            if 'connection' in locals() and connection.is_open:
                connection.close()
                logger.info("🔌 RabbitMQ connection closed.")

    logger.info("🛑 Consumer stopped.")


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------
def main():
    """Start the consumer with banner."""
    logger.info("=" * 60)
    logger.info("🚀 AI Log Intelligence — Consumer Starting")
    logger.info(f"   RabbitMQ:       {settings.RABBITMQ_HOST}:{settings.RABBITMQ_PORT}")
    logger.info(f"   Queue:          {settings.RABBITMQ_QUEUE}")
    logger.info(f"   Prefetch:       {PREFETCH_COUNT}")
    logger.info(f"   Analysis:       {'enabled' if ENABLE_ANALYSIS else 'disabled'}")
    logger.info(f"   Storage:        {'enabled' if ENABLE_STORAGE else 'disabled'}")
    logger.info(f"   Requeue on fail: {REQUEUE_ON_FAILURE}")
    logger.info("=" * 60)

    start_consuming()


if __name__ == "__main__":
    main()
