"""
producer/producer.py — Log Producer (RabbitMQ Publisher)
========================================================

PURPOSE:
    Generates realistic, randomized log entries and publishes them
    to a RabbitMQ queue. This simulates a fleet of microservices
    emitting logs in a production environment.

ARCHITECTURE:
    ┌──────────┐          ┌──────────────┐
    │ Producer │ ──AMQP──▶│  RabbitMQ    │
    │ (this)   │          │  queue: logs │
    └──────────┘          └──────────────┘

WHY MESSAGE QUEUES?
    In a real system, hundreds of services produce logs simultaneously.
    Writing directly to a database would:
      - Create a tight coupling (if DB is down, logs are lost)
      - Overwhelm the DB under spike traffic
    A message queue DECOUPLES producers from consumers:
      - Producer pushes and forgets — zero knowledge of who processes logs
      - Queue buffers during traffic spikes — consumers catch up at their pace
      - If the consumer dies, messages are safely buffered (not lost)

USAGE:
    python -m producer.producer              # Run continuous log generation
    python -m producer.producer --count 10   # Generate exactly 10 logs, then stop
"""

import json
import sys
import time
import random
import signal
import logging
import argparse
from datetime import datetime, timezone

import pika
from pika.exceptions import AMQPConnectionError, AMQPChannelError

# Project imports
from config.settings import settings
from producer.config import (
    SERVICE_NAMES,
    LOG_LEVELS,
    LOG_MESSAGES,
    PLACEHOLDER_RANGES,
    SAMPLE_USERS,
    SAMPLE_EMAILS,
)

# ---------------------------------------------------------------------------
# Logging setup
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("producer")


# ---------------------------------------------------------------------------
# Graceful shutdown handler
# ---------------------------------------------------------------------------
_shutdown_requested = False


def _handle_signal(signum, frame):
    """Handle SIGINT/SIGTERM for graceful shutdown."""
    global _shutdown_requested
    logger.info(f"Received signal {signum} — shutting down gracefully...")
    _shutdown_requested = True


signal.signal(signal.SIGINT, _handle_signal)
signal.signal(signal.SIGTERM, _handle_signal)


# ---------------------------------------------------------------------------
# Log generation
# ---------------------------------------------------------------------------
def _pick_log_level() -> str:
    """
    Pick a log level using weighted random selection.
    Realistic distribution: INFO is most common, CRITICAL is rare.
    """
    levels, weights = zip(*LOG_LEVELS)
    return random.choices(levels, weights=weights, k=1)[0]


def _render_template(template: str) -> str:
    """
    Fill placeholder tokens like {user}, {latency} with realistic values.

    Uses the ranges defined in producer/config.py to generate
    contextually appropriate values for each placeholder.
    """
    result = template

    for key, value_range in PLACEHOLDER_RANGES.items():
        placeholder = "{" + key + "}"
        if placeholder not in result:
            continue

        if key == "flag":
            replacement = str(random.choice([True, False]))
        elif key == "user":
            replacement = random.choice(SAMPLE_USERS)
        elif key == "email":
            replacement = random.choice(SAMPLE_EMAILS)
        elif value_range is not None:
            low, high = value_range
            replacement = str(random.randint(low, high))
        else:
            replacement = "unknown"

        result = result.replace(placeholder, replacement)

    return result


def generate_log_entry() -> dict:
    """
    Generate a single realistic log entry.

    Returns:
        dict with keys: timestamp, service, level, message
    """
    level = _pick_log_level()
    template = random.choice(LOG_MESSAGES[level])
    message = _render_template(template)

    log_entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "service": random.choice(SERVICE_NAMES),
        "level": level,
        "message": message,
    }

    return log_entry


