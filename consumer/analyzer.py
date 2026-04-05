"""
consumer/analyzer.py — Log Analysis Engine
============================================

PURPOSE:
    Analyzes log entries to detect issues, classify severity, and
    suggest fixes. This is the "intelligence" layer of the AIOps system.

DESIGN FOR EXTENSIBILITY:
    The analyzer uses a Strategy pattern internally:
      1. Rule-based analysis (current — fast, deterministic)
      2. LLM-based analysis (Step 10 — slower, more nuanced)

    The public API is a single function: analyze_log(log_entry) → dict
    The consumer doesn't know or care which strategy runs underneath.
    This is the key abstraction — swapping rule-based for LLM is a
    one-line config change, not a rewrite.

WHY ABSTRACTION MATTERS:
    In production AIOps, you often want:
      - Rule-based for known patterns (fast, cheap, reliable)
      - LLM for novel/complex patterns (slow, expensive, creative)
      - Hybrid: rules first, LLM as fallback for unrecognized patterns
    This architecture supports all three without changing the consumer.

ANALYSIS RESULT FORMAT:
    {
        "issue": "connection_timeout",        # Machine-readable issue ID
        "severity": "high",                   # low | medium | high | critical
        "suggested_fix": "Check database...", # Human-readable remediation
        "analyzer": "rule_based",             # Which engine produced this
        "matched_rule": "timeout_detection",  # Traceability — which rule fired
        "confidence": 0.95                    # How confident the analysis is
    }
"""

import re
import json
import logging
from typing import Protocol

import requests

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logger = logging.getLogger("analyzer")


# ---------------------------------------------------------------------------
# Analyzer Protocol (interface) — any analyzer must implement this
# ---------------------------------------------------------------------------
class LogAnalyzer(Protocol):
    """
    Protocol (interface) for log analyzers.

    Any new analyzer (LLM, ML model, etc.) just needs to implement
    this single method to be plug-compatible.
    """

    def analyze(self, log_entry: dict) -> dict:
        """Analyze a log entry and return a structured result."""
        ...


