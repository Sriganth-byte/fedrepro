# FedRepro — System Architecture

**Last Updated**: 2026-08-05  
**Migration Head**: `0006_variant_generator`  
**Status**: Phase I production-ready

---

## 1. Dependency Direction

```
React UI (Webpack/port 3000)
  └── axios /api client
        └── FastAPI routes (port 8000, prefix /api)
              └── Application services
                    ├── Deterministic domain services  ← own ALL metrics
                    ├── Repository ports (SQLAlchemy)
                    └── LocalFileStorage
                          └── PostgreSQL + immutable CSV files
```

**Key invariant**: Routes contain HTTP translation only. Services coordinate use cases. Repositories contain persistence. Deterministic services own every metric output. AI/Ollama is isolated and receives only already-persisted evidence.

---

## 2. Runtime Stack

| Layer | Technology |
|---|---|
| Backend framework | FastAPI + Uvicorn |
| ORM / persistence | SQLAlchemy 2.0 async-compatible, Alembic migrations |
| Database | PostgreSQL (`postgresql+psycopg2://localhost:5432/fedrepo`) |
| Data processing | Pandas, NumPy, scikit-learn |
| Report generation | python-docx |
| AI integration | Ollama (optional, `AI_ENABLED=false` by default) |
| Frontend framework | React 18 + React Router 6 |
| Bundler | Webpack 5 |
| HTTP client | Axios (660 s timeout) |
| Charts | Recharts |
| Icons | lucide-react |
| File storage | Local filesystem under `uploads/` |

---

## 3. Database Schema

### 3.1 Migration Chain

```
0001_phase1_schema               — All Phase 1 tables
0002_evidence_lifecycle          — Cascade FKs, combined fingerprint index
0003_ai_source_foreign_keys      — Optional FKs from AIExplanation to evidence
0004_study_configurations        — StudyConfiguration table
0005_study_configuration_completeness — +5 columns, completeness scoring
0006_variant_generator           — variant_generation_jobs/records + generation_method
```

### 3.2 Entity Relationships

```
User
 └── Study (owner_id FK)
       └── Dataset (study_id FK)
             └── DatasetRegistration  (staged CSV + metadata)
                   └── DatasetConfiguration  (task-aware config + hash)
                         └── DatasetVersion  (immutable CSV + version_number + generation_method)
                               ├── DatasetFingerprint     (file/schema/metadata/combined hashes)
                               ├── LineageEvent           (creation evidence record)
                               ├── SemanticDiffReport     (SCM + DSI vs parent)
                               ├── DatasetProfileReport   (deterministic profile JSON)
                               ├── DiagnosisReport        (findings + MLRS + LRS)
                               └── VariantGenerationJob   (source_version_id FK)
                                     └── VariantGenerationRecord (pipeline + VRS score)

Study
 └── StudyConfiguration (versioned protocol config + completeness_score)
       └── self-reference: source_configuration_id (lineage)

AIGeneratedExplanation  → Study, SemanticDiffReport?, DatasetProfileReport?, DiagnosisReport?
ActivityLog             → used for both event stream and deterministic report payload storage
```

### 3.3 Key Column Notes

| Entity | Notable Columns |
|---|---|
| `DatasetVersion` | `version_number`, `parent_version_id`, `file_hash`, `generation_method` |
| `DatasetFingerprint` | `file_hash`, `schema_hash`, `metadata_hash`, `combined_fingerprint`, `algorithm_version` |
| `SemanticDiffReport` | `scm_score`, `dsi_score`, `ruleset_version` |
| `DiagnosisReport` | `mlrs_score`, `lrs_score`, `findings_json`, `ruleset_version` |
| `StudyConfiguration` | `completeness_score`, `missing_fields` (JSONB), `change_reason`, `superseded_at`, `source_configuration_id` |
| `VariantGenerationJob` | `optimization_goal`, `constraints_json`, `status`, `total_variants_planned/completed` |
| `VariantGenerationRecord` | `pipeline_steps_json`, `vrs_score`, `vrs_rank`, `mlrs_before/after`, `lrs_after`, `goal_satisfaction` |

---

## 4. Evidence Lifecycle

