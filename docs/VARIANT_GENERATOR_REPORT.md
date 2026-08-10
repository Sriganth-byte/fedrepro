# FedRepro — Variant Generator Implementation Report

**Generated**: 2026-08-05  
**Migration**: `0006_variant_generator` (revises `0005_study_configuration_completeness`)  
**Status**: ✅ Production-ready

---

## 1. Objective

Before this refinement, FedRepro could diagnose dataset quality issues (MLRS/LRS) but provided no mechanism to act on them. Researchers had to manually decide which preprocessing transformations to apply and implement them outside the platform. This broke reproducibility and left a gap between diagnosis and evidence-backed variant creation.

The Variant Generator closes this gap by:
1. Translating diagnosis findings deterministically into pipeline requirements
2. Planning N candidate preprocessing pipelines (no AI selection)
3. Building each pipeline by transforming the source CSV
4. Evaluating each variant with the same ProfilingService → DiagnosisService stack (so MLRS/LRS are always deterministic)
5. Ranking by a Variant Readiness Score (VRS) tied to the researcher's chosen optimization goal
6. Allowing the top variant to be promoted as a new immutable DatasetVersion with `generation_method="variant"`

---

## 2. Database Changes

### Migration: `0006_variant_generator.py`

#### New Table: `variant_generation_jobs`

| Column | Type | Description |
|---|---|---|
| `id` | INTEGER PK | |
| `source_version_id` | INT FK → dataset_versions CASCADE | Which version is being varied |
| `diagnosis_report_id` | INT FK → diagnosis_reports SET NULL | Diagnosis that drives issue interpretation |
| `optimization_goal` | VARCHAR(64) | One of 6 valid goals |
| `constraints_json` | JSONB | User-supplied constraints (allowed/excluded transformations, cost cap) |
| `job_constraints_hash` | VARCHAR(64) | Hash of constraints for deduplication |
| `status` | VARCHAR(32) | `pending` → `running` → `completed` / `failed` |
| `total_variants_planned` | INTEGER | Set when planning completes |
| `total_variants_completed` | INTEGER | Incremented as records finish |
| `error_message` | TEXT | Set on failure |
| `created_at` | TIMESTAMPTZ | |
| `completed_at` | TIMESTAMPTZ | |

Indexes: `ix_vjobs_source_version_id`, `ix_vjobs_status`, `ix_vjobs_constraints_hash`

#### New Table: `variant_generation_records`

| Column | Type | Description |
|---|---|---|
| `id` | INTEGER PK | |
| `job_id` | INT FK → variant_generation_jobs CASCADE | |
| `variant_version_id` | INT FK → dataset_versions SET NULL | Set when promoted to a version |
| `pipeline_id` | VARCHAR(32) | Human-readable ID (e.g. "PIPELINE_A") |
| `pipeline_hash` | VARCHAR(64) | Hash of sorted steps (deduplication) |
| `pipeline_steps_json` | JSONB | Ordered list of step objects |
| `random_seed` | INTEGER | Seed used for reproducible transformations |
| `execution_time_seconds` | FLOAT | |
| `estimated_cost` | VARCHAR(16) | `very_low/low/medium/high` |
| `mlrs_before` | FLOAT | MLRS of source version |
| `mlrs_after` | FLOAT | MLRS of the variant (re-diagnosed) |
| `lrs_after` | FLOAT | |
| `lrs_caveat` | VARCHAR(64) | e.g. `"mi_selection_expected"` |
| `missing_values_pct_before/after` | FLOAT | |
| `class_balance_score_before/after` | FLOAT | |
| `feature_count_before/after` | INTEGER | |
| `row_count_before/after` | INTEGER | |
| `vrs_score` | FLOAT | 0–100, goal-weighted |
| `vrs_rank` | INTEGER | 1 = best |
| `goal_satisfaction` | VARCHAR(16) | `excellent/good/fair/poor` |
| `explanation_json` | JSONB | Per-step deterministic explanations |
| `status` | VARCHAR(32) | `pending/running/completed/failed` |
| `error_message` | TEXT | |
| `created_at` | TIMESTAMPTZ | |

Indexes: `ix_vrecords_job_id`, `ix_vrecords_variant_version_id`, `ix_vrecords_vrs_rank`

#### Column on `dataset_versions`: `generation_method`
- `VARCHAR(32)`, nullable
- `NULL` or `"manual"` = user-uploaded dataset version
- `"variant"` = promoted from a `VariantGenerationRecord`
- Index: `ix_dataset_versions_generation_method`

---

## 3. Service Architecture