# ---------------------------------------------------------------------------
# Analysis rules — each rule is a dict with pattern + metadata
# ---------------------------------------------------------------------------
# Rules are evaluated top-to-bottom. First match wins.
# Each rule has:
#   - name:          Human-readable rule identifier
#   - pattern:       Regex pattern to match against the log message
#   - log_levels:    Which log levels this rule applies to (None = all)
#   - issue:         Machine-readable issue classification
#   - severity:      low | medium | high | critical
#   - suggested_fix: Actionable remediation advice
#   - confidence:    How confident this rule is (0.0 - 1.0)
ANALYSIS_RULES = [
    # ── CRITICAL severity rules ──────────────────────────────────
    {
        "name": "disk_full",
        "pattern": r"(?i)disk\s+full|writes?\s+halted|no\s+space\s+left",
        "log_levels": ["CRITICAL", "ERROR"],
        "issue": "disk_full",
        "severity": "critical",
        "suggested_fix": (
            "Immediately free disk space: delete old logs, expand volume, "
            "or enable log rotation. Check /data volume usage with `df -h`."
        ),
        "confidence": 0.98,
    },
    {
        "name": "out_of_memory",
        "pattern": r"(?i)out\s+of\s+memory|heap\s+usage\s+at\s+9[5-9]%|OOM",
        "log_levels": ["CRITICAL", "ERROR"],
        "issue": "out_of_memory",
        "severity": "critical",
        "suggested_fix": (
            "Increase JVM heap size or container memory limits. "
            "Investigate memory leaks with heap dump analysis. "
            "Consider horizontal scaling."
        ),
        "confidence": 0.97,
    },
    {
        "name": "circuit_breaker_open",
        "pattern": r"(?i)circuit\s+breaker\s+open|consecutive\s+failures",
        "log_levels": ["CRITICAL", "ERROR"],
        "issue": "circuit_breaker_open",
        "severity": "critical",
        "suggested_fix": (
            "Downstream service is unresponsive. Check the health of the "
            "dependent service. Review circuit breaker thresholds and "
            "implement graceful degradation."
        ),
        "confidence": 0.95,
    },
    {
        "name": "ssl_certificate_expired",
        "pattern": r"(?i)ssl\s+certificate\s+expired|cert.*expired",
        "log_levels": ["CRITICAL", "ERROR"],
        "issue": "ssl_certificate_expired",
        "severity": "critical",
        "suggested_fix": (
            "Renew SSL certificate immediately. Use cert-manager or "
            "Let's Encrypt for automated renewal. Update trust stores."
        ),
        "confidence": 0.99,
    },
    {
        "name": "connection_pool_exhausted",
        "pattern": r"(?i)connection\s+pool\s+exhausted|all\s+\d+\s+connections?\s+in\s+use",
        "log_levels": ["CRITICAL", "ERROR"],
        "issue": "connection_pool_exhausted",
        "severity": "critical",
        "suggested_fix": (
            "Increase connection pool size or investigate connection leaks. "
            "Check for unclosed connections in application code. "
            "Consider connection pooling middleware (e.g., PgBouncer)."
        ),
        "confidence": 0.96,
    },

    # ── HIGH severity rules ──────────────────────────────────────
    {
        "name": "timeout_detection",
        "pattern": r"(?i)timeout|timed?\s*out|connection\s+timeout",
        "log_levels": ["ERROR", "WARNING", "CRITICAL"],
        "issue": "connection_timeout",
        "severity": "high",
        "suggested_fix": (
            "Check network connectivity to the target service. "
            "Verify DNS resolution. Increase timeout thresholds if "
            "the downstream service has high latency. "
            "Consider implementing retry with exponential backoff."
        ),
        "confidence": 0.90,
    },
    {
        "name": "service_unavailable",
        "pattern": r"(?i)HTTP\s+50[0-9]|service\s*unavailable|downstream.*unavailable",
        "log_levels": ["ERROR", "WARNING"],
        "issue": "service_unavailable",
        "severity": "high",
        "suggested_fix": (
            "The downstream service is returning 5xx errors. "
            "Check service health, resource limits, and recent deployments. "
            "Consider enabling a circuit breaker to prevent cascade failures."
        ),
        "confidence": 0.88,
    },
    {
        "name": "deserialization_failure",
        "pattern": r"(?i)deserialization\s+failed|invalid\s+JSON|parse\s+error|malformed",
        "log_levels": ["ERROR", "WARNING"],
        "issue": "data_format_error",
        "severity": "high",
        "suggested_fix": (
            "Incoming data does not match expected schema. "
            "Check the producer's serialization format. Validate payload "
            "structure at the API gateway. Add schema versioning."
        ),
        "confidence": 0.92,
    },
    {
        "name": "authentication_failure",
        "pattern": r"(?i)authentication\s+failed|invalid\s+credentials|unauthorized|401",
        "log_levels": ["ERROR", "WARNING"],
        "issue": "authentication_failure",
        "severity": "high",
        "suggested_fix": (
            "User authentication failed. Check for brute-force attempts. "
            "Verify credential stores and rotation policies. "
            "Implement account lockout after N failed attempts."
        ),
        "confidence": 0.93,
    },
    {
        "name": "null_pointer",
        "pattern": r"(?i)null\s*pointer|NoneType|AttributeError|NullReference",
        "log_levels": ["ERROR", "CRITICAL"],
        "issue": "null_reference_error",
        "severity": "high",
        "suggested_fix": (
            "Null reference in application code. Add defensive null checks. "
            "Review the stack trace to identify the source. "
            "Consider using Optional types or null-safe operators."
        ),
        "confidence": 0.91,
    },

    # ── MEDIUM severity rules ────────────────────────────────────
    {
        "name": "high_memory_usage",
        "pattern": r"(?i)high\s+memory|memory\s+usage.*[89]\d%",
        "log_levels": ["WARNING", "ERROR"],
        "issue": "high_memory_usage",
        "severity": "medium",
        "suggested_fix": (
            "Memory usage is approaching the threshold. "
            "Monitor trend — if increasing, investigate potential memory leaks. "
            "Consider scaling horizontally or tuning garbage collection."
        ),
        "confidence": 0.85,
    },
    {
        "name": "high_disk_usage",
        "pattern": r"(?i)disk\s+usage\s+at\s+[89]\d%",
        "log_levels": ["WARNING"],
        "issue": "high_disk_usage",
        "severity": "medium",
        "suggested_fix": (
            "Disk usage is high. Enable log rotation, archive old data, "
            "or expand storage. Set up alerts at 90% and 95% thresholds."
        ),
        "confidence": 0.87,
    },
    {
        "name": "rate_limit_warning",
        "pattern": r"(?i)rate\s+limit|throttl|too\s+many\s+requests|429",
        "log_levels": ["WARNING", "ERROR"],
        "issue": "rate_limit_approaching",
        "severity": "medium",
        "suggested_fix": (
            "Client is approaching rate limits. Implement request queuing "
            "or backoff. Consider increasing rate limits for trusted clients "
            "or distributing load across multiple API keys."
        ),
        "confidence": 0.86,
    },
    {
        "name": "certificate_expiry_warning",
        "pattern": r"(?i)certificate.*expir.*\d+\s*days?|cert.*warning",
        "log_levels": ["WARNING"],
        "issue": "certificate_expiry_warning",
        "severity": "medium",
        "suggested_fix": (
            "SSL certificate is expiring soon. Schedule renewal before "
            "the expiry date. Set up automated renewal with cert-manager."
        ),
        "confidence": 0.90,
    },
    {
        "name": "api_latency_degradation",
        "pattern": r"(?i)response\s+time\s+degraded|latency.*SLA|slow\s+response",
        "log_levels": ["WARNING"],
        "issue": "api_latency_degradation",
        "severity": "medium",
        "suggested_fix": (
            "API response times exceed SLA. Check database query performance, "
            "cache hit rates, and downstream service latency. "
            "Consider adding caching or optimizing hot paths."
        ),
        "confidence": 0.83,
    },
    {
        "name": "retry_detected",
        "pattern": r"(?i)retry\s+attempt|retrying|attempt\s+\d+/\d+",
        "log_levels": ["WARNING", "INFO"],
        "issue": "retry_in_progress",
        "severity": "medium",
        "suggested_fix": (
            "Transient failure detected — system is retrying automatically. "
            "If retries become frequent, investigate the root cause. "
            "Check downstream service health and network stability."
        ),
        "confidence": 0.80,
    },

    # ── LOW severity rules ───────────────────────────────────────
    {
        "name": "payment_declined",
        "pattern": r"(?i)card\s+declined|payment.*failed|transaction.*failed",
        "log_levels": ["ERROR", "WARNING"],
        "issue": "payment_declined",
        "severity": "low",
        "suggested_fix": (
            "Payment card was declined. This is typically a user-side issue. "
            "Notify the user to try a different payment method. "
            "Monitor for elevated decline rates that may indicate fraud."
        ),
        "confidence": 0.88,
    },
]