```
1. STUDY CREATION
   User defines ML task, research objective, research question, hypothesis,
   target column, baseline model, validation strategy, random seed.
   → Study + StudyConfiguration (completeness_score computed server-side)

2. DATASET REGISTRATION
   User uploads CSV (max size enforced, CSV-only in Phase 1).
   → DatasetRegistration (staged CSV path + row/col metadata)
   → Explanation report payload stored in ActivityLog

3. DATASET CONFIGURATION
   User selects task, target column, encoding strategy.
   DatasetWorkflowService orchestrates atomically:
     a. Promote staged CSV → uploads/datasets/study-{id}/dataset-{id}/v{N}.csv (immutable)
     b. Create DatasetVersion (version_number per dataset, parent_version_id set)
     c. Generate DatasetFingerprint (algorithm: fingerprint-1.0)
     d. If V2+: generate SemanticDiffReport (ruleset: semantic-1.2)
     e. Generate DatasetProfileReport (profiler: profile-1.0)
     f. Generate DiagnosisReport (ruleset: diagnosis-2.0, MLRS + LRS + findings)
     g. Store report payloads in ActivityLog

4. DIAGNOSIS CONTRACT
   DiagnosisContractService converts diagnosis + profile + version into a
   structured handoff contract for variant planning and experiment constraints.

5. VARIANT GENERATION (Phase 1 extension)
   POST /versions/{id}/variant-jobs creates VariantGenerationJob.
   BackgroundTask runs VariantGeneratorOrchestrator:
     a. IssueInterpreterService: diagnosis findings → requirements dict
     b. PipelinePlannerService: requirements → N candidate pipelines (deterministic)
     c. VariantBuilderService: apply pipeline transformations to source CSV
     d. VariantEvaluatorService: ProfilingService → DiagnosisService on variant CSV → VRS
     e. Rank by VRS, persist VariantGenerationRecord rows
     f. Optional: register top-ranked variant as a new DatasetVersion

6. AI EXPLANATION (optional, evidence-bound)
   Requires AI_ENABLED=true + running Ollama instance.
   AIExplanationService receives ONLY already-persisted evidence.
   Cannot modify any deterministic score.
   Evidence hash stored with every explanation.
```

---

## 5. Metric Computation

### 5.1 SCM — Semantic Change Magnitude
**Computed by**: `SemanticDiffService` (ruleset `semantic-1.2`)  
**Compares**: previous version CSV vs current version CSV  
**Inputs**: schema movement, dtype changes, row count delta, row content turnover, duplicate rates, missingness deltas, numeric distribution shifts, categorical distribution shifts, target distribution changes  
**Output**: float 0–100. Higher = larger structural/content change between versions.

### 5.2 DSI — Distribution Shift Index
**Computed by**: `SemanticDiffService` (same run as SCM)  
**Measures**: distributional movement across numeric and categorical features  
**Output**: float 0–100. Higher = greater feature distribution movement between versions.

### 5.3 MLRS — ML Training Readiness Risk Score
**Computed by**: `DiagnosisService` (ruleset `diagnosis-2.0`)  
**Inputs**: profile findings (missingness, duplicates, outliers, correlation, class imbalance, target skew, scaling hints, drift detection, target leakage signals)  
**Algorithm**: weighted sum of finding severities across 9 finding codes  
**Output**: float 0–100. Higher = more evidence issues, higher training risk. **Lower is better.**

### 5.4 LRS — Leakage Risk Score
**Computed by**: `DiagnosisService` (same run as MLRS)  
**Measures**: potential target leakage and invalid evaluation signals  
**Output**: float 0–100. Higher = stronger leakage evidence. Independent of MLRS.

### 5.5 VRS — Variant Readiness Score
**Computed by**: `VariantEvaluatorService`  
**Formula**: `VRS = w_mlrs × MLRS_reduction + w_miss × missing_reduction + w_bal × class_balance + w_feat × feature_score + w_cost × cost_score` × 100  
**Weights**: goal-dependent (6 goals: `maximize_accuracy`, `faster_training`, `lightweight_dataset`, `improve_recall`, `fairness`, `explainable_model`)  
**Output**: float 0–100. Higher = better variant for the chosen goal.

