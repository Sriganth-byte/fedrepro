# FedRepro System Architecture

**Last updated:** 2026-08-11
**Migration head:** `0006_variant_generator`
**Current status:** production-ready research workflow with deterministic evidence warmup

FedRepro is an evidence-first machine-learning research platform. It does not train models. It prepares dataset evidence so later experiment work can reference immutable, auditable data versions with fingerprints, profiles, semantic-change metrics, diagnoses, interventions, variants, reports, and optional AI interpretations.

## Core Boundary

All metrics are deterministic. AI is explanation-only.

AI must not compute or modify:

- fingerprints
- profile evidence
- SCM
- DSI
- MLRS
- LRS
- VRS
- findings
- diagnosis thresholds
- intervention eligibility

AI explanations are generated only from persisted evidence and are cached with the evidence hash, prompt version, model name, source type, and source identifier.

## Runtime Stack

| Layer | Technology |
|---|---|
| Web app | React 18, React Router, Axios, Recharts, lucide-react, Webpack |
| API | FastAPI, Uvicorn |
| Persistence | PostgreSQL, SQLAlchemy 2.0, Alembic |
| Data processing | Pandas, NumPy, scikit-learn, imbalanced-learn |
| Document export | python-docx |
| Optional AI | Ollama HTTP API |
| Storage | Local staged and immutable CSV files under backend uploads |

## Dependency Direction

```text
React UI
  -> frontend/src/api/client.js
    -> FastAPI routes
      -> application workflow services
        -> deterministic metric services
        -> SQLAlchemy models/repositories
        -> local file storage
        -> optional AI explanation cache
```

Routes translate HTTP, enforce ownership, and shape responses. Services own workflows. Deterministic services own metric formulas. Models persist evidence. The UI renders already-computed evidence and triggers explicit runs/recomputes.

## Evidence Lifecycle

```text
Study
  -> StudyConfiguration
  -> DatasetRegistration
  -> DatasetConfiguration
  -> immutable DatasetVersion
      -> DatasetFingerprint
      -> SemanticDiffReport for child versions
      -> DatasetProfileReport
      -> DiagnosisReport
      -> ActivityLog report payloads
      -> AIGeneratedExplanation rows when AI is enabled
      -> VariantGenerationRecord when version came from a variant
```

## Dataset Version Types

FedRepro supports diagnosis for every immutable `DatasetVersion`:

- manually uploaded baseline versions
- normal uploaded revisions
- variant-generated versions

Each selected version follows the same evidence contract:

1. Check for persisted fingerprint, profile, diagnosis, semantic diff when applicable, reports, and AI rows.
2. Reuse valid persisted evidence.
3. Show `Run Diagnosis` when profile or diagnosis is absent.
4. Show `Recompute Diagnosis` when profile, diagnosis, or semantic ruleset evidence is stale.
5. Execute `ProfilingService -> DiagnosisService` deterministically when run/recompute is requested.
6. Persist evidence against the exact immutable `DatasetVersion`.
7. Refresh the UI immediately after completion.

## Startup Evidence Warmup

`EvidenceWarmupService` runs from FastAPI lifespan startup when `EVIDENCE_WARMUP_ON_STARTUP=true`.

For every study and every dataset version it:

- generates missing profile evidence
- generates missing diagnosis evidence
- generates missing semantic SCM/DSI evidence for child versions
- recomputes stale profile, diagnosis, or semantic evidence when algorithm versions changed
- stores deterministic version explanation payloads in `ActivityLog`
- queues missing AI explanations when `AI_ENABLED=true`
- skips usable cached AI explanations with matching evidence hash and prompt version

Warmup is best-effort and runs in a daemon thread so API startup is not blocked. Errors are logged per version and do not stop the server.

AI warmup can use multiple locally available Ollama models. It lists `/api/tags`, ranks smaller capable models first, and runs at most three concurrent AI tasks. Preferred model families include `qwen2.5`, `qwen2`, `llama3.2`, `phi3`, `gemma2`, `mistral`, and `llama3.1`.

Disable startup warmup:

```env
EVIDENCE_WARMUP_ON_STARTUP=false
```

## Deterministic Metrics

| Metric | Service | Version | Meaning |
|---|---|---|---|
| Fingerprint | `FingerprintService` | `fingerprint-1.0` | File, schema, metadata, config, and combined reproducibility hashes |
| Profile | `ProfilingService` | `profile-1.0` | Dataset quality, column, task, correlation, missingness, duplicate, outlier evidence |
| SCM | `SemanticDiffService` | `semantic-2.0` | Structural/content change between parent and current version |
| DSI | `SemanticDiffService` | `semantic-2.0` | Distribution movement across common features |
| MLRS | `DiagnosisService` | `diagnosis-2.0` | ML training readiness risk; higher means more risk |
| LRS | `DiagnosisService` | `diagnosis-2.0` | Leakage risk; independent of MLRS |
| VRS | `VariantEvaluatorService` | deterministic | Variant readiness score; higher means better for chosen goal |
| Protocol completeness | `StudyService` | deterministic | Study protocol field coverage, 0-100 |
| AI explanation | `AIExplanationService` | `explanation-2.0` | Evidence-bound interpretation text or structured version analysis |

