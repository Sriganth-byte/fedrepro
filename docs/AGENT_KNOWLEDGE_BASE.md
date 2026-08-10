# FedRepro Agent Knowledge Base

**Generated**: 2026-08-05  
**Migration head**: `0006_variant_generator`  
**Purpose**: Fast-load agent reference. Read this first, then inspect referenced files before editing.

---

## Project Snapshot

FedRepro is a Phase 1 data-centric ML research platform. It registers CSV dataset evidence, creates immutable versions, fingerprints versions, tracks semantic change, profiles data deterministically, produces evidence-backed ML risk diagnoses, and generates preprocessing pipeline variants — all before a model touches data.

**Critical boundary**: AI is optional and explanation-only. AI must NEVER compute profiles, fingerprints, semantic scores, diagnosis findings, MLRS, LRS, SCM, DSI, or VRS. Deterministic services own every metric output.

---

## Runtime Stack

| Layer | Technology |
|---|---|
| Backend | FastAPI + Uvicorn on port 8000 |
| ORM | SQLAlchemy 2.0, Alembic |
| Database | PostgreSQL (`localhost:5432/fedrepo`) |
| Data | Pandas, NumPy, scikit-learn |
| Reports | python-docx |
| AI (optional) | Ollama via HTTP (`AI_ENABLED=false` by default) |
| Frontend | React 18, React Router 6, Axios, Recharts, lucide-react |
| Bundler | Webpack 5, port 3000 |
| Storage | Local filesystem, `uploads/` |

---

## Repository Index

```text
docs/AGENT_KNOWLEDGE_BASE.md          ← This file (agent reference)
docs/ARCHITECTURE.md                  ← System architecture, lifecycle, metrics, routes
docs/UI_REFERENCE.md                  ← Every page, component, state flow, CSS classes
docs/REFINEMENT_1_IMPLEMENTATION_REPORT.md ← Refinement #1 detailed report
docs/VARIANT_GENERATOR_REPORT.md      ← Variant Generator detailed report

backend/
  requirements.txt
  alembic.ini
  alembic/env.py
  alembic/versions/
    0001_phase1_schema.py             Phase 1 tables
    0002_evidence_lifecycle.py        Cascade FKs, fingerprint index
    0003_ai_source_foreign_keys.py    AI explanation source FKs
    0004_study_configurations.py      StudyConfiguration table
    0005_study_configuration_completeness.py  +5 columns, completeness scoring
    0006_variant_generator.py         variant_generation_jobs/records tables + generation_method

  app/main.py                         FastAPI app, CORS, routers, health
  app/core/config.py                  Settings: DATABASE_URL, SECRET_KEY, AI_ENABLED, etc.
  app/core/database.py                Engine/session/Base (created at import time)
  app/core/security.py                JWT + password hashing
  app/models/entities.py              All ORM entities
  app/schemas/contracts.py            All Pydantic schemas
  app/api/dependencies.py             get_current_user dependency
  app/api/routes/auth.py              /auth/register, /auth/login
  app/api/routes/studies.py           Dashboard, studies, configurations, findings
  app/api/routes/datasets.py          Dataset workflow, analysis, reports, bundles
  app/api/routes/variants.py          Variant generation jobs and records
  app/api/routes/ai.py               Explanation endpoints
  app/repositories/base.py            Repository port interfaces
  app/repositories/sqlalchemy.py      SQLAlchemy implementations
  app/storage/local_storage.py        CSV staging, promotion, deletion guards
  app/services/study_service.py       Study CRUD + completeness scoring
  app/services/dataset_workflow_service.py  Upload→version→profile→diagnosis
  app/services/fingerprint_service.py
  app/services/semantic_diff_service.py    SCM + DSI computation
  app/services/profiling_service.py
  app/services/diagnosis_service.py        MLRS + LRS computation
  app/services/diagnosis_contract_service.py
  app/services/diagnosis_report_service.py .docx reports
  app/services/executive_report_service.py
  app/services/dataset_explanation_report_service.py
  app/services/ai_explanation_service.py    Evidence-bound Ollama calls
  app/services/reporting_service.py
  app/services/issue_interpreter_service.py     Diagnosis → requirements dict
  app/services/pipeline_planner_service.py      Requirements → pipelines
  app/services/transformation_knowledge_base.py All transformations catalogue
  app/services/variant_builder_service.py       Apply pipeline to CSV
  app/services/variant_evaluator_service.py     Profile+diagnose variant → VRS
  app/services/variant_generator_orchestrator.py Full job coordination
  app/services/explanation_engine_service.py    Step explanation text
  app/utilities/hashing.py            canonical_hash, sha256_file
  tests/test_api_workflow.py
  tests/test_analysis_services.py
  tests/test_study_configuration_refinement.py
  tests/test_variant_services.py

frontend/
  package.json                        Scripts: start (webpack dev), build
  webpack.config.js
  public/index.html
  src/index.jsx                       React root + FOUC-prevention theme init
  src/App.jsx                         Routes + Protected guard
  src/api/client.js                   Axios facade: authApi, dashboardApi, studyApi,
                                      datasetApi, aiApi, variantApi
  src/context/AuthContext.jsx         Token state (localStorage: fedrepro_token)
  src/layouts/AppLayout.jsx           Sidebar + topbar + ThemeToggle
  src/components/UI.jsx               All shared primitives (see UI_REFERENCE.md §2)
  src/pages/AuthPage.jsx              Login/register
  src/pages/DashboardPage.jsx         KPI metrics + risk chart + activity feed
  src/pages/StudiesPage.jsx           Protocol builder + study directory
  src/pages/StudyWorkspace.jsx        State owner + 5-tab workspace
  src/pages/ResearchFindingsPage.jsx  Cross-study evidence summary
  src/features/studies/WorkspacePanels.jsx  All 5 tab panels (2500 lines)
  src/styles.css                      Global token-based design system (light+dark)
```