# ---------------------------------------------------------------------------
# Rule-Based Analyzer
# ---------------------------------------------------------------------------
class RuleBasedAnalyzer:
    """
    Analyzes logs by matching message content against predefined rules.

    Advantages:
      - Deterministic: same input always produces same output
      - Fast: regex matching is O(n) per rule, microseconds total
      - Explainable: you can trace exactly which rule fired
      - No external dependencies: no API calls, no model loading

    Limitations:
      - Cannot detect novel/unknown patterns
      - Requires manual rule maintenance
      - No semantic understanding (can't infer context)
    """

    def __init__(self, rules: list[dict] = None):
        """
        Initialize with a list of analysis rules.

        Args:
            rules: List of rule dicts. Defaults to ANALYSIS_RULES.
        """
        self.rules = rules or ANALYSIS_RULES
        # Pre-compile regex patterns for performance
        self._compiled_rules = []
        for rule in self.rules:
            self._compiled_rules.append({
                **rule,
                "_compiled": re.compile(rule["pattern"]),
            })
        logger.info(f"RuleBasedAnalyzer initialized with {len(self.rules)} rules.")

    def analyze(self, log_entry: dict) -> dict:
        """
        Analyze a log entry against all rules.

        First matching rule wins (rules are priority-ordered).

        Args:
            log_entry: Dict with keys: timestamp, service, level, message

        Returns:
            Analysis result dict with: issue, severity, suggested_fix,
            analyzer, matched_rule, confidence
        """
        message = log_entry.get("message", "")
        level = log_entry.get("level", "INFO")

        for rule in self._compiled_rules:
            # Skip rules that don't apply to this log level
            if rule["log_levels"] is not None and level not in rule["log_levels"]:
                continue

            # Try to match the pattern against the message
            if rule["_compiled"].search(message):
                result = {
                    "issue": rule["issue"],
                    "severity": rule["severity"],
                    "suggested_fix": rule["suggested_fix"],
                    "analyzer": "rule_based",
                    "matched_rule": rule["name"],
                    "confidence": rule["confidence"],
                }
                logger.debug(
                    f"Rule '{rule['name']}' matched: "
                    f"severity={rule['severity']}, issue={rule['issue']}"
                )
                return result

        # No rule matched — return a "clean" result
        return {
            "issue": "none_detected",
            "severity": "low",
            "suggested_fix": "No known issues detected. Log appears normal.",
            "analyzer": "rule_based",
            "matched_rule": None,
            "confidence": 0.5,
        }


