<![CDATA[# 🧠 AI Log Intelligence System (AIOps Lite)

> A production-grade, distributed log intelligence pipeline that generates, streams, analyzes, stores, and queries application logs in real-time — powered by RabbitMQ, OpenSearch, FastAPI, and optionally LLMs.

![Python](https://img.shields.io/badge/Python-3.11+-blue?logo=python&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-0.115-009688?logo=fastapi&logoColor=white)
![RabbitMQ](https://img.shields.io/badge/RabbitMQ-3.13-FF6600?logo=rabbitmq&logoColor=white)
![OpenSearch](https://img.shields.io/badge/OpenSearch-2.18-005EB8?logo=opensearch&logoColor=white)
![Docker](https://img.shields.io/badge/Docker-Compose-2496ED?logo=docker&logoColor=white)
![License](https://img.shields.io/badge/License-MIT-green)

---

## 📑 Table of Contents

- [Overview](#-overview)
- [Architecture](#-architecture)
- [Data Flow](#-data-flow)
- [Project Structure](#-project-structure)
- [Prerequisites](#-prerequisites)
- [Quick Start](#-quick-start)
- [Running Individual Components](#-running-individual-components)
- [API Reference](#-api-reference)
- [LLM Integration](#-llm-integration)
- [Docker Deployment](#-docker-deployment)
- [Integration Testing](#-integration-testing)
- [Configuration Reference](#-configuration-reference)
- [Monitoring & Dashboards](#-monitoring--dashboards)
- [Troubleshooting](#-troubleshooting)
- [Future Improvements](#-future-improvements)
- [Tech Stack](#-tech-stack)
- [Resume Bullet Points](#-resume-bullet-points)

---

## 🎯 Overview

The **AI Log Intelligence System** is a distributed, event-driven pipeline that simulates real-world AIOps workflows. It demonstrates how modern organizations ingest, analyze, and search application logs at scale.

### What it does

| Stage | Component | Technology |
|-------|-----------|------------|
| **Generate** | Producer generates realistic microservice logs | Python + pika |
| **Stream** | Logs flow through a message queue | RabbitMQ (AMQP) |
| **Analyze** | Rule-based engine detects issues & suggests fixes | Regex + Strategy pattern |
| **Store** | Enriched logs indexed for full-text search | OpenSearch |
| **Query** | REST API exposes logs, search, and analytics | FastAPI |
| **Extend** | Optional LLM integration for novel pattern detection | Ollama / OpenAI |

### Key features

- 🔄 **Event-driven architecture** — decoupled producer/consumer via message queue
- 🧠 **18 analysis rules** covering critical, high, medium, and low severity patterns
- 🔍 **Full-text search** with fuzzy matching and relevance scoring
- 📊 **Aggregated statistics** — severity distribution, top services, issue breakdown
- 🤖 **LLM-ready** — hybrid analyzer (rules first, LLM as fallback for unknown patterns)
- 🐳 **Fully containerized** — single `docker compose up` deploys everything
- ✅ **Production patterns** — retry logic, graceful shutdown, health checks, manual ACK

---

## 🏗️ Architecture

```
┌──────────────────────────────────────────────────────────────────┐
│                    AI Log Intelligence System                     │
├──────────────────────────────────────────────────────────────────┤
│                                                                   │
│  ┌───────────┐     ┌──────────────┐     ┌───────────────────┐   │
│  │  Producer  │────▶│   RabbitMQ   │────▶│     Consumer      │   │
│  │           │AMQP │  queue: logs  │AMQP │                   │   │
│  │ Generates │     │              │     │  ┌─────────────┐  │   │
│  │ realistic │     │ • Buffering  │     │  │  Analyzer   │  │   │
│  │ logs      │     │ • Persistence│     │  │ (Rules/LLM) │  │   │
│  └───────────┘     │ • Retry      │     │  └──────┬──────┘  │   │
│                     └──────────────┘     │         │         │   │
│                                          │  ┌──────▼──────┐  │   │
│  ┌───────────┐     ┌──────────────┐     │  │  Storage    │  │   │
│  │  FastAPI  │────▶│  OpenSearch  │◀────│  │ (OpenSearch)│  │   │
│  │  REST API │query│  Index: logs │store │  └─────────────┘  │   │
│  │           │     │              │     └───────────────────┘   │
│  │ /logs     │     │ • Full-text  │                              │
│  │ /search   │     │ • Aggregates │                              │
│  │ /stats    │     │ • Analytics  │                              │
│  └───────────┘     └──────────────┘                              │
│                                                                   │
└──────────────────────────────────────────────────────────────────┘
```

---

## 🔄 Data Flow

```
Step 1: Producer generates a log entry
   { "timestamp": "...", "service": "auth-service", "level": "ERROR",
     "message": "Connection timeout after 30s to database primary" }
        │
        ▼
Step 2: Published to RabbitMQ (queue: "logs", persistent message)
        │
        ▼
Step 3: Consumer receives message (manual ACK, prefetch=1)
        │
        ▼
Step 4: Analyzer detects issue
   { "issue": "connection_timeout", "severity": "high",
     "suggested_fix": "Check network connectivity...",
     "analyzer": "rule_based", "confidence": 0.90 }
        │
        ▼
Step 5: Enriched document stored in OpenSearch
   Original log + analysis + ingested_at metadata
        │
        ▼
Step 6: Queryable via REST API
   GET /logs           → List all logs
   GET /logs/search?q= → Full-text search
   GET /logs/stats     → Aggregated analytics
```

---

## 📁 Project Structure

```
ai-log-intelligence-system/
│
├── producer/                    # Log generation & RabbitMQ publishing
│   ├── __init__.py
│   ├── producer.py              # Main producer — generates & publishes logs
│   ├── config.py                # Service names, log templates, placeholders
│   └── Dockerfile               # Container image for the producer
│
├── consumer/                    # Message consumption & processing pipeline
│   ├── __init__.py
│   ├── consumer.py              # RabbitMQ consumer with manual ACK/NACK
│   ├── analyzer.py              # Rule-based + LLM log analysis engine
│   ├── config.py                # Prefetch, retry, pipeline feature flags
│   └── Dockerfile               # Container image for the consumer
│
├── api/                         # REST API layer
│   ├── __init__.py
│   ├── app.py                   # FastAPI application factory + lifecycle
│   ├── routes.py                # Endpoint definitions (5 routes)
│   └── Dockerfile               # Container image for the API
│
├── storage/                     # OpenSearch persistence layer
│   ├── __init__.py
│   ├── opensearch_client.py     # Client singleton, store/query functions
│   └── schemas.py               # Index mapping — field types & analyzers
│
├── config/                      # Centralized configuration
│   ├── __init__.py
│   └── settings.py              # Frozen dataclass loading from .env
│
├── docker-compose.yml           # Full infrastructure + app services
├── integration_test.py          # 8-stage end-to-end pipeline test
├── requirements.txt             # Pinned Python dependencies
├── .env                         # Environment variables (not committed)
├── .gitignore                   # Python + Docker + IDE exclusions
└── README.md                    # You are here
```

---

## 📋 Prerequisites

| Requirement | Version | Purpose |
|-------------|---------|---------|
| **Docker Desktop** | 4.0+ | Runs RabbitMQ & OpenSearch containers |
| **Python** | 3.11+ | Runs producer, consumer, and API |
| **pip** | Latest | Installs Python dependencies |
| **Git** | Any | Version control |

> **Note:** If running fully in Docker (recommended), only Docker Desktop is required.

---

## 🚀 Quick Start

### 1. Clone the repository

```bash
git clone https://github.com/AshwinKumarBV-git/ai-log-intelligence-system.git
cd ai-log-intelligence-system
```

### 2. Start infrastructure services

```bash
docker compose up -d
```

This starts:
- **RabbitMQ** on ports `5672` (AMQP) and `15672` (Management UI)
- **OpenSearch** on port `9200`
- **OpenSearch Dashboards** on port `5601`

Wait for all services to be healthy:

```bash
docker compose ps --format "table {{.Name}}\t{{.Status}}"
```

Expected output:

```
NAME               STATUS
aiops-dashboards   Up (running)
aiops-opensearch   Up (healthy)
aiops-rabbitmq     Up (healthy)
```

### 3. Install Python dependencies

```bash
pip install -r requirements.txt
```

### 4. Start the API server

```bash
python -m api.app
```

The API is now available at `http://localhost:8000`.

### 5. Start the consumer (new terminal)

```bash
python -m consumer.consumer
```

### 6. Produce some test logs (new terminal)

```bash
# Produce 20 logs (one every 2 seconds)
python -m producer.producer --count 20

# Or run continuously (Ctrl+C to stop)
python -m producer.producer
```

### 7. View results

| Resource | URL |
|----------|-----|
| 📄 **API — All Logs** | http://localhost:8000/logs |
| 🔍 **API — Search** | http://localhost:8000/logs/search?q=timeout |
| 📊 **API — Statistics** | http://localhost:8000/logs/stats |
| 📚 **API — Swagger Docs** | http://localhost:8000/docs |
| 🐰 **RabbitMQ Dashboard** | http://localhost:15672 (guest/guest) |
| 📈 **OpenSearch Dashboards** | http://localhost:5601 |

---

## 🛠️ Running Individual Components

### Producer

```bash
# Continuous mode (produces logs until Ctrl+C)
python -m producer.producer

# Fixed count mode (produce exactly N logs and stop)
python -m producer.producer --count 10

# Help
python -m producer.producer --help
```

**What it does:** Generates realistic log entries from 8 simulated microservices with weighted log levels (INFO 50%, CRITICAL 5%) and 30+ parameterized message templates.

### Consumer

```bash
# Start consuming (blocks until Ctrl+C)
python -m consumer.consumer
```

**What it does:** Subscribes to the RabbitMQ `logs` queue, processes each message through the analysis pipeline (Analyze → Store), and sends ACK/NACK based on success/failure. Auto-reconnects on connection loss.

### API Server

```bash
# With auto-reload (development)
python -m api.app

# With uvicorn directly
uvicorn api.app:app --reload --host 0.0.0.0 --port 8000
```

### Config Verification

```bash
# Verify all environment variables are loaded correctly
python -m config.settings
```

### Analyzer Self-Test

```bash
# Run 8 test cases through all analysis rules
python -m consumer.analyzer
```

### Storage Self-Test

```bash
# Test OpenSearch connection, index creation, store, retrieve, and search
python -m storage.opensearch_client
```

---

## 📡 API Reference

### `GET /` — Health Check

Returns service status and OpenSearch connectivity.

```bash
curl http://localhost:8000/
```

```json
{
  "status": "healthy",
  "service": "ai-log-intelligence-api",
  "opensearch": {
    "connected": true,
    "version": "2.18.0",
    "url": "http://localhost:9200"
  }
}
```

---

### `GET /logs` — Fetch Recent Logs

Retrieves recent logs with optional filtering.

**Query Parameters:**

| Param | Type | Default | Description |
|-------|------|---------|-------------|
| `size` | int | 50 | Number of logs to return (1-500) |
| `service` | string | — | Filter by service name |
| `level` | string | — | Filter by log level (DEBUG, INFO, WARNING, ERROR, CRITICAL) |
| `severity` | string | — | Filter by analysis severity (low, medium, high, critical) |

```bash
# All recent logs
curl http://localhost:8000/logs

# Filter by service and level
curl "http://localhost:8000/logs?service=auth-service&level=ERROR&size=10"

# Filter by analysis severity
curl "http://localhost:8000/logs?severity=critical"
```

**Response:**

```json
{
  "total": 42,
  "returned": 10,
  "logs": [
    {
      "id": "abc123",
      "timestamp": "2026-04-05T10:00:00Z",
      "service": "auth-service",
      "level": "ERROR",
      "message": "Connection timeout after 30s to database primary",
      "analysis": {
        "issue": "connection_timeout",
        "severity": "high",
        "suggested_fix": "Check network connectivity...",
        "analyzer": "rule_based",
        "matched_rule": "timeout_detection",
        "confidence": 0.90
      },
      "ingested_at": "2026-04-05T10:00:01Z"
    }
  ]
}
```

---

### `GET /logs/search?q=` — Full-Text Search

Searches across log messages, analysis results, and service names with fuzzy matching.

```bash
# Search for timeout-related logs
curl "http://localhost:8000/logs/search?q=timeout"

# Search for memory issues
curl "http://localhost:8000/logs/search?q=memory+leak"

# With result limit
curl "http://localhost:8000/logs/search?q=payment&size=5"
```

---

### `GET /logs/stats` — Aggregated Statistics

Returns severity distribution, log level counts, top services, and issue breakdown.

```bash
curl http://localhost:8000/logs/stats
```

```json
{
  "total_logs": 150,
  "severity_distribution": {
    "low": 95,
    "medium": 30,
    "high": 20,
    "critical": 5
  },
  "level_distribution": {
    "INFO": 75,
    "DEBUG": 30,
    "WARNING": 23,
    "ERROR": 15,
    "CRITICAL": 7
  },
  "top_services": {
    "auth-service": 22,
    "payment-gateway": 20,
    "order-service": 18
  },
  "issues_breakdown": {
    "none_detected": 95,
    "connection_timeout": 12,
    "high_memory_usage": 8
  }
}
```

---

### `GET /logs/{log_id}` — Get Log by ID

Retrieves a single log entry by its OpenSearch document ID.

```bash
curl http://localhost:8000/logs/abc123
```

---

## 🤖 LLM Integration

The system supports a **hybrid analysis mode** — rule-based for known patterns, LLM for novel ones.

### How it works

```
Incoming log
    │
    ├── Rule matches? ──YES──▶ Return rule result (⚡ fast, free)
    │
    ├── Log level WARNING/ERROR/CRITICAL?
    │       │
    │       YES──▶ Call LLM ──▶ Succeeded? ──YES──▶ Return LLM result
    │                               │
    │                               NO──▶ Return "none_detected"
    │
    └── INFO/DEBUG ──▶ Return "none_detected" (no LLM call needed)
```

### Supported LLM providers

| Provider | API Type | Example URL |
|----------|----------|-------------|
| **Ollama** (local, free) | `/api/generate` | `http://localhost:11434/api/generate` |
| **OpenAI** | `/v1/chat/completions` | `https://api.openai.com/v1/chat/completions` |
| **Azure OpenAI** | OpenAI-compatible | Your Azure endpoint |
| **vLLM** | OpenAI-compatible | `http://localhost:8080/v1/chat/completions` |
| **LM Studio** | OpenAI-compatible | `http://localhost:1234/v1/chat/completions` |

### Enable LLM analysis

1. **Install Ollama** (recommended for local use):

   ```bash
   # Download from https://ollama.com
   ollama pull llama2
   ```

2. **Update `.env`:**

   ```env
   LLM_API_URL=http://localhost:11434/api/generate
   LLM_MODEL=llama2
   LLM_ENABLED=true
   ```

3. **Restart the consumer** — it will now use the HybridAnalyzer.

### Three analyzer modes

| Mode | Config | Behavior |
|------|--------|----------|
| **Rule-only** | `LLM_ENABLED=false` (default) | Fast, deterministic, 18 built-in rules |
| **LLM-only** | Use `LLMAnalyzer` directly | All logs sent to LLM (slow, expensive) |
| **Hybrid** | `LLM_ENABLED=true` (recommended) | Rules first, LLM fallback for unknowns |

---

## 🐳 Docker Deployment

### Full-stack deployment (recommended)

Deploy everything — infrastructure + application — with a single command:

```bash
docker compose up -d --build
```

This starts 6 containers:

| Container | Service | Port |
|-----------|---------|------|
| `aiops-rabbitmq` | Message broker | 5672, 15672 |
| `aiops-opensearch` | Search engine | 9200 |
| `aiops-dashboards` | OpenSearch UI | 5601 |
| `aiops-producer` | Log generator | — |
| `aiops-consumer` | Log processor | — |
| `aiops-api` | REST API | 8000 |

### Infrastructure only

If you want to run the Python services locally (for development):

```bash
# Start only RabbitMQ + OpenSearch + Dashboards
docker compose up -d rabbitmq opensearch opensearch-dashboards
```

### Useful Docker commands

```bash
# Check all service statuses
docker compose ps

# View logs from a specific service
docker compose logs -f consumer

# Restart a single service
docker compose restart producer

# Stop everything (keep data)
docker compose down

# Stop everything (delete data volumes)
docker compose down -v

# Rebuild after code changes
docker compose up -d --build
```

---

## 🧪 Integration Testing

Run the comprehensive 8-stage integration test:

```bash
python integration_test.py
```

**Prerequisites:** RabbitMQ, OpenSearch, and the API must be running.

### Test stages

| Stage | What it tests |
|-------|---------------|
| 1. Infrastructure | RabbitMQ and OpenSearch connectivity |
| 2. Index Reset | Delete and recreate the `logs` index with schema |
| 3. Log Generation | Generate 10 test logs with valid schema |
| 4. Analysis | Run all 10 logs through the analyzer |
| 5. Storage | Store all logs + analyses in OpenSearch |
| 6. Retrieval | Verify `get_all_logs()` returns stored data |
| 7. Search | Full-text search for "timeout", "error", "memory", "service" |
| 8. API | Test all 5 REST endpoints (health, logs, filter, search, stats) |

### Expected output

```
======================================================================
📊 INTEGRATION TEST REPORT
======================================================================
  ✅ PASS RabbitMQ connection
  ✅ PASS OpenSearch connection — v2.18.0
  ✅ PASS Index reset — 'logs' created with schema
  ✅ PASS Generate logs — 10 logs, levels: {INFO, WARNING, ERROR, ...}
  ✅ PASS Analyze logs — Severities: {low: 7, medium: 2, high: 1}
  ✅ PASS Store logs — 10/10 docs indexed
  ✅ PASS Retrieve logs — Retrieved 10, all have analysis: True
  ✅ PASS Search 'timeout' — 1 results
  ✅ PASS GET / — status=healthy
  ✅ PASS GET /logs — total=10, returned=5
  ✅ PASS GET /logs/stats — total=10
----------------------------------------------------------------------
  Total: 15 | Passed: 15 | Failed: 0

  🎉 ALL TESTS PASSED — Pipeline is fully operational!
======================================================================
```

---

## ⚙️ Configuration Reference

All configuration is managed via environment variables in `.env`:

### RabbitMQ

| Variable | Default | Description |
|----------|---------|-------------|
| `RABBITMQ_HOST` | `localhost` | RabbitMQ hostname |
| `RABBITMQ_PORT` | `5672` | AMQP port |
| `RABBITMQ_USER` | `guest` | Authentication username |
| `RABBITMQ_PASSWORD` | `guest` | Authentication password |
| `RABBITMQ_QUEUE` | `logs` | Queue name for log messages |

### OpenSearch

| Variable | Default | Description |
|----------|---------|-------------|
| `OPENSEARCH_HOST` | `localhost` | OpenSearch hostname |
| `OPENSEARCH_PORT` | `9200` | REST API port |
| `OPENSEARCH_INDEX` | `logs` | Index name for log documents |

### FastAPI

| Variable | Default | Description |
|----------|---------|-------------|
| `API_HOST` | `0.0.0.0` | API bind address |
| `API_PORT` | `8000` | API port |

### Producer

| Variable | Default | Description |
|----------|---------|-------------|
| `PRODUCER_INTERVAL` | `2` | Seconds between generated logs |

### LLM (Optional)

| Variable | Default | Description |
|----------|---------|-------------|
| `LLM_API_URL` | *(empty)* | LLM API endpoint URL |
| `LLM_MODEL` | *(empty)* | Model name (e.g., `llama2`) |
| `LLM_ENABLED` | `false` | Enable hybrid LLM analysis |

---

## 📈 Monitoring & Dashboards

### RabbitMQ Management UI

**URL:** http://localhost:15672 | **Credentials:** `guest` / `guest`

Monitor:
- Queue depth (messages waiting)
- Consumer count and throughput
- Message publish/delivery rates
- Connection health

### OpenSearch Dashboards

**URL:** http://localhost:5601

Explore:
- Create index patterns for the `logs` index
- Build visualizations (severity pie charts, time histograms)
- Run ad-hoc queries with Dev Tools

### FastAPI Swagger UI

**URL:** http://localhost:8000/docs

Interactive API documentation — test all endpoints directly from the browser.

---

## 🔧 Troubleshooting

### OpenSearch won't start

```
Container aiops-opensearch: Error / Restarting
```

**Fix:** Check Docker logs:

```bash
docker logs aiops-opensearch
```

Common causes:
- **Missing `OPENSEARCH_INITIAL_ADMIN_PASSWORD`** — already configured in `docker-compose.yml`
- **Insufficient memory** — OpenSearch needs at least 512MB. Increase Docker Desktop memory allocation.
- **`vm.max_map_count` too low** (Linux) — run `sudo sysctl -w vm.max_map_count=262144`

### Consumer not processing messages

**Check:** Is the consumer connected to the right queue?

```bash
# Verify queue has messages
curl -u guest:guest http://localhost:15672/api/queues/%2F/logs
```

**Check:** Is OpenSearch reachable from the consumer?

```bash
curl http://localhost:9200/_cluster/health
```

### API returns 500 errors

**Check:** Is OpenSearch running and healthy?

```bash
docker compose ps --format "table {{.Name}}\t{{.Status}}"
```

**Check:** Does the `logs` index exist?

```bash
curl http://localhost:9200/logs/_count
```

### Producer fails to connect

**Check:** Is RabbitMQ healthy?

```bash
docker compose ps rabbitmq
```

The producer has built-in retry with exponential backoff (5 attempts). If RabbitMQ is not ready, it will keep trying.

---

## 🚀 Future Improvements

### Short-term enhancements

- [ ] **Alerting System** — Send Slack/PagerDuty notifications for CRITICAL severity logs
- [ ] **Log correlation** — Group related logs by request ID or trace ID
- [ ] **Rate-based anomaly detection** — Alert when error rate exceeds baseline
- [ ] **Dead letter queue** — Route unparseable messages to a DLQ for inspection
- [ ] **Grafana dashboards** — Real-time monitoring with pre-built dashboards

### Medium-term features

- [ ] **Multi-tenant support** — Separate log indices per team/environment
- [ ] **Log retention policies** — Auto-delete logs older than N days using ISM
- [ ] **Authentication & RBAC** — Secure the API with JWT tokens and role-based access
- [ ] **Webhook ingestion** — Accept logs via HTTP POST (not just RabbitMQ)
- [ ] **Batch ingestion** — Bulk index for high-throughput scenarios

### Long-term vision

- [ ] **ML anomaly detection** — Train models on historical log patterns
- [ ] **Root cause analysis (RCA)** — Correlate across services to identify root causes
- [ ] **Predictive alerting** — Forecast issues before they happen based on trends
- [ ] **Kubernetes operator** — Deploy and manage the system on K8s natively
- [ ] **OpenTelemetry integration** — Unified logs, metrics, and traces

### Architecture improvements

- [ ] **Horizontal scaling** — Multiple consumer instances for parallel processing
- [ ] **Schema registry** — Version control for log schemas (Apache Avro)
- [ ] **CDC (Change Data Capture)** — Stream changes from OpenSearch to downstream systems
- [ ] **Event sourcing** — Full audit trail of all log processing decisions

---

## 🧰 Tech Stack

| Technology | Role | Why chosen |
|------------|------|------------|
| **Python 3.11** | Runtime | Type hints, async support, dataclasses |
| **RabbitMQ 3.13** | Message broker | Reliable, persistent, management UI, AMQP standard |
| **OpenSearch 2.18** | Search & analytics | Full-text search, aggregations, OpenSearch Dashboards |
| **FastAPI 0.115** | REST API | Async, auto-generated docs, Pydantic validation |
| **pika 1.3** | RabbitMQ client | Official Python AMQP library |
| **Docker Compose** | Orchestration | Single-command deployment, isolated networking |
| **Pydantic 2.10** | Validation | Schema validation at API boundaries |

---

## 📝 Resume Bullet Points

> Use these to describe this project on your resume or portfolio:

- **Designed and built a distributed AIOps pipeline** processing real-time application logs through RabbitMQ → OpenSearch → FastAPI, demonstrating event-driven architecture and clean separation of concerns

- **Implemented a hybrid log analysis engine** with 18 rule-based pattern detectors (regex, priority-ordered) and an LLM fallback layer supporting Ollama and OpenAI-compatible APIs

- **Built a full-text search API** with FastAPI, featuring dynamic query filtering, fuzzy search, and server-side aggregations across OpenSearch indices

- **Containerized a 6-service distributed system** using Docker Compose with health checks, persistent volumes, isolated networking, and environment-driven configuration

- **Applied production-grade reliability patterns** including exponential backoff retry, manual message acknowledgment, graceful shutdown, circuit-breaker-ready design, and comprehensive error handling

---

## 📄 License

This project is available under the [MIT License](LICENSE).

---

<p align="center">
  Built with ❤️ for learning distributed systems, AIOps, and production engineering.
</p>
]]>