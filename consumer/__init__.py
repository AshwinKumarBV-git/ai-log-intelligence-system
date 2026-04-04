"""
consumer — RabbitMQ message consumer and log processing pipeline.

Usage:
    python -m consumer.consumer    # Start consuming messages
"""

from consumer.consumer import start_consuming, process_message

__all__ = ["start_consuming", "process_message"]