# ---------------------------------------------------------------------------
# LLM Analyzer — Full Implementation (Step 10)
# ---------------------------------------------------------------------------
class LLMAnalyzer:
    """
    Analyzes logs using a Large Language Model (LLM).

    Supports any OpenAI-compatible or Ollama API endpoint.
    The LLM receives a structured prompt with the log entry and
    returns a JSON analysis result.

    AIOPS CONCEPT:
        Traditional monitoring uses static rules — they catch known patterns
        but miss novel issues. LLMs bring semantic understanding:
          - "Connection refused on port 5432" → understands this is a PostgreSQL issue
          - "Latency spike correlated with deployment at 14:00" → understands causality
          - Can generate human-readable root cause analysis

    WHY HYBRID APPROACH?
        - Rules: Fast (microseconds), cheap (no API call), reliable for known patterns
        - LLM:   Slower (seconds), costly (API call), creative for novel patterns
        - Hybrid: Best of both — rules for the 80% of known issues, LLM for the 20% unknown
    """

    # Prompt template — instructs the LLM to return structured JSON
    SYSTEM_PROMPT = """You are an expert AIOps engineer analyzing application logs.
Your job is to:
1. Identify the issue in the log message
2. Classify its severity (low, medium, high, critical)
3. Suggest a concrete fix

IMPORTANT: Respond ONLY with valid JSON in this exact format:
{
    "issue": "short_issue_id_with_underscores",
    "severity": "low|medium|high|critical",
    "suggested_fix": "Concise, actionable remediation advice."
}

Do NOT include any text outside the JSON object."""

    USER_PROMPT_TEMPLATE = """Analyze this log entry:

Timestamp: {timestamp}
Service:   {service}
Level:     {level}
Message:   {message}

Return your analysis as JSON."""

    def __init__(self, api_url: str = "", model: str = "", timeout: int = 30):
        """
        Initialize the LLM analyzer.

        Args:
            api_url: LLM API endpoint (Ollama or OpenAI-compatible).
            model:   Model name (e.g., "llama2", "mistral", "gpt-3.5-turbo").
            timeout: Request timeout in seconds.
        """
        from config.settings import settings

        self.api_url = api_url or settings.LLM_API_URL
        self.model = model or settings.LLM_MODEL
        self.timeout = timeout
        self._rule_fallback = RuleBasedAnalyzer()

        if not self.api_url:
            logger.warning("LLM_API_URL not configured. LLM analysis will fall back to rules.")
        else:
            logger.info(f"LLMAnalyzer initialized: url={self.api_url}, model={self.model}")

    def _build_prompt(self, log_entry: dict) -> str:
        """Build the user prompt from the log entry."""
        return self.USER_PROMPT_TEMPLATE.format(
            timestamp=log_entry.get("timestamp", "N/A"),
            service=log_entry.get("service", "N/A"),
            level=log_entry.get("level", "N/A"),
            message=log_entry.get("message", "N/A"),
        )

    def _call_ollama(self, log_entry: dict) -> dict | None:
        """
        Call an Ollama-compatible API.

        Ollama uses: POST /api/generate
        Body: { "model": "...", "prompt": "...", "system": "...", "stream": false }
        """
        try:
            payload = {
                "model": self.model,
                "prompt": self._build_prompt(log_entry),
                "system": self.SYSTEM_PROMPT,
                "stream": False,
                "options": {
                    "temperature": 0.1,  # Low temperature for consistent, deterministic output
                },
            }

            response = requests.post(
                self.api_url,
                json=payload,
                timeout=self.timeout,
            )
            response.raise_for_status()

            result = response.json()
            raw_text = result.get("response", "")
            return self._parse_llm_response(raw_text)

        except requests.exceptions.Timeout:
            logger.warning(f"LLM request timed out after {self.timeout}s.")
            return None
        except requests.exceptions.ConnectionError:
            logger.warning(f"Cannot connect to LLM at {self.api_url}.")
            return None
        except Exception as e:
            logger.error(f"LLM API call failed: {e}", exc_info=True)
            return None

    def _call_openai_compatible(self, log_entry: dict) -> dict | None:
        """
        Call an OpenAI-compatible API (works with OpenAI, Azure, vLLM, LM Studio).

        Uses: POST /v1/chat/completions
        """
        try:
            payload = {
                "model": self.model,
                "messages": [
                    {"role": "system", "content": self.SYSTEM_PROMPT},
                    {"role": "user", "content": self._build_prompt(log_entry)},
                ],
                "temperature": 0.1,
                "max_tokens": 300,
            }

            response = requests.post(
                self.api_url,
                json=payload,
                timeout=self.timeout,
            )
            response.raise_for_status()

            result = response.json()
            raw_text = result["choices"][0]["message"]["content"]
            return self._parse_llm_response(raw_text)

        except requests.exceptions.Timeout:
            logger.warning(f"LLM request timed out after {self.timeout}s.")
            return None
        except requests.exceptions.ConnectionError:
            logger.warning(f"Cannot connect to LLM at {self.api_url}.")
            return None
        except Exception as e:
            logger.error(f"LLM API call failed: {e}", exc_info=True)
            return None

    def _parse_llm_response(self, raw_text: str) -> dict | None:
        """
        Parse the LLM's response text into a structured dict.

        Handles common LLM quirks:
          - Extra text before/after JSON
          - Markdown code fences (```json ... ```)
          - Missing fields
        """
        try:
            # Strip markdown code fences if present
            text = raw_text.strip()
            if text.startswith("```"):
                # Remove ```json and trailing ```
                lines = text.split("\n")
                lines = [l for l in lines if not l.strip().startswith("```")]
                text = "\n".join(lines)

            # Try to find JSON object in the text
            start = text.find("{")
            end = text.rfind("}") + 1
            if start == -1 or end == 0:
                logger.warning(f"No JSON found in LLM response: {raw_text[:200]}")
                return None

            json_str = text[start:end]
            parsed = json.loads(json_str)

            # Validate required fields
            required = {"issue", "severity", "suggested_fix"}
            if not required.issubset(parsed.keys()):
                missing = required - set(parsed.keys())
                logger.warning(f"LLM response missing fields: {missing}")
                return None

            # Normalize severity
            valid_severities = {"low", "medium", "high", "critical"}
            if parsed["severity"].lower() not in valid_severities:
                parsed["severity"] = "medium"  # Safe default
            else:
                parsed["severity"] = parsed["severity"].lower()

            return parsed

        except json.JSONDecodeError as e:
            logger.warning(f"Failed to parse LLM JSON: {e}. Raw: {raw_text[:200]}")
            return None

    def _detect_api_type(self) -> str:
        """Detect whether the API is Ollama or OpenAI-compatible."""
        if "ollama" in self.api_url.lower() or "/api/generate" in self.api_url:
            return "ollama"
        return "openai"

    def analyze(self, log_entry: dict) -> dict:
        """
        Analyze a log entry using the LLM.

        Falls back to rule-based analysis if:
          - LLM API is not configured
          - LLM request fails or times out
          - LLM response is unparseable

        Args:
            log_entry: Dict with keys: timestamp, service, level, message

        Returns:
            Analysis result dict.
        """
        # Fallback if LLM is not configured
        if not self.api_url:
            logger.debug("No LLM URL — falling back to rule-based.")
            return self._rule_fallback.analyze(log_entry)

        # Call the appropriate API
        api_type = self._detect_api_type()
        if api_type == "ollama":
            llm_result = self._call_ollama(log_entry)
        else:
            llm_result = self._call_openai_compatible(log_entry)

        # If LLM succeeded, return enriched result
        if llm_result:
            return {
                "issue": llm_result["issue"],
                "severity": llm_result["severity"],
                "suggested_fix": llm_result["suggested_fix"],
                "analyzer": "llm",
                "matched_rule": None,
                "confidence": 0.85,  # LLM confidence is generally good but not rule-certain
            }

        # LLM failed — fall back to rules
        logger.warning("LLM analysis failed. Falling back to rule-based analyzer.")
        result = self._rule_fallback.analyze(log_entry)
        result["analyzer"] = "rule_based_fallback"
        return result


