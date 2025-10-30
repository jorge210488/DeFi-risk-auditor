# DeFi Risk Auditor

![DeFi Risk Auditor – Overview](https://assets.example.com/screens/deFi-risk-auditor-overview.png)
![DeFi Risk Auditor – Swagger](https://assets.example.com/screens/deFi-risk-auditor-swagger.png)
![DeFi Risk Auditor – Metrics](https://assets.example.com/screens/deFi-risk-auditor-metrics.png)
![DeFi Risk Auditor – ABI Cache](https://assets.example.com/screens/deFi-risk-auditor-abi-cache.png)
![DeFi Risk Auditor – Audit Flow](https://assets.example.com/screens/deFi-risk-auditor-audit-flow.png)
![DeFi Risk Auditor – Jobs](https://assets.example.com/screens/deFi-risk-auditor-jobs.png)

## Description

**DeFi Risk Auditor** is a Python/Flask backend that analyzes smart contracts on EVM networks. It automatically resolves and caches ABIs (via **Etherscan API v2**), performs read-only contract calls, runs an AI-based risk scoring (IsolationForest), and executes long-running audits asynchronously using **Celery** and **Redis**. The service exposes **OpenAPI/Swagger** docs and **Prometheus** metrics for observability.

**Live (Render):** `https://defi-risk-auditor.onrender.com`

- API Docs: `/apidocs/`
- Health: `/healthz`
- Metrics (Prometheus): `/metrics`

---

## Technologies Used

### Backend

- **Flask 3.x**
- **Flask-SQLAlchemy 3.x** + **Flask-Migrate/Alembic**
- **Celery 5.5** with **Redis** (broker + result backend)
- **Web3.py 6.x** (PoA middleware support)
- **scikit-learn**, **joblib**, **numpy** (AI risk scoring)
- **Flasgger** (Swagger UI / OpenAPI)
- **prometheus-flask-exporter** (metrics)
- **requests** (Etherscan integration)
- **python-json-logger** (structured logging)

### Infrastructure

- **Dockerfile** (Python 3.10-slim, non-root user)
- **docker-compose**: `web`, `worker`, `db` (PostgreSQL 15), `redis`
- **Render**: Docker deploy for Web Service (Flask) and Background Worker (Celery)

### Database

- **PostgreSQL 15**
- Key tables:

  - `analysis_jobs` — status/results for background tasks
  - `contract_abis` — cached ABIs (indexed by `address`; includes `network`, `source`, JSON `abi`)
  - `contract_audits` — end-to-end audit results (AI score, risk level, features, summary)

---

## Deployment

- **Backend (Render)**: Docker-based deploy using the repository’s `Dockerfile`.
- **Worker (Render)**: Background Worker using the same image and the Celery command.
- **Managed PostgreSQL** (Render) with `DATABASE_URL`.
- **Redis**: Use a Redis instance/URL compatible with Celery (e.g., `rediss://...` on Render).

> Note: In local `docker-compose`, Redis/DB service names are used (e.g., `redis://redis:6379/0`). In Render, set the corresponding external URLs in environment variables.

---

## How to Run the Application (Local)

### 1) Clone

```bash
git clone https://github.com/your-org/defi-risk-auditor.git
cd defi-risk-auditor
```

### 2) Environment Variables

Create a `.env` file at the project root:

```env
# Redis / Celery
CELERY_BROKER_URL=redis://redis:6379/0
CELERY_RESULT_BACKEND=redis://redis:6379/0

# Postgres
DATABASE_URL=postgresql+psycopg2://app_user:app_pass@db:5432/app_db

# Web3 / Etherscan
WEB3_PROVIDER_URI=https://sepolia.infura.io/v3/<YOUR_INFURA_KEY>
WEB3_CHAIN_ID=11155111
ETHERSCAN_CHAIN_ID=11155111
WEB3_USE_POA=true
ETHERSCAN_NETWORK=sepolia
ETHERSCAN_API_KEY=<YOUR_ETHERSCAN_KEY>

# Optional defaults
CONTRACT_ADDRESS=0x01bb56E6A4deDa43338f8425407743CdCfAC1EA7
CONTRACT_ABI_PATH=/app/app/abi/ERC20.json

# Only for workers that sign TX (not required for read-only calls)
PRIVATE_KEY=0xREPLACE_WITH_YOUR_PRIVATE_KEY

# Diagnostics
DEBUG_METRICS=1
```

### 3) Build & Run with Docker Compose

```bash
docker compose up --build
```

- **web**: applies DB migrations (`flask db upgrade`), then starts `wsgi.py`
- **worker**: applies DB migrations, then starts Celery worker
- **db** and **redis**: healthy checks ensure readiness

**Ports:**

- API: `http://localhost:5050/` (proxied to Flask on port `5000` inside the container)
- Redis: `6379` (exposed in dev)
- Postgres: `5432` (exposed in dev)

---

## Environment Variables

| Variable                                     | Purpose                                              |
| -------------------------------------------- | ---------------------------------------------------- |
| `DATABASE_URL`                               | SQLAlchemy URL to PostgreSQL                         |
| `CELERY_BROKER_URL`, `CELERY_RESULT_BACKEND` | Celery broker/result backend (Redis)                 |
| `WEB3_PROVIDER_URI`                          | RPC endpoint (Sepolia/Infura, etc.)                  |
| `WEB3_CHAIN_ID`, `ETHERSCAN_CHAIN_ID`        | Chain IDs (e.g., 11155111 for Sepolia)               |
| `WEB3_USE_POA`                               | Enable PoA middleware if `true`                      |
| `ETHERSCAN_API_KEY`                          | Etherscan API key                                    |
| `ETHERSCAN_NETWORK`                          | Human label for network (e.g., `sepolia`)            |
| `CONTRACT_ADDRESS`                           | Default contract address (optional)                  |
| `CONTRACT_ABI_PATH`                          | Local fallback path to ABI JSON (optional)           |
| `PRIVATE_KEY`                                | Only needed by Celery worker for signed transactions |
| `DEBUG_METRICS`                              | If set, enables Prometheus setup hints               |

---

## API Overview

**Base URL (Render):** `https://defi-risk-auditor.onrender.com`

### System

- `GET /healthz` — health check
- `GET /apidocs/` — Swagger UI
- `GET /apispec_1.json` — OpenAPI spec
- `GET /metrics` — Prometheus metrics

### Blockchain / ABI

- `GET /api/blockchain/abi?address=0x...&network=sepolia|mainnet`
  Resolve ABI from cache or Etherscan v2 and return JSON list.

- `POST /api/blockchain/abi`
  Save/overwrite ABI manually in DB cache.

  ```json
  {
    "address": "0x...",
    "network": "sepolia",
    "abi": [ { "type": "function", "name": "symbol", ... } ],
    "source": "manual"
  }
  ```

- `GET /api/blockchain/info`
  Basic chain info (e.g., `chain_id`, `latest_block`).

- `POST /api/blockchain/call`
  Perform a **read-only** contract call using ABI from: body `abi` → file → cache → Etherscan v2.

  ```json
  {
    "contract_address": "0x...",
    "network": "sepolia",
    "function": "symbol",
    "args": [],
    "force_refresh": false,
    "cache_manual": false
  }
  ```

### AI

- `POST /api/ai/predict`
  IsolationForest-based demo risk score.

  ```json
  { "feature1": 0.3, "feature2": -0.4 }
  ```

### Audits (asynchronous)

- `POST /api/audit/start`
  Enqueue an audit for `address`/`network`. Returns a `job_id`.

  ```json
  {
    "address": "0x...",
    "network": "sepolia",
    "force_refresh": true
  }
  ```

- `GET /api/audit/status/<job_id>`
  Poll job state and result (when completed).

- `GET /api/audit/<audit_id>`
  Retrieve full audit (summary, features, AI score, risk level).

- `GET /api/audit/`
  List audits (optionally filter by `?address=`).

### Jobs (generic)

- `POST /procesar`
  Example route to enqueue a background job; returns `job_id`.

- `GET /jobs/<job_id>`
  Check generic job status/result.

> Exact payloads and response shapes are visible in **Swagger** at `/apidocs/`.

---

## Sample Usage (cURL)

> On macOS/Linux: `BASE=https://defi-risk-auditor.onrender.com`
> On PowerShell: `$BASE = "https://defi-risk-auditor.onrender.com"`

**Health**

```bash
curl -s "$BASE/healthz"
```

**Swagger**

```bash
curl -I "$BASE/apidocs/"
```

**Metrics (Prometheus)**

```bash
curl -s "$BASE/metrics" | head -n 30
```

**Save ABI manually**

```bash
curl -s -X POST "$BASE/api/blockchain/abi" \
  -H "Content-Type: application/json" \
  -d '{
        "address":"0x3245166A4399A34A76cc9254BC13Aae3dA07e27b",
        "network":"mainnet",
        "abi":[
          {"type":"function","name":"symbol","stateMutability":"view","inputs":[],"outputs":[{"type":"string","name":""}]}
        ],
        "source":"manual"
      }'
```

**Resolve ABI (cache or Etherscan v2)**

```bash
curl -s "$BASE/api/blockchain/abi?address=0xA0b86991c6218b36c1d19d4a2e9eb0cE3606eB48&network=mainnet" | jq '.[0:3]'
```

**Read-only call**

```bash
curl -s -X POST "$BASE/api/blockchain/call" \
  -H "Content-Type: application/json" \
  -d '{
        "contract_address":"0x01bb56E6A4deDa43338f8425407743CdCfAC1EA7",
        "network":"sepolia",
        "function":"symbol",
        "args":[]
      }'
```

**AI risk score**

```bash
curl -s -X POST "$BASE/api/ai/predict" \
  -H "Content-Type: application/json" \
  -d '{"feature1":0.3,"feature2":-0.4}'
```

**Start audit (async)**

```bash
curl -s -X POST "$BASE/api/audit/start" \
  -H "Content-Type: application/json" \
  -d '{"address":"0x01bb56E6A4deDa43338f8425407743CdCfAC1EA7","network":"sepolia","force_refresh":true}'
```

**Check job status**

```bash
curl -s "$BASE/api/audit/status/123"
```

**Fetch audit by id**

```bash
curl -s "$BASE/api/audit/456" | jq .
```

---

## Observability

- **Prometheus**: `/metrics` (includes app info and HTTP request metrics)
- **Structured logs**: `python-json-logger`
- **Health**: `/healthz`

---

## Security Notes

- **Private keys** are **not required** for read-only calls.
- If you configure `PRIVATE_KEY`, keep it **only** in secure worker environments (e.g., Render Background Worker).
- On public deployments, **never** expose signing endpoints without proper auth/rate limiting.

---

## Project Structure

```
app/
  __init__.py            # create_app(), Swagger, Prometheus, blueprints
  models/
    __init__.py          # SQLAlchemy/Migrate init, model imports
    job.py               # AnalysisJob
    contract_abi.py      # ContractABI cache
    audit.py             # ContractAudit
  routes/
    task_routes.py       # /procesar, /jobs/<id>
    blockchain_routes.py # /api/blockchain/*
    ai_routes.py         # /api/ai/*
    audit_routes.py      # /api/audit/*
    health.py            # /healthz
  services/
    abi_service.py       # Etherscan v2, cache, save, resolve
    ai_service.py        # IsolationForest risk scoring
  tasks/
    celery_app.py        # Celery app init (Flask context)
    background_tasks.py  # examples
    audit_tasks.py       # audit.run pipeline
config/
  ...
wsgi.py                  # Flask entrypoint
docker-compose.yml
Dockerfile
requirements.txt
```

---
