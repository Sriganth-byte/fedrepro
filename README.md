# FedRepro

FedRepro is a data-centric machine-learning research platform for managing dataset evidence before model experimentation. It registers CSV datasets, creates immutable dataset versions, fingerprints evidence, tracks semantic change between versions, profiles datasets deterministically, produces ML readiness and leakage diagnoses, and generates deterministic preprocessing variants.

AI support is optional and explanation-only. AI does not calculate fingerprints, profiles, findings, SCM, DSI, MLRS, LRS, or VRS.

## Features

- JWT authentication for study owners
- Study protocol builder with versioned research configurations
- CSV dataset registration with validation and metadata capture
- Immutable dataset versioning with lineage records
- SHA-256 file, schema, metadata, and combined fingerprints
- Semantic difference reports between dataset versions
- Deterministic dataset profiling for classification, regression, and clustering
- Diagnosis reports with MLRS and LRS scores
- Variant generator for preprocessing pipeline candidates and VRS ranking
- Optional Ollama-powered evidence explanations
- React dashboard and tabbed study workspace

## Tech Stack

Backend:

- Python 3.11
- FastAPI
- SQLAlchemy
- Alembic
- PostgreSQL
- Pandas, NumPy, scikit-learn, imbalanced-learn
- python-docx

Frontend:

- React 18
- React Router
- Axios
- Recharts
- lucide-react
- Webpack

## Project Structure

```text
backend/
  app/
    api/routes/       FastAPI route modules
    core/             settings, database, security
    models/           SQLAlchemy entities
    services/         workflow and deterministic analysis logic
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

docs/                 architecture and implementation notes
tools/                local utility scripts
```

## Prerequisites

Install these before setup:

- Python 3.11
- Node.js 18 or newer
- PostgreSQL 14 or newer
- Git
- Optional: Ollama, only if AI explanations are enabled

## Database Setup

Create a PostgreSQL database for the app.

Example using `psql`:

```sql
CREATE DATABASE fedrepo;
```

Create or choose a database user with access to that database. Your connection string should look like:

```text
postgresql+psycopg2://<user>:<password>@localhost:5432/fedrepo
```

## Backend Setup

From the project root:

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\pip.exe install -r requirements.txt
Copy-Item .env.example .env
```

Edit `backend/.env` and set:

```env
DATABASE_URL=postgresql+psycopg2://<user>:<password>@localhost:5432/fedrepo
SECRET_KEY=<use-a-long-random-secret>
ACCESS_TOKEN_EXPIRE_MINUTES=1440
CORS_ORIGINS=["http://localhost:3000","http://127.0.0.1:3000"]
AI_ENABLED=false
OLLAMA_BASE_URL=http://127.0.0.1:11434
OLLAMA_MODEL=llama3.1:latest
```

Run database migrations:

```powershell
.\.venv\Scripts\alembic.exe upgrade head
```

Start the backend:

```powershell
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Backend URLs:

- API health: `http://127.0.0.1:8000/api/health`
- API docs: `http://127.0.0.1:8000/api/docs`

## Frontend Setup

Open a second terminal from the project root:

```powershell
cd frontend
npm install
npm start
```

Open:

```text
http://127.0.0.1:3000
```

The Webpack dev server proxies `/api` requests to the FastAPI backend.

## Optional AI Explanations

AI is disabled by default. Deterministic workflows work without Ollama.

To enable local AI explanations:

1. Install and start Ollama.
2. Pull a model, for example:

```powershell
ollama pull llama3.1:latest
```

3. Update `backend/.env`:

```env
AI_ENABLED=true
OLLAMA_BASE_URL=http://127.0.0.1:11434
OLLAMA_MODEL=llama3.1:latest
```

4. Restart the backend.

## Verification

Run backend tests:

```powershell
cd backend
.\.venv\Scripts\python.exe -m pytest -q
```

Build the frontend:

```powershell
cd frontend
npm run build
```

Optional production dependency audit:

```powershell
cd frontend
npm audit --omit=dev
```

## Main Workflow

1. Register or log in.
2. Create an ML study and define the research protocol.
3. Upload a CSV dataset as evidence.
4. Configure the dataset for classification, regression, or clustering.
5. Promote the upload into an immutable dataset version.
6. Review fingerprints, semantic changes, profile evidence, and diagnosis findings.
7. Generate a diagnosis contract and optional preprocessing variants.
8. Use optional AI explanations only to interpret already-persisted evidence.

## GitHub Notes

The repository is configured to ignore:

- local `.env` files
- Python virtual environments
- `node_modules`
- frontend build output
- runtime uploads
- logs and caches
- legacy backup zip archives

Commit `backend/.env.example`, but do not commit `backend/.env`.

## First Push

```powershell
git init
git remote add origin https://github.com/Sriganth-byte/fedrepro.git
git add .
git commit -m "Initial FedRepro project"
git branch -M main
git push -u origin main
```

If the remote already exists locally:

```powershell
git remote set-url origin https://github.com/Sriganth-byte/fedrepro.git
git push -u origin main
```

## Boundaries

FedRepro does not train ML models or calculate model performance. It prepares, fingerprints, analyzes, diagnoses, and variants dataset evidence so later experiment phases can reference immutable evidence records.