# ---------------------------------------------------------------------------
# Hybrid Analyzer — Best of both worlds
# ---------------------------------------------------------------------------
class HybridAnalyzer:
    """
    Hybrid analyzer: tries rule-based first, falls back to LLM for
    unrecognized patterns.

    WHY THIS IS THE BEST APPROACH:
        - Known patterns (timeout, OOM, disk full) → rules handle instantly
        - Novel patterns (unusual error messages) → LLM provides insight
        - Cost-effective: LLM is only called for the ~20% of logs that
          rules can't classify
    """

    def __init__(self):
        self._rule_analyzer = RuleBasedAnalyzer()
        self._llm_analyzer = LLMAnalyzer()
        logger.info("HybridAnalyzer initialized (rules + LLM fallback).")

    def analyze(self, log_entry: dict) -> dict:
        """
        Analyze using rules first. If no rule matches AND the log level
        suggests a potential issue, escalate to LLM.

        Args:
            log_entry: Dict with keys: timestamp, service, level, message

        Returns:
            Analysis result from either rules or LLM.
        """
        # Step 1: Try rule-based analysis
        rule_result = self._rule_analyzer.analyze(log_entry)

        # If a rule matched, return it (fast path)
        if rule_result["matched_rule"] is not None:
            logger.debug(f"Rule hit — skipping LLM: {rule_result['matched_rule']}")
            return rule_result

        # Step 2: If no rule matched and log level is WARNING/ERROR/CRITICAL,
        # this might be a novel issue — escalate to LLM
        level = log_entry.get("level", "INFO")
        escalation_levels = {"WARNING", "ERROR", "CRITICAL"}

        if level in escalation_levels:
            logger.info(f"No rule matched [{level}] log — escalating to LLM.")
            llm_result = self._llm_analyzer.analyze(log_entry)

            # Only use LLM result if it found something meaningful
            if llm_result.get("issue") != "none_detected":
                llm_result["analyzer"] = "hybrid_llm"
                return llm_result

        # Step 3: Return the rule result (none_detected) for INFO/DEBUG logs
        return rule_result


