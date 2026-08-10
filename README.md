# FedRepro

FedRepro is a data-centric machine-learning research platform for managing dataset evidence before model experimentation. It registers CSV datasets, creates immutable dataset versions, fingerprints evidence, tracks semantic change between versions, profiles datasets deterministically, produces ML readiness and leakage diagnoses, generates preprocessing variants, and caches evidence-bound AI interpretations when enabled.

AI support is optional and explanation-only. AI does not calculate fingerprints, profiles, findings, SCM, DSI, MLRS, LRS, VRS, or deterministic thresholds.

## Current Highlights

- Study protocol builder with server-computed completeness and versioned protocol lineage
- CSV dataset registration with metadata capture
- Immutable dataset versioning for manual uploads, revisions, and variant-generated versions
- SHA-256 file, schema, metadata, and combined fingerprints
- SCM/DSI semantic comparison for child versions
- Profile evidence for quality, missingness, duplicates, outliers, correlations, and target distribution
- Diagnosis dashboard with MLRS, LRS, findings, severity distribution, intervention planning, and click-to-open detail workspace
- Explicit per-version `Run Diagnosis` and `Recompute Diagnosis`
- Startup evidence warmup for all dataset versions
- Variant Generator with deterministic pipeline planning, VRS ranking, and version promotion
- Optional Ollama summaries, diagnosis interpretations, semantic interpretations, and dataset explanation reports
- DOCX diagnosis and executive reports
- Full light/dark React UI

## Documentation

| Document | Purpose |
|---|---|
| `docs/ARCHITECTURE.md` | Current backend/frontend architecture, evidence lifecycle, metrics, routes, startup warmup |
| `docs/UI_REFERENCE.md` | UI implementation reference for components, state, diagnosis dashboard, and styling |
| `docs/UI_PAGE_GUIDE.md` | User-facing guide for every page and main workflow |
| `docs/AGENT_KNOWLEDGE_BASE.md` | Fast-load engineering reference for future coding agents |
| `docs/VARIANT_GENERATOR_REPORT.md` | Detailed Variant Generator implementation report |
| `docs/REFINEMENT_1_IMPLEMENTATION_REPORT.md` | Study configuration completeness and lineage report |
| `TECHNICAL_IMPLEMENTATION_REPORT.md` | Detailed implementation assessment and current addendum |
| `GITHUB_READY.md` | Commit/push and verification checklist |

## Project Structure

```text
backend/
  app/
    api/routes/       FastAPI route modules
    core/             settings, database, security
    models/           SQLAlchemy entities
    services/         workflow, deterministic analysis, AI explanation, warmup
    storage/          local CSV staging/version storage
  alembic/            database migrations
  tests/              backend tests
  requirements.txt

frontend/
  public/
  src/
    api/              Axios client facade
    components/       shared UI primitives
    context/          auth context
    features/         study workspace panels
    layouts/          app shell
    pages/            routed pages
  package.json

docs/                 architecture, UI, implementation, and user guides
tools/                local utility scripts
```

## Prerequisites

- Python 3.11
- Node.js 18 or newer
- PostgreSQL 14 or newer
- Git
- Optional: Ollama, only if AI explanations are enabled

## Backend Setup

From the project root:

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\pip.exe install -r requirements.txt
Copy-Item .env.example .env
```

Set `backend/.env`:

```env
DATABASE_URL=postgresql+psycopg2://<user>:<password>@localhost:5432/fedrepo
SECRET_KEY=<use-a-long-random-secret>
ACCESS_TOKEN_EXPIRE_MINUTES=1440
CORS_ORIGINS=["http://localhost:3000","http://127.0.0.1:3000"]
AI_ENABLED=false
OLLAMA_BASE_URL=http://127.0.0.1:11434
OLLAMA_MODEL=llama3.1:latest
EVIDENCE_WARMUP_ON_STARTUP=true
```

Run migrations:

```powershell
.\.venv\Scripts\alembic.exe upgrade head
```

Start the backend:

```powershell
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Useful URLs:

- Health: `http://127.0.0.1:8000/api/health`
- Version: `http://127.0.0.1:8000/api/version`
- API docs: `http://127.0.0.1:8000/api/docs`

## Frontend Setup

Open a second terminal:

```powershell
cd frontend
npm install
npm start
```

Open:

```text
http://127.0.0.1:3000
```

## Startup Evidence Warmup

When `EVIDENCE_WARMUP_ON_STARTUP=true`, backend startup launches a best-effort background scan across all studies and all dataset versions.

It fills missing or stale:

- profile evidence
- diagnosis evidence
- SCM/DSI semantic evidence for child versions
- deterministic version report payloads
- AI summaries, reports, and interpretations when `AI_ENABLED=true`

Warmup reuses valid persisted evidence and does not alter metric formulas. When Ollama is enabled, it can use multiple available local models and caps AI concurrency.

For a deliberate full recompute:

```powershell
python tools\recompute_all_dataset_evidence.py --skip-ai
python tools\recompute_all_dataset_evidence.py --limit 5
```

## Main Workflow

1. Register or log in.
2. Create an ML study and complete the research protocol.
3. Upload CSV dataset evidence.
4. Configure the dataset target, metric, validation strategy, features, and scaling.
5. Promote the upload into an immutable dataset version.
6. Review fingerprints, profile evidence, semantic changes, and diagnosis status.
7. Use the Diagnosis dashboard to inspect quality, MLRS, LRS, SCM, DSI, VRS, risks, interventions, human decisions, evidence, and AI interpretation.
8. Generate variants from diagnosis findings when needed.
9. Promote a selected variant to a new immutable version.
10. Re-diagnose or audit the new version exactly like any other version.

## Optional AI Explanations

AI is disabled by default.

To enable local AI:

```powershell
ollama pull qwen2.5:3b
ollama pull llama3.2:3b
```

Then set:

```env
AI_ENABLED=true
OLLAMA_BASE_URL=http://127.0.0.1:11434
OLLAMA_MODEL=qwen2.5:3b
```

FedRepro will use configured and locally available Ollama models for evidence-bound summaries and interpretations.

## Verification

Backend:

```powershell
cd backend
..\backend\venv\Scripts\python.exe -m pytest
```

Frontend:

```powershell
cd frontend
npm.cmd run build
```

Latest local verification:

- Backend: 59 passed
- Frontend: build passed with a webpack entrypoint size warning

## Boundaries

FedRepro does not train ML models or calculate model performance. It prepares, fingerprints, analyzes, diagnoses, explains, and variants dataset evidence so later experiment phases can reference immutable stored evidence.
