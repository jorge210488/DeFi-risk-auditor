# DeFi Risk Auditor

![DeFi Risk Auditor – Overview](https://assets.example.com/screens/deFi-risk-auditor-overview.png)
![DeFi Risk Auditor – Swagger](https://assets.example.com/screens/deFi-risk-auditor-swagger.png)
![DeFi Risk Auditor – Metrics](https://assets.example.com/screens/deFi-risk-auditor-metrics.png)
![DeFi Risk Auditor – ABI Cache](https://assets.example.com/screens/deFi-risk-auditor-abi-cache.png)
![DeFi Risk Auditor – Audit Flow](https://assets.example.com/screens/deFi-risk-auditor-audit-flow.png)
![DeFi Risk Auditor – Jobs](https://assets.example.com/screens/deFi-risk-auditor-jobs.png)

**DeFi Risk Auditor** is a Python/Flask backend to analyze EVM smart contracts.
It automatically resolves and caches **ABIs** (Etherscan API v2), performs **read-only on-chain calls**, runs an **AI-based risk score** (IsolationForest), and executes **asynchronous audits** with Celery/Redis. The service exposes **OpenAPI/Swagger** and **Prometheus** metrics.

**Live (Render):** `https://defi-risk-auditor.onrender.com`

- API Docs: `/apidocs/`
- Health: `/healthz`
- Metrics: `/metrics`

---

## Features

- 🔗 **Blockchain**

  - ABI resolution via **Etherscan v2** with **PostgreSQL cache**.
  - **Read-only** Web3 calls (no gas), PoA middleware support.
  - Optional signed transactions (requires `PRIVATE_KEY` in the worker).

- 🤖 **AI**

  - Risk scoring (demo) with **IsolationForest** on features derived from ABI/bytecode.
  - Used **directly** (demo endpoint) and **inside the audit pipeline**.

- 🧪 **Audit pipeline**

  - ABI → feature extraction → AI score → persisted **ai_score/risk_level** + **summary/features**.
  - Asynchronous execution via Celery, trackable with `job_id`.

- 📊 **Operations**

  - **Swagger** documentation.
  - **Prometheus** metrics (`prometheus-flask-exporter`).
  - Structured logging with `python-json-logger`.

---

## Architecture (overview)

- **Flask** (API, Swagger, metrics)
- **Celery + Redis** (queues/workers)
- **PostgreSQL** (jobs, ABI cache, audits)
- **Web3.py** (EVM RPC)
- **Etherscan v2** (ABI source)
- **scikit-learn** (AI model)

Core flows:

1. **Read-only calls** → Resolve ABI (inline/file/cache/Etherscan) → Web3 call → JSON result.
2. **Audit** → ABI + bytecode → features (write ratio, flags, etc.) → AI → store score/level → fetch by `audit_id`.
3. **Signing (optional)** → Worker with `PRIVATE_KEY` sends tx (not required for reads/audits).

---

## Tech Stack

- **Flask 3.x**, **Flask-SQLAlchemy 3.x**, **Flask-Migrate/Alembic**
- **Celery 5.5** + **Redis**
- **Web3.py 6.x** (PoA middleware)
- **scikit-learn**, **joblib**, **numpy**
- **Flasgger** (Swagger / OpenAPI)
- **prometheus-flask-exporter**
- **requests** (Etherscan)
- **python-json-logger**

---

## Environment Variables (main)

| Variable                                     | Description                                                       |
| -------------------------------------------- | ----------------------------------------------------------------- |
| `DATABASE_URL`                               | SQLAlchemy PostgreSQL URL                                         |
| `CELERY_BROKER_URL`, `CELERY_RESULT_BACKEND` | Celery broker/result backend (Redis)                              |
| `WEB3_PROVIDER_URI`                          | RPC endpoint (e.g., Sepolia via Infura/Alchemy)                   |
| `WEB3_CHAIN_ID`, `ETHERSCAN_CHAIN_ID`        | Chain IDs (Sepolia = `11155111`)                                  |
| `WEB3_USE_POA`                               | Enable PoA middleware if `true`                                   |
| `ETHERSCAN_API_KEY`                          | Etherscan API key                                                 |
| `ETHERSCAN_NETWORK`                          | Human label for network (e.g., `sepolia`)                         |
| `CONTRACT_ADDRESS`                           | Optional default address (fallback for reads)                     |
| `CONTRACT_ABI_PATH`                          | Optional local ABI JSON fallback                                  |
| `PRIVATE_KEY`                                | **Only** for signing tx in the worker (not required for reads/AI) |
| `DEBUG_METRICS`                              | If set, enables extra metrics hints                               |

> **Render vs Local:** In Render, configure external URLs (`rediss://`, managed `postgres://`, HTTPS RPC).
> In local `docker-compose`, service names are used (`redis://redis:6379/0`, `db`, etc.).

---

## Getting Started (local)

### 1) Clone

```bash
git clone https://github.com/your-org/defi-risk-auditor.git
cd defi-risk-auditor
```

### 2) `.env` (example)

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

# Optional fallbacks
CONTRACT_ADDRESS=0x01bb56E6A4deDa43338f8425407743CdCfAC1EA7
CONTRACT_ABI_PATH=/app/app/abi/ERC20.json

# Only if you will sign tx in the worker
# PRIVATE_KEY=0xREPLACE_WITH_YOUR_PRIVATE_KEY
```

### 3) Run

```bash
docker compose up --build
```

- API: `http://localhost:5050/`
- Swagger: `http://localhost:5050/apidocs/`
- Health: `http://localhost:5050/healthz`
- Metrics: `http://localhost:5050/metrics`

---

## Deployment (Render)

- **Web Service** (Flask) using the same Docker image.
- **Background Worker** (Celery) with the worker command.
- Managed **PostgreSQL** and **Redis** (or external providers).
- Configure all **ENV VARS** in Render. Swagger is served with **HTTPS**.

---

## Security

- `PRIVATE_KEY` is **not needed** for read-only calls or audits.
- If you enable signing, keep `PRIVATE_KEY` **only** in the worker and secured.
- For public deployments, consider **auth**, **rate limiting**, and secret rotation.

---

## Project Structure

```
app/
  __init__.py            # create_app(), Swagger, metrics, blueprints
  models/
    __init__.py          # SQLAlchemy/Migrate init
    job.py               # AnalysisJob
    contract_abi.py      # ABI cache
    audit.py             # ContractAudit
  routes/
    health.py            # /healthz
    ai_routes.py         # /api/ai (AI demo)
    blockchain_routes.py # /api/blockchain (ABI/cache/read calls)
    audit_routes.py      # /api/audit (audit jobs)
    task_routes.py       # generic jobs / alias
  services/
    abi_service.py       # Etherscan v2, cache/resolve
    ai_service.py        # IsolationForest risk scoring
  tasks/
    audit_tasks.py       # audit.run (AI pipeline)
    blockchain_tasks.py  # tx send/wait
    ai_tasks.py          # async inference (optional)
config/
Dockerfile
docker-compose.yml
requirements.txt
wsgi.py
```

---

## API

Full request/response details are documented in **Swagger**:
`https://defi-risk-auditor.onrender.com/apidocs/`
