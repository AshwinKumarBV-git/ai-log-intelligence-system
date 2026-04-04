"""
config/settings.py — Centralized Configuration Management
==========================================================

WHY CENTRALIZE CONFIG?
    1. Single source of truth — every module reads from one place
    2. Environment-driven — behavior changes per environment (dev/staging/prod)
       without touching code
    3. Fail-fast — missing critical config raises an error at startup,
       not 30 minutes into a run when the consumer first tries to connect
    4. Testable — swap configs in tests without monkey-patching env vars
    5. Secure — secrets stay in .env (never committed), not hardcoded

USAGE:
    from config.settings import settings
    print(settings.RABBITMQ_HOST)  # "localhost"
"""

import os
import logging
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

# ---------------------------------------------------------------------------
# Load .env file
# ---------------------------------------------------------------------------
# Walk up from this file's directory to find the project root .env
# This works whether you run from project root or from a subdirectory
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
_ENV_PATH = _PROJECT_ROOT / ".env"

if _ENV_PATH.exists():
    load_dotenv(dotenv_path=_ENV_PATH)
else:
    logging.warning(
        f".env file not found at {_ENV_PATH}. "
        "Falling back to system environment variables."
    )


def _get_env(key: str, default: str | None = None, required: bool = False) -> str:
    """
    Retrieve an environment variable with validation.

    Args:
        key:      Environment variable name.
        default:  Fallback value if not set.
        required: If True, raise an error when the variable is missing.

    Returns:
        The environment variable value as a string.

    Raises:
        EnvironmentError: If a required variable is not set.
    """
    value = os.getenv(key, default)
    if required and value is None:
        raise EnvironmentError(
            f"Required environment variable '{key}' is not set. "
            f"Add it to your .env file or export it in your shell."
        )
    return value


# ---------------------------------------------------------------------------
# Settings dataclass — immutable after creation
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class Settings:
    """
    Immutable application settings loaded from environment variables.

    frozen=True prevents accidental mutation at runtime, which is a
    common source of hard-to-debug configuration bugs in distributed systems.
    """

    # --- RabbitMQ ---
    RABBITMQ_HOST: str = field(default_factory=lambda: _get_env("RABBITMQ_HOST", "localhost"))
    RABBITMQ_PORT: int = field(default_factory=lambda: int(_get_env("RABBITMQ_PORT", "5672")))
    RABBITMQ_USER: str = field(default_factory=lambda: _get_env("RABBITMQ_USER", "guest"))
    RABBITMQ_PASSWORD: str = field(default_factory=lambda: _get_env("RABBITMQ_PASSWORD", "guest"))
    RABBITMQ_QUEUE: str = field(default_factory=lambda: _get_env("RABBITMQ_QUEUE", "logs"))

    # --- OpenSearch ---
    OPENSEARCH_HOST: str = field(default_factory=lambda: _get_env("OPENSEARCH_HOST", "localhost"))
    OPENSEARCH_PORT: int = field(default_factory=lambda: int(_get_env("OPENSEARCH_PORT", "9200")))
    OPENSEARCH_INDEX: str = field(default_factory=lambda: _get_env("OPENSEARCH_INDEX", "logs"))

    # --- FastAPI ---
    API_HOST: str = field(default_factory=lambda: _get_env("API_HOST", "0.0.0.0"))
    API_PORT: int = field(default_factory=lambda: int(_get_env("API_PORT", "8000")))

    # --- Producer ---
    PRODUCER_INTERVAL: int = field(default_factory=lambda: int(_get_env("PRODUCER_INTERVAL", "2")))

    # --- LLM (Optional — Step 10) ---
    LLM_API_URL: str = field(default_factory=lambda: _get_env("LLM_API_URL", ""))
    LLM_MODEL: str = field(default_factory=lambda: _get_env("LLM_MODEL", ""))
    LLM_ENABLED: bool = field(default_factory=lambda: _get_env("LLM_ENABLED", "false").lower() == "true")

    # --- Derived Properties ---

    @property
    def OPENSEARCH_URL(self) -> str:
        """Full OpenSearch URL for client connections."""
        return f"http://{self.OPENSEARCH_HOST}:{self.OPENSEARCH_PORT}"

    @property
    def RABBITMQ_URL(self) -> str:
        """Full AMQP connection URL."""
        return (
            f"amqp://{self.RABBITMQ_USER}:{self.RABBITMQ_PASSWORD}"
            f"@{self.RABBITMQ_HOST}:{self.RABBITMQ_PORT}/"
        )

    def __repr__(self) -> str:
        """Mask sensitive fields in logs."""
        return (
            f"Settings("
            f"RABBITMQ={self.RABBITMQ_HOST}:{self.RABBITMQ_PORT}, "
            f"OPENSEARCH={self.OPENSEARCH_URL}, "
            f"API={self.API_HOST}:{self.API_PORT}, "
            f"LLM_ENABLED={self.LLM_ENABLED}"
            f")"
        )


# ---------------------------------------------------------------------------
# Singleton instance — import this everywhere
# ---------------------------------------------------------------------------
# All modules should do:   from config.settings import settings
settings = Settings()


# ---------------------------------------------------------------------------
# Self-test — run this file directly to verify config loading
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    logger = logging.getLogger(__name__)

    logger.info("=" * 60)
    logger.info("CONFIG VERIFICATION")
    logger.info("=" * 60)
    logger.info(f"Settings: {settings}")
    logger.info(f"RabbitMQ URL:   {settings.RABBITMQ_URL}")
    logger.info(f"OpenSearch URL: {settings.OPENSEARCH_URL}")
    logger.info(f"API endpoint:   {settings.API_HOST}:{settings.API_PORT}")
    logger.info(f"Producer interval: {settings.PRODUCER_INTERVAL}s")
    logger.info(f"LLM enabled:    {settings.LLM_ENABLED}")
    logger.info("=" * 60)
    logger.info("✅ All config values loaded successfully!")