Ignore: `backend/venv/**`, `frontend/node_modules/**`.

---

## Evidence Lifecycle (Phase 1)

```
User
  → Study + StudyConfiguration (completeness_score computed server-side)
  → Dataset registration (staged CSV + metadata → DatasetRegistration)
  → Dataset configuration (promoted → immutable DatasetVersion)
      → DatasetFingerprint (fingerprint-1.0)
      → SemanticDiffReport for V2+ (semantic-1.2, SCM + DSI)
      → DatasetProfileReport (profile-1.0)
      → DiagnosisReport (diagnosis-2.0, MLRS + LRS)
  → DiagnosisContract (intervention handoff)
  → VariantGenerationJob (background task)
      → IssueInterpreterService → PipelinePlannerService → VariantBuilderService
      → VariantEvaluatorService → VRS → ranked VariantGenerationRecord rows
  → Optional: register top variant as new DatasetVersion (generation_method="variant")
  → Optional: AI explanation from persisted evidence (explanation-1.8)
```

---

## Metric Computation

| Score | Service | Algorithm Version | Meaning |
|---|---|---|---|
| SCM | SemanticDiffService | semantic-1.2 | Structural/content change between versions (0–100, higher = more change) |
| DSI | SemanticDiffService | semantic-1.2 | Distribution shift between versions (0–100) |
| MLRS | DiagnosisService | diagnosis-2.0 | ML training readiness risk (0–100, **higher = worse**) |
| LRS | DiagnosisService | diagnosis-2.0 | Target leakage risk (0–100, independent of MLRS) |
| VRS | VariantEvaluatorService | — | Variant readiness score (0–100, higher = better for the chosen goal) |
| Completeness | StudyService | — | Protocol field coverage 0–100 (10 pts × 10 fields, server-computed) |

**VRS formula**:
```
VRS = (w_mlrs × MLRS_reduction + w_miss × miss_reduction + w_bal × class_balance
       + w_feat × feature_score + w_cost × cost_score) × 100
```
Weights are goal-dependent. Six optimization goals available.

**Completeness** — 10 fields (10 pts each):
`ml_task, domain, research_objective, research_question, hypothesis, target_column, primary_metric, baseline_model, validation_strategy, random_seed`  
**`random_seed = 0` is VALID** — only `None` is missing.

---

## API Routes Summary

**Auth**: `/api/auth/register`, `/api/auth/login`

**Studies**: `/api/dashboard`, `/api/studies` (CRUD + config history + diff + completeness), `/api/research-findings`

**Datasets**: `/api/studies/{id}/datasets/register`, `/api/registrations/{id}/configure`, `/api/versions/{id}/analysis`, `/api/versions/{id}/diagnosis-contract`, `/api/versions/{id}/diagnosis-report`, `/api/versions/{id}/recreation-bundle`

**Variants**: `/api/versions/{id}/variant-jobs`, `/api/variant-jobs/{id}`, `/api/variant-jobs/{id}/records/{id}/register`, `/api/versions/{id}/variant-tree`