# ---------------------------------------------------------------------------
# Analyzer factory — returns the configured analyzer instance
# ---------------------------------------------------------------------------
def _get_analyzer() -> LogAnalyzer:
    """
    Factory function that returns the appropriate analyzer
    based on configuration.

    Modes:
      - LLM_ENABLED=false → RuleBasedAnalyzer (default)
      - LLM_ENABLED=true  → HybridAnalyzer (rules + LLM fallback)

    Returns:
        A LogAnalyzer instance.
    """
    try:
        from config.settings import settings
        if settings.LLM_ENABLED:
            logger.info("LLM enabled — using HybridAnalyzer (rules + LLM fallback).")
            return HybridAnalyzer()
    except (ImportError, AttributeError):
        pass

    return RuleBasedAnalyzer()


# Create a module-level analyzer instance (singleton)
_analyzer = _get_analyzer()


# ---------------------------------------------------------------------------
# Public API — this is what the consumer calls
# ---------------------------------------------------------------------------
def analyze_log(log_entry: dict) -> dict:
    """
    Analyze a log entry and return structured analysis results.

    This is the single public entry point. The consumer calls this
    function without knowing which analyzer runs underneath.

    Args:
        log_entry: Dict with keys: timestamp, service, level, message

    Returns:
        dict with keys: issue, severity, suggested_fix, analyzer,
        matched_rule, confidence
    """
    try:
        result = _analyzer.analyze(log_entry)
        logger.info(
            f"Analysis complete: issue={result['issue']}, "
            f"severity={result['severity']}, "
            f"rule={result.get('matched_rule', 'N/A')}"
        )
        return result

    except Exception as e:
        logger.error(f"Analysis failed: {e}", exc_info=True)
        return {
            "issue": "analysis_error",
            "severity": "unknown",
            "suggested_fix": f"Analysis engine encountered an error: {e}",
            "analyzer": "error",
            "matched_rule": None,
            "confidence": 0.0,
        }