### 5.6 Protocol Completeness Score
**Computed by**: `StudyService._compute_completeness()`  
**Evaluated fields (10, 10 pts each)**: `ml_task`, `domain`, `research_objective`, `research_question`, `hypothesis`, `target_column`, `primary_metric`, `baseline_model`, `validation_strategy`, `random_seed`  
**Edge case**: `random_seed = 0` is VALID and scores full points. Only `None` is missing.  
**Output**: int 0–100. Stored in `completeness_score` DB column.

---

## 6. Service Catalogue

| Service | File | Responsibility |
|---|---|---|
| `StudyService` | `study_service.py` | Create/update/list studies; compute + persist completeness score |
| `DatasetWorkflowService` | `dataset_workflow_service.py` | Full registration→version→fingerprint→diff→profile→diagnosis orchestration |
| `LocalFileStorage` | `storage/local_storage.py` | CSV staging, immutable promotion, deletion guards |
| `FingerprintService` | `fingerprint_service.py` | File/schema/metadata/combined hash computation (`fingerprint-1.0`) |
| `SemanticDiffService` | `semantic_diff_service.py` | SCM + DSI computation across two version dataframes (`semantic-1.2`) |
| `ProfilingService` | `profiling_service.py` | Deterministic per-column + task-specific profile (`profile-1.0`) |
| `DiagnosisService` | `diagnosis_service.py` | MLRS + LRS + findings (`diagnosis-2.0`) |
| `DiagnosisContractService` | `diagnosis_contract_service.py` | Structured handoff contract for variant planning |
| `DiagnosisReportExportService` | `diagnosis_report_service.py` | `.docx` diagnosis reports via python-docx |
| `ExecutiveReportService` | `executive_report_service.py` | `.docx` study-level executive reports |
| `DatasetExplanationReportService` | `dataset_explanation_report_service.py` | Deterministic registration + version report JSON payloads |
| `AIExplanationService` | `ai_explanation_service.py` | Evidence-bound Ollama calls (`explanation-1.8`); gated by `AI_ENABLED` |
| `ReportingService` | `reporting_service.py` | Dashboard counts, activity feed, recent diagnoses |
| `IssueInterpreterService` | `issue_interpreter_service.py` | Diagnosis findings → requirements dict for PipelinePlanner |
| `PipelinePlannerService` | `pipeline_planner_service.py` | Requirements → N deterministic candidate pipelines |
| `TransformationKnowledgeBase` | `transformation_knowledge_base.py` | All available transformations, cost estimates, conflict rules |
| `VariantBuilderService` | `variant_builder_service.py` | Apply pipeline steps to source CSV, produce variant CSV |
| `VariantEvaluatorService` | `variant_evaluator_service.py` | Profile + diagnose variant CSV, compute VRS |
| `VariantGeneratorOrchestrator` | `variant_generator_orchestrator.py` | Full job coordination: interpret → plan → build → evaluate → rank |
| `ExplanationEngineService` | `explanation_engine_service.py` | Deterministic explanation text for variant pipeline steps |

---

## 7. API Route Map

### Auth (`/api/auth`)
| Method | Path | Description |
|---|---|---|
| POST | `/auth/register` | Create user + return JWT |
| POST | `/auth/login` | Authenticate + return JWT |

### Dashboard + Studies (`/api`)
| Method | Path | Description |
|---|---|---|
| GET | `/dashboard` | Counts + recent activity + recent diagnoses |
| POST | `/studies` | Create study |
| GET | `/studies` | List owned studies (`?search=&ml_task=&include_configuration=`) |
| GET | `/studies/{id}` | Get study (`?include_configuration=`) |
| PATCH | `/studies/{id}` | Update study |
| GET | `/studies/{id}/findings` | Study-scoped findings |
| GET | `/studies/{id}/executive-report` | Download .docx |
| GET | `/research-findings` | All studies' findings |
| GET | `/studies/{id}/configuration` | Current (latest) configuration |
| GET | `/studies/{id}/configurations` | Full configuration history |
| POST | `/studies/{id}/configurations` | Create new configuration version |
| GET | `/studies/{id}/configurations/diff` | Field-level diff between two versions |
| GET | `/studies/{id}/configurations/{version_number}` | Specific version |