```
POST /versions/{id}/variant-jobs
  ↓
variants.py (route)
  ↓ creates VariantGenerationJob (status=pending)
  ↓ BackgroundTasks.add_task(run_variant_job_background, job_id)
  ↓ returns VariantJobRead immediately

Background Task:
  VariantGeneratorOrchestrator.run_job(job_id, db)
    1. IssueInterpreterService.interpret(diagnosis, profile)
         → requirements dict (bool flags + severity + dataset properties)
    2. PipelinePlannerService.plan(requirements, goal, constraints)
         → List[PipelineSpec] (N pipelines, deterministic, deduplicated by hash)
    3. For each pipeline:
         VariantBuilderService.build(source_df, pipeline, config)
           → BuildResult (output_csv_path, before/after metrics)
         VariantEvaluatorService.evaluate(build_result, source_mlrs, goal, pipeline, config)
           → EvaluationResult (mlrs_after, lrs_after, vrs_score, goal_satisfaction, components)
         ExplanationEngineService.explain(pipeline_steps)
           → explanation_json (per-step deterministic text)
         Persist VariantGenerationRecord
    4. Rank all completed records by vrs_score DESC → set vrs_rank
    5. Update job status to "completed"

Polling: GET /variant-jobs/{id} returns job + all records with current status
```

---

## 4. Metric Details

### 4.1 IssueInterpreterService

Maps `DiagnosisReport.findings_json` finding codes to boolean/severity requirements:

| Finding code | Requirements key | Detail key |
|---|---|---|
| MISSINGNESS | `needs_missing_value_handling` | `missing_values_pct` |
| DUPLICATES | `has_duplicates` | — |
| OUTLIERS | `needs_outlier_treatment` | `outlier_severity` |
| CORRELATION | `needs_feature_reduction` | `high_correlation_detected` |
| CLASS_IMBALANCE | `needs_class_balancing` | `class_imbalance_severity` |
| TARGET_LEAKAGE | `needs_leakage_fix` | — |
| TARGET_SKEW | `has_target_skew` | — |
| SCALING | `needs_scaling` | — |

Also sets `needs_encoding=True` if any categorical columns detected in profile.

### 4.2 PipelinePlannerService

**Step ordering** (always fixed, never re-ordered):
```
1. duplicate_removal
2. missing_value_handling
3. encoding
4. outlier_treatment
5. class_balancing
6. feature_reduction
7. scaling
```

**Goal weights** (each row sums to 1.0):

| Goal | mlrs | miss | bal | feat | cost |
|---|---|---|---|---|---|
| maximize_accuracy | 0.40 | 0.25 | 0.20 | 0.10 | 0.05 |
| faster_training | 0.25 | 0.20 | 0.15 | 0.15 | 0.25 |
| lightweight_dataset | 0.25 | 0.20 | 0.10 | 0.20 | 0.25 |
| improve_recall | 0.30 | 0.20 | 0.35 | 0.10 | 0.05 |
| fairness | 0.25 | 0.20 | 0.40 | 0.10 | 0.05 |
| explainable_model | 0.30 | 0.20 | 0.15 | 0.25 | 0.10 |

**Conflict pairs** (never in the same pipeline):
- `iqr_filtering` ↔ `isolation_forest`
- `correlation_filter` ↔ `mutual_information`

**Deduplication**: pipeline hash = SHA-256 of sorted step IDs. Duplicate pipelines are discarded.

### 4.3 VRS Formula

```python
VRS = (
    w["mlrs"] * max(0, (source_mlrs - mlrs_after) / max(source_mlrs, 1))
  + w["miss"] * missing_reduction
  + w["bal"]  * class_balance_score
  + w["feat"] * feature_score      # direction depends on goal
  + w["cost"] * cost_score         # very_low=1.0, low=0.75, medium=0.50, high=0.25
) * 100
```

**Goal satisfaction thresholds**:
- VRS ≥ 80 → `"excellent"`
- VRS ≥ 60 → `"good"`
- VRS ≥ 40 → `"fair"`
- VRS < 40 → `"poor"`

**LRS caveat**: when `mutual_information` is in pipeline steps, `lrs_caveat = "mi_selection_expected"` — mutual information feature selection uses target column information, which mechanically elevates LRS. This is expected and noted, not an error.

---

## 5. API Endpoints

```
POST  /api/versions/{version_id}/variant-jobs
      Body: { optimization_goal, constraints_json }
      → Creates job, starts BackgroundTask
      → Returns VariantJobRead immediately (status=pending)
      → Runs synchronously if source CSV < SYNC_ROW_THRESHOLD (5000) rows

GET   /api/versions/{version_id}/variant-jobs
      → List all jobs for this version

GET   /api/variant-jobs/{job_id}
      → Full job + all records sorted by vrs_rank
      → Use for polling (poll every 2s while status=running)

POST  /api/variant-jobs/{job_id}/records/{record_id}/register
      → Promotes the variant CSV to a new DatasetVersion
      → Runs full fingerprint + semantic diff + profile + diagnosis pipeline
      → Sets generation_method="variant" on the new version
      → Returns the new DatasetVersion

GET   /api/versions/{version_id}/variant-tree
      → Returns source version + all variant children as a lineage tree
```

