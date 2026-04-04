"""
producer — Log generation and RabbitMQ publishing module.

Usage:
    python -m producer.producer              # Continuous mode
    python -m producer.producer --count 10   # Produce 10 logs
"""

from producer.producer import generate_log_entry, publish_logs

__all__ = ["generate_log_entry", "publish_logs"]