**AI**: `/api/ai/studies/{id}/explain`, `/api/ai/studies/{id}/versions/{id}/executive-summary`, etc.

Full route table → `docs/ARCHITECTURE.md §7`.

---

## Variant Generator (Phase 1 Extension)

### Services

| Service | Responsibility |
|---|---|
| `IssueInterpreterService` | Maps `DiagnosisReport.findings_json` finding codes to a requirements dict |
| `PipelinePlannerService` | Builds N candidate pipelines deterministically from requirements + goal |
| `TransformationKnowledgeBase` | Catalogue of all transformations, cost estimates, conflict rules |
| `VariantBuilderService` | Applies pipeline steps to source CSV, returns `BuildResult` |
| `VariantEvaluatorService` | Profiles + diagnoses variant CSV, computes VRS components |
| `VariantGeneratorOrchestrator` | Coordinates the full job: interpret → plan → build → evaluate → rank |
| `ExplanationEngineService` | Generates deterministic explanation text for each pipeline step |

### Finding Code → Requirements Map

| Finding code | Requirements key |
|---|---|
| MISSINGNESS | needs_missing_value_handling |
| DUPLICATES | has_duplicates |
| OUTLIERS | needs_outlier_treatment |
| CORRELATION | needs_feature_reduction |
| CLASS_IMBALANCE | needs_class_balancing |
| TARGET_LEAKAGE | needs_leakage_fix |
| TARGET_SKEW | has_target_skew |
| SCALING | needs_scaling |

### Pipeline Step Order (always fixed)
`duplicate_removal → missing_value_handling → encoding → outlier_treatment → class_balancing → feature_reduction → scaling`

### Optimization Goals
`maximize_accuracy`, `faster_training`, `lightweight_dataset`, `improve_recall`, `fairness`, `explainable_model`

### Conflict Rules
- `iqr_filtering` and `isolation_forest` cannot coexist
- `correlation_filter` and `mutual_information` cannot coexist

### DB Tables (migration 0006)

**`variant_generation_jobs`**: source_version_id, diagnosis_report_id, optimization_goal, constraints_json, job_constraints_hash, status, total_variants_planned, total_variants_completed, error_message

**`variant_generation_records`**: job_id, variant_version_id, pipeline_id, pipeline_hash, pipeline_steps_json, random_seed, execution_time_seconds, mlrs_before/after, lrs_after, lrs_caveat, vrs_score, vrs_rank, goal_satisfaction, explanation_json, status

**`dataset_versions.generation_method`**: `"manual"` (default) or `"variant"` (promoted from a generation record)

---

## UI Design System

- All styles in `src/styles.css` — token-based, light + dark mode via `[data-theme]`.
- Dark mode persisted to `localStorage.fedrepro-theme`.
- FOUC prevented by `index.jsx` applying theme before React renders.
- ThemeToggle in topbar (moon/sun icon).
- All components in `src/components/UI.jsx`: Card, Button (with loading spinner), Field, Badge, Notice, PageHeader, Empty, MetricCard, DataTable (sortable), Skeleton, SkeletonCard, CopyButton, ThemeToggle, StatusDot.
- Full UI page and component documentation → `docs/UI_REFERENCE.md`.

---

## Refinements Applied

### Refinement #1 — Study Configuration Completeness (2026-08-04)
Migration: `0005_study_configuration_completeness`  
Added: `change_reason`, `superseded_at`, `source_configuration_id`, `completeness_score`, `missing_fields` to `study_configurations`.  
New endpoints: `GET /configurations/diff`, `GET /configurations/{version_number}`.  
Full report: `docs/REFINEMENT_1_IMPLEMENTATION_REPORT.md`

### Refinement #2 — Variant Generator (2026-08-04)
Migration: `0006_variant_generator`  
Added: `variant_generation_jobs`, `variant_generation_records`, `dataset_versions.generation_method`.  
New services: 7 variant generator services.  
New routes: `variants.py` (5 endpoints).  
New frontend: `VariantGeneratorPanel` in `WorkspacePanels.jsx`.  
Full report: `docs/VARIANT_GENERATOR_REPORT.md`

### UI/UX Overhaul (2026-08-04)
- Complete CSS design system rewrite (token-based, light/dark mode)
- Upgraded `AppLayout.jsx` with ThemeToggle, ARIA roles, mobile drawer
- Upgraded `AuthPage.jsx` with split-panel design and proof points
- Upgraded `DashboardPage.jsx` with Skeleton loaders, risk-colored chart, custom tooltip
- Upgraded `StudiesPage.jsx` with animated readiness bar, Enter-key search
- Upgraded `StudyWorkspace.jsx` with skeleton loader, status Notice, version badge
- Upgraded `ResearchFindingsPage.jsx` with aggregate stats, MLRS+LRS badges
- Upgraded `UI.jsx` with Button.loading, Skeleton, CopyButton, ThemeToggle, StatusDot
- Upgraded `WorkspacePanels.jsx` imports to use new UI primitives