### Datasets + Versions (`/api`)
| Method | Path | Description |
|---|---|---|
| POST | `/studies/{id}/datasets/register` | Upload CSV + register |
| GET | `/studies/{id}/datasets` | List datasets with versions |
| GET | `/registrations/{id}` | Registration detail |
| GET | `/registrations/{id}/explanation-report` | Registration report |
| POST | `/registrations/{id}/configure` | Configure + promote to version |
| GET | `/versions/{id}` | Version detail |
| GET | `/versions/{id}/analysis` | Full version analysis (version+profile+diagnosis+timeline) |
| DELETE | `/versions/{id}` | Delete version |
| GET | `/versions/{id}/semantic-diff` | Semantic diff detail |
| GET | `/versions/{id}/compare` | On-demand comparison (`?against_version_id=`) |
| GET | `/versions/{id}/recreation-bundle` | Recreation evidence JSON |
| POST | `/versions/recreate/verify` | Verify candidate CSV against bundle |
| GET | `/versions/{id}/profile` | Profile report |
| GET | `/versions/{id}/diagnosis` | Diagnosis report |
| GET | `/versions/{id}/diagnosis-contract` | Diagnosis contract for variant planning |
| GET | `/versions/{id}/diagnosis-report` | Download .docx |
| GET | `/versions/{id}/explanation-report` | Version explanation report |
| POST | `/versions/{id}/explanation-report/generate` | Generate version explanation report |

### Variant Generator (`/api`)
| Method | Path | Description |
|---|---|---|
| POST | `/versions/{id}/variant-jobs` | Create + run variant generation job |
| GET | `/versions/{id}/variant-jobs` | List jobs for version |
| GET | `/variant-jobs/{id}` | Get job + all records (polling) |
| POST | `/variant-jobs/{id}/records/{record_id}/register` | Promote top variant to a new DatasetVersion |
| GET | `/versions/{id}/variant-tree` | Lineage tree (source + all variants) |

### AI (`/api/ai`)
| Method | Path | Description |
|---|---|---|
| POST | `/ai/studies/{id}/explain` | General evidence-bound explanation |
| POST | `/ai/studies/{id}/semantic-diffs/{diff_id}/metrics-interpretation` | Metrics explanation |
| POST | `/ai/studies/{id}/semantic-diffs/{diff_id}/interpretation` | Narrative diff interpretation |
| POST | `/ai/studies/{id}/versions/{version_id}/executive-summary` | Version executive summary |
| POST | `/ai/studies/{id}/versions/{version_id}/diagnosis-interpretation` | Diagnosis narrative |

---

## 8. Frontend Route Map

| URL | Component | Description |
|---|---|---|
| `/login` | `AuthPage` | Login + register |
| `/dashboard` | `DashboardPage` | Metrics, risk chart, activity feed |
| `/studies` | `StudiesPage` | Protocol builder + study directory |
| `/studies/:studyId` | `StudyWorkspace` | Tabbed workspace (5 tabs) |
| `/findings` | `ResearchFindingsPage` | Cross-study evidence summary |
| `*` | redirect | → `/dashboard` |

All non-login routes are guarded by `AuthContext.authenticated`.

---

## 9. Deterministic Evidence Invariants

1. **AI never computes metrics.** All scores (MLRS, LRS, SCM, DSI, VRS, fingerprints, profiles) are computed by deterministic services only.
2. **Dataset versions are immutable.** After promotion from staging, the CSV file is never modified.
3. **Idempotent configure.** If a registration is already configured, `configure_and_analyze` returns the existing version.
4. **Version numbering.** Per dataset, incrementing from the latest. V1 has no semantic diff.
5. **Algorithm versioning.** Every artifact carries a version string: `fingerprint-1.0`, `semantic-1.2`, `profile-1.0`, `diagnosis-2.0`, `explanation-1.8`.
6. **Storage guards.** Deletion of version files is constrained to the configured dataset storage root path.
7. **ActivityLog dual use.** Used for the event stream AND as the payload store for deterministic report JSON.

---

## 10. Extension Points

**Phase 2 experiment modules** should:
- Reference `dataset_versions.id` and `dataset_configurations.id` — never mutable uploads.
- Join against `dataset_profile_reports` and `diagnosis_reports` for pre-computed evidence.
- Not modify Phase 1 ownership, lineage, or immutability contracts.
- Register results in new Phase 2 tables; do not extend Phase 1 tables with experiment-specific columns.
