"""
storage/schemas.py — OpenSearch Index Schemas
===============================================

Defines the index mapping (schema) for log documents stored in OpenSearch.

WHY EXPLICIT MAPPINGS?
    Without a mapping, OpenSearch "guesses" field types on first insert
    (dynamic mapping). This often goes wrong:
      - Timestamps become strings → date range queries fail
      - Numbers become long → you can't do float math
      - Text fields get wrong analyzers → search quality suffers

    By defining the mapping upfront, we:
      1. Control how each field is indexed and searched
      2. Prevent type conflicts when different logs have different shapes
      3. Enable efficient queries (keyword vs. full-text, date ranges, etc.)

FIELD TYPES EXPLAINED:
    - "keyword":  Exact-match only, no tokenization. For filtering/aggregation.
                  Example: service="auth-service" (not split into "auth" and "service")
    - "text":     Full-text searchable, tokenized by analyzer.
                  Example: message="Connection timeout" → finds "timeout" alone
    - "date":     ISO 8601 timestamps. Enables range queries (last 24h, etc.)
    - "float":    Floating point numbers. For confidence scores, metrics.
"""

# ---------------------------------------------------------------------------
# Index settings — controls shards, replicas, and analysis
# ---------------------------------------------------------------------------
INDEX_SETTINGS = {
    "index": {
        # Single shard is fine for dev. Production: scale based on data volume.
        "number_of_shards": 1,

        # Zero replicas for dev (single node). Production: set to 1+.
        "number_of_replicas": 0,

        # Refresh interval — how often new docs become searchable.
        # Default 1s is fine for near-real-time search.
        "refresh_interval": "1s",
    }
}

# ---------------------------------------------------------------------------
# Index mapping — defines the schema for log documents
# ---------------------------------------------------------------------------
INDEX_MAPPING = {
    "properties": {

        # ── Original log fields ──────────────────────────────────
        "timestamp": {
            "type": "date",
            # Accepts ISO 8601 with timezone and epoch millis as fallback
            "format": "strict_date_optional_time||epoch_millis",
        },
        "service": {
            "type": "keyword",
            # keyword = exact match. Enables: filter by service, aggregate by service
        },
        "level": {
            "type": "keyword",
            # keyword = exact match. Enables: filter by ERROR, count by level
        },
        "message": {
            "type": "text",
            # text = full-text searchable. Enables: search for "timeout" in messages
            "analyzer": "standard",
            "fields": {
                "raw": {
                    "type": "keyword",
                    # .raw sub-field = exact match on full message (for aggregation)
                    "ignore_above": 512,
                }
            },
        },

        # ── Analysis result fields ───────────────────────────────
        "analysis": {
            "type": "object",
            "properties": {
                "issue": {
                    "type": "keyword",
                    # Enables: filter by issue type, count issues
                },
                "severity": {
                    "type": "keyword",
                    # Enables: filter by severity, severity distribution charts
                },
                "suggested_fix": {
                    "type": "text",
                    # Full-text searchable remediation text
                },
                "analyzer": {
                    "type": "keyword",
                    # Track which analyzer produced the result (rule_based vs llm)
                },
                "matched_rule": {
                    "type": "keyword",
                    # Which rule fired — useful for rule effectiveness tracking
                },
                "confidence": {
                    "type": "float",
                    # 0.0 - 1.0 confidence score — enables threshold filtering
                },
            },
        },

        # ── Metadata fields ──────────────────────────────────────
        "ingested_at": {
            "type": "date",
            # When the log was stored in OpenSearch (not when it was generated)
            "format": "strict_date_optional_time||epoch_millis",
        },
    }
}

# ---------------------------------------------------------------------------
# Full index body — combines settings + mapping for index creation
# ---------------------------------------------------------------------------
def get_index_body() -> dict:
    """
    Return the complete index creation body.

    Usage:
        client.indices.create(index="logs", body=get_index_body())
    """
    return {
        "settings": INDEX_SETTINGS,
        "mappings": INDEX_MAPPING,
    }