---

## Common Development Commands

```powershell
# Backend
cd backend
.\.venv\Scripts\alembic.exe upgrade head
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000

# Frontend
cd frontend
npm start          # webpack dev server on port 3000
npm run build      # production build (use to check for compile errors)

# Tests
cd backend
.\.venv\Scripts\python.exe -m pytest -q
```

---

## Known Footguns

1. **`backend/venv`** dominates file search — always exclude it.
2. **`app/core/database.py`** creates engine at import time — tests must set env before importing app modules.
3. **`AI_ENABLED`** defaults to `false` — AI endpoints return errors if Ollama is not running.
4. **`DatasetWorkflowService.configure_and_analyze`** promotes file before downstream analysis and attempts rollback on failure.
5. **`ActivityLog`** serves dual purpose: event history AND deterministic report JSON storage.
6. **`WorkspacePanels.jsx`** is 2,500 lines — make targeted edits, search by component name.
7. **`StudyService.list()`** shadows the `list` builtin — requires `from __future__ import annotations` at line 1.
8. **Route order in `studies.py`**: `GET /configurations/diff` MUST be registered before `GET /configurations/{version_number}`.
9. **`random_seed = 0`** in completeness scoring: `0` is VALID. Only `None` is missing.
10. **LRS caveat**: when `mutual_information` is a pipeline step, `lrs_caveat = "mi_selection_expected"` is set — LRS elevation is an expected artifact of the step.

---

## Safe Change Recipes

**Add a new deterministic metric**:
1. Implement in `ProfilingService`, `SemanticDiffService`, or `DiagnosisService`.
2. Store in existing report JSON if possible; add migration only if it needs to be a DB column.
3. Update route payload shaping in `datasets.py`.
4. Add/update tests in `test_analysis_services.py`.
5. Wire to UI through `client.js` + `WorkspacePanels.jsx`.

**Add a new backend endpoint**:
1. Add route in the relevant `routes/*.py` file (business logic stays in services).
2. Enforce ownership via `StudyService.get_owned()` or study join.
3. Add `client.js` method.
4. Add tests if it changes workflow or evidence contracts.

**Add a new transformation to Variant Generator**:
1. Add entry to `TRANSFORMATIONS` dict in `transformation_knowledge_base.py`.
2. Add to `CANONICAL_CATEGORY_ORDER` if it's a new category.
3. Add conflict rules if needed in `pipeline_planner_service.py`.
4. Implement in `VariantBuilderService` with the same `transformation_id`.

**Add a new AI explanation type**:
1. Add allowed type in `schemas/contracts.py` `ExplanationRequest`.
2. Add evidence resolution in `api/routes/ai.py`.
3. Add prompt branch in `AIExplanationService._prompt()`.
4. Store source IDs and hashes.
5. Never allow invented metrics or model-performance claims.

**Add a Phase 2 feature**:
1. Reference `dataset_versions.id`, `dataset_configurations.id` — not raw uploads.
2. Create new Phase 2 tables; do not extend Phase 1 tables.
3. Do not modify Phase 1 ownership, lineage, or immutability.

---

## Glossary

| Term | Definition |
|---|---|
| SCM | Semantic Change Magnitude — structural/content change between two dataset versions (0–100) |
| DSI | Distribution Shift Index — feature distribution movement between versions (0–100) |
| MLRS | ML Training Readiness Risk Score — higher means more evidence issues (0–100, lower is better) |
| LRS | Leakage Risk Score — potential target leakage signal strength (0–100) |
| VRS | Variant Readiness Score — goal-weighted improvement score for a preprocessing variant (0–100, higher is better) |
| Fingerprint | Combined hash: file + schema + metadata + configuration + algorithm version |
| Recreation bundle | Version evidence package to verify a candidate CSV matches an immutable version |
| Diagnosis contract | Structured handoff: intervention options, human-decision flags, experiment constraints |
| Generation method | `"manual"` (user upload) or `"variant"` (generated by VariantGeneratorOrchestrator) |
| Completeness score | Server-computed protocol coverage 0–100 based on 10 required StudyConfiguration fields |