Baseline versions do not have SCM/DSI because there is no parent version. The UI must render this as `N/A` or `Not computed`, not as zero unless the persisted metric is actually zero.

## Diagnosis Status

The API returns `diagnosis_status` in dataset/version payloads.

Statuses:

- `Not Diagnosed`
- `Diagnosed`
- `Recompute Available`
- `Running` when the UI has an active request
- `Failed` when the UI request fails

`Recompute Available` is returned when:

- a diagnosis exists but profile is missing
- profile `profiler_version` is stale
- diagnosis `ruleset_version` is stale
- a child version is missing semantic evidence
- semantic `ruleset_version` is stale

## Variant Integration

The Variant Generator creates candidate pipelines from diagnosis findings. A generated variant can be registered as a new immutable `DatasetVersion`.

When a variant version is created:

- a synthetic registration is stored
- a copied dataset configuration is stored
- a fingerprint is generated
- lineage is recorded
- semantic diff against the source version is generated
- profile and diagnosis are generated
- AI diagnosis/executive/report explanations are attempted when enabled
- VRS metadata remains available through `VariantGenerationRecord`

The Diagnosis page displays VRS alongside MLRS/LRS/SCM/DSI when the selected version originated from a variant.

## Main API Routes

### Datasets and Versions

| Method | Path | Purpose |
|---|---|---|
| POST | `/api/studies/{study_id}/datasets/register` | Register staged CSV evidence |
| GET | `/api/studies/{study_id}/datasets` | List datasets and versions with diagnosis status |
| POST | `/api/registrations/{registration_id}/configure` | Promote upload into immutable version and analyze |
| GET | `/api/versions/{version_id}` | Version bundle |
| GET | `/api/versions/{version_id}/analysis` | Version, profile, diagnosis, and timeline |
| POST | `/api/versions/{version_id}/diagnosis/run?recompute=false` | Run or recompute diagnosis |
| GET | `/api/versions/{version_id}/profile` | Profile report |
| GET | `/api/versions/{version_id}/diagnosis` | Diagnosis report |
| GET | `/api/versions/{version_id}/semantic-diff` | SCM/DSI evidence |
| GET | `/api/versions/{version_id}/compare?against_version_id=` | Ad hoc version comparison |
| GET | `/api/versions/{version_id}/recreation-bundle` | Reproducibility bundle |
| POST | `/api/versions/recreate/verify` | Verify a CSV against a recreation bundle |
| GET | `/api/versions/{version_id}/diagnosis-contract` | Intervention handoff contract |
| GET | `/api/versions/{version_id}/diagnosis-report` | Download DOCX diagnosis report |
| GET | `/api/versions/{version_id}/explanation-report` | Deterministic or cached LLM version report |
| POST | `/api/versions/{version_id}/explanation-report/generate` | Generate LLM version explanation report |

### AI

| Method | Path | Purpose |
|---|---|---|
| POST | `/api/ai/studies/{study_id}/explain` | Generic evidence explanation |
| POST | `/api/ai/studies/{study_id}/versions/{version_id}/executive-summary` | Cached version executive summary |
| POST | `/api/ai/studies/{study_id}/versions/{version_id}/executive-summary/stream` | Stream version executive summary |
| POST | `/api/ai/studies/{study_id}/versions/{version_id}/diagnosis-interpretation` | Cached diagnosis interpretation |
| POST | `/api/ai/studies/{study_id}/semantic-diffs/{diff_id}/metrics-interpretation` | SCM/DSI interpretation |
| POST | `/api/ai/studies/{study_id}/semantic-diffs/{diff_id}/interpretation` | Semantic diff narrative |

### Variants

| Method | Path | Purpose |
|---|---|---|
| POST | `/api/versions/{version_id}/variant-jobs` | Create and run variant job |
| GET | `/api/versions/{version_id}/variant-jobs` | List jobs |
| GET | `/api/variant-jobs/{job_id}` | Poll one job |
| POST | `/api/variant-jobs/{job_id}/records/{record_id}/register` | Promote generated variant version |
| GET | `/api/versions/{version_id}/variant-tree` | Version lineage tree |

## Operational Utility

`tools/recompute_all_dataset_evidence.py` can be used for a deliberate one-off recomputation across all versions.

Examples:

```powershell
python tools/recompute_all_dataset_evidence.py --skip-ai
python tools/recompute_all_dataset_evidence.py --limit 5
python tools/recompute_all_dataset_evidence.py --keep-ai-cache
```

Startup warmup is preferred for normal operation because it only fills missing or stale artifacts.

## Verification

Current verification commands:

```powershell
cd backend
..\backend\venv\Scripts\python.exe -m pytest

cd ..\frontend
npm.cmd run build
```

Latest local result:

- Backend: 59 passed
- Frontend: production build passed with a webpack entrypoint size warning