# ---------------------------------------------------------------------------
# RabbitMQ connection with retry logic
# ---------------------------------------------------------------------------
def connect_to_rabbitmq(max_retries: int = 5, retry_delay: int = 3) -> pika.BlockingConnection:
    """
    Establish a connection to RabbitMQ with exponential backoff retry.

    WHY RETRY?
        In containerized environments, RabbitMQ may not be ready when
        the producer starts (race condition). Retry with backoff gives
        the broker time to initialize without manual intervention.

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
        # Heartbeat keeps the connection alive during idle periods
        heartbeat=600,
        # Timeout for blocking operations (connection, channel open)
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
                    f"❌ Failed to connect to RabbitMQ after {max_retries} attempts. "
                    f"Last error: {e}"
                )
                raise

            wait_time = retry_delay * (2 ** (attempt - 1))  # Exponential backoff
            logger.warning(
                f"Connection attempt {attempt} failed: {e}. "
                f"Retrying in {wait_time}s..."
            )
            time.sleep(wait_time)


# ---------------------------------------------------------------------------
# Publishing
# ---------------------------------------------------------------------------
def publish_logs(count: int | None = None):
    """
    Main producer loop — generates and publishes log entries.

    Args:
        count: If set, produce exactly this many logs and stop.
               If None, produce continuously until interrupted.
    """
    connection = connect_to_rabbitmq()
    channel = connection.channel()

    # Declare the queue (idempotent — safe to call multiple times)
    # durable=True ensures the queue survives broker restarts
    channel.queue_declare(queue=settings.RABBITMQ_QUEUE, durable=True)
    logger.info(f"📤 Publishing to queue: '{settings.RABBITMQ_QUEUE}'")

    produced = 0
    try:
        while not _shutdown_requested:
            # Check if we've hit the target count
            if count is not None and produced >= count:
                logger.info(f"Reached target count ({count}). Stopping.")
                break

            # Generate and serialize the log entry
            log_entry = generate_log_entry()
            message_body = json.dumps(log_entry)

            # Publish with persistence — messages survive broker restarts
            channel.basic_publish(
                exchange="",                          # Default exchange
                routing_key=settings.RABBITMQ_QUEUE,  # Direct to queue
                body=message_body,
                properties=pika.BasicProperties(
                    delivery_mode=pika.DeliveryMode.Persistent,  # Survive restarts
                    content_type="application/json",
                ),
            )

            produced += 1
            logger.info(
                f"[{produced}] Published: "
                f"[{log_entry['level']}] {log_entry['service']} — "
                f"{log_entry['message'][:80]}"
            )

            # Wait before sending the next log
            time.sleep(settings.PRODUCER_INTERVAL)

    except AMQPChannelError as e:
        logger.error(f"Channel error during publish: {e}")
        raise
    except Exception as e:
        logger.error(f"Unexpected error: {e}", exc_info=True)
        raise
    finally:
        # Always clean up the connection
        if connection and connection.is_open:
            connection.close()
            logger.info("🔌 RabbitMQ connection closed.")

    logger.info(f"📊 Total logs produced: {produced}")


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------
def main():
    """Parse arguments and start the producer."""
    parser = argparse.ArgumentParser(
        description="AI Log Intelligence — Log Producer",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python -m producer.producer              # Continuous mode
  python -m producer.producer --count 10   # Produce 10 logs and stop
  python -m producer.producer --count 5    # Quick smoke test
        """,
    )
    parser.add_argument(
        "--count", "-c",
        type=int,
        default=None,
        help="Number of logs to produce (default: continuous)",
    )

    args = parser.parse_args()

    logger.info("=" * 60)
    logger.info("🚀 AI Log Intelligence — Producer Starting")
    logger.info(f"   RabbitMQ:  {settings.RABBITMQ_HOST}:{settings.RABBITMQ_PORT}")
    logger.info(f"   Queue:     {settings.RABBITMQ_QUEUE}")
    logger.info(f"   Interval:  {settings.PRODUCER_INTERVAL}s")
    logger.info(f"   Mode:      {'Continuous' if args.count is None else f'{args.count} logs'}")
    logger.info("=" * 60)

    publish_logs(count=args.count)


if __name__ == "__main__":
    main()