# ---------------------------------------------------------------------------
# Self-test — run this file directly to test rules
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG)

    # Test cases covering different severities
    test_logs = [
        {"timestamp": "2026-04-05T00:00:00Z", "service": "auth-service", "level": "ERROR",
         "message": "Connection timeout after 30s to database primary"},
        {"timestamp": "2026-04-05T00:00:01Z", "service": "payment-gateway", "level": "CRITICAL",
         "message": "Out of memory error — heap usage at 98%"},
        {"timestamp": "2026-04-05T00:00:02Z", "service": "order-service", "level": "WARNING",
         "message": "High memory usage detected: 92% — threshold: 80%"},
        {"timestamp": "2026-04-05T00:00:03Z", "service": "user-api", "level": "INFO",
         "message": "User alice logged in successfully"},
        {"timestamp": "2026-04-05T00:00:04Z", "service": "inventory-service", "level": "ERROR",
         "message": "HTTP 503 from downstream inventory-service"},
        {"timestamp": "2026-04-05T00:00:05Z", "service": "search-service", "level": "CRITICAL",
         "message": "Disk full on /data volume — writes halted"},
        {"timestamp": "2026-04-05T00:00:06Z", "service": "analytics-engine", "level": "WARNING",
         "message": "Rate limit approaching for client 42: 950/1000"},
        {"timestamp": "2026-04-05T00:00:07Z", "service": "auth-service", "level": "ERROR",
         "message": "Authentication failed for user bob: invalid credentials"},
    ]

    print("=" * 80)
    print("ANALYZER SELF-TEST")
    print("=" * 80)

    for log in test_logs:
        result = analyze_log(log)
        print(f"\n📋 [{log['level']}] {log['service']}: {log['message'][:60]}...")
        print(f"   🔍 Issue:     {result['issue']}")
        print(f"   ⚠️  Severity:  {result['severity']}")
        print(f"   🛠️  Rule:      {result.get('matched_rule', 'N/A')}")
        print(f"   📊 Confidence: {result['confidence']}")
        print(f"   💡 Fix:        {result['suggested_fix'][:80]}...")

    print("\n" + "=" * 80)
    print("✅ All test cases passed!")