---

## 6. Frontend: `VariantGeneratorPanel`

Located in `WorkspacePanels.jsx`, exported as `VariantGeneratorPanel`.

**Props**: `version` (selected DatasetVersion), `diagnosis` (DiagnosisReport)

**User flow**:
1. Select optimization goal (6 clickable cards)
2. Configure constraints (max variants, allowed transformations, excluded transformations, cost cap)
3. Click "Generate Variants" → `variantApi.createJob(version.id, payload)`
4. Panel polls `variantApi.getJob(jobId)` every 2 seconds while status = `"running"`
5. When complete: displays ranked result cards with VRS score, MLRS reduction, pipeline steps
6. "Register as Version" on any record → `variantApi.registerVariant()` → new DatasetVersion appears in Evidence + Versions tabs

**Previous jobs**: if jobs exist for the selected version, they appear in a history list below the result cards and can be clicked to reload.

---

## 7. Tests

`backend/tests/test_variant_services.py` covers:
- `IssueInterpreterService`: all finding codes mapped correctly, severity normalization
- `PipelinePlannerService`: step ordering enforced, conflict pairs rejected, deduplication works, goal preferences applied
- `VariantBuilderService`: transformations applied correctly, BuildResult metrics computed
- `VariantEvaluatorService`: VRS formula, goal_satisfaction thresholds, lrs_caveat detection

---

## 8. Files Added / Modified

```text
backend/alembic/versions/0006_variant_generator.py              [NEW]
backend/app/models/entities.py                                  [MODIFIED] +VariantGenerationJob, +VariantGenerationRecord, +generation_method
backend/app/schemas/contracts.py                                [MODIFIED] +VariantJobCreate, VariantJobRead, VariantRecordRead
backend/app/api/routes/variants.py                              [NEW]
backend/app/main.py                                             [MODIFIED] +variants router
backend/app/services/issue_interpreter_service.py               [NEW]
backend/app/services/pipeline_planner_service.py                [NEW]
backend/app/services/transformation_knowledge_base.py           [NEW]
backend/app/services/variant_builder_service.py                 [NEW]
backend/app/services/variant_evaluator_service.py               [NEW]
backend/app/services/variant_generator_orchestrator.py          [NEW]
backend/app/services/explanation_engine_service.py              [NEW]
backend/tests/test_variant_services.py                          [NEW]
frontend/src/api/client.js                                      [MODIFIED] +variantApi
frontend/src/features/studies/WorkspacePanels.jsx               [MODIFIED] +VariantGeneratorPanel
frontend/src/styles.css                                         [MODIFIED] +variant panel CSS
```

---

## 9. Current Update: Diagnosis And Startup Evidence Integration (2026-08-11)

The Variant Generator is now integrated with the same per-version diagnosis and evidence warmup workflow used by manual dataset versions.

### Current behavior

- A generated variant is registered as a normal immutable `DatasetVersion`.
- The variant version receives a synthetic `DatasetRegistration`.
- The variant version receives a copied `DatasetConfiguration`.
- The variant version receives a `DatasetFingerprint`.
- The variant version receives parent-linked semantic SCM/DSI evidence.
- The variant version receives profile and diagnosis evidence through `DatasetWorkflowService.run_diagnosis()`.
- The variant version can receive AI diagnosis interpretation, executive summary, and dataset explanation report when AI is enabled.
- The Diagnosis page displays VRS through the linked `VariantGenerationRecord`.

### Invariant

Variant versions must not be treated as a separate evidence type in the UI. Once saved, they are first-class dataset versions and must support:

- version selector visibility
- diagnosis status
- `Run Diagnosis`
- `Recompute Diagnosis`
- profile report
- diagnosis report
- SCM/DSI when a parent exists
- MLRS/LRS
- VRS when linked to a variant record
- fingerprint and recreation evidence
- AI explanations and reports when enabled

### Startup repair

`EvidenceWarmupService` scans variant-generated versions on startup exactly like manual versions. If a variant version is missing profile, diagnosis, semantic evidence, deterministic report payload, or AI cache, the warmup process fills it and saves it for quick rendering.

If SCM/DSI or diagnosis rows exist but were produced by stale ruleset versions, the warmup path recomputes them using the existing deterministic services. No metric formulas were changed by this integration.
