# FedRepro Phase 1 Implementation Report

**Assessment date:** 5 July 2026  
**System:** FedRepro 1.0.0  
**Scope:** Repository implementation, database migrations, deterministic analysis services, API, web client, security controls, and executable verification

## 1. Executive summary

FedRepro Phase 1 is an implemented, working data-centric machine-learning research framework. It captures dataset evidence before model experimentation and preserves a traceable chain from study definition through upload, configuration, immutable versioning, fingerprinting, semantic comparison, profiling, diagnosis, and optional AI explanation.

The implementation has a sound separation of responsibilities:

- React presents study and evidence workflows.
- FastAPI routes translate HTTP requests and enforce authenticated ownership.
- Application services coordinate evidence lifecycle operations.
- Deterministic services calculate all profiles, change scores, findings, and risk scores.
- SQLAlchemy and PostgreSQL retain structured evidence and audit records.
- Local storage retains staged and immutable CSV files.
- Ollama is optional and receives only already-calculated evidence for explanation.

The current build is appropriate for Phase 1 research use and local or controlled deployment. The main limitations are production hardening rather than missing core workflow: development credentials remain in defaults and documentation, file storage is local to one host, automated coverage is narrow, long analyses execute synchronously, and operational controls such as rate limiting, backup policy, observability, and CI enforcement are not yet implemented.

**Overall assessment:** Phase 1 is functionally complete and internally consistent. It should be treated as a strong research-grade baseline, not yet as an internet-facing, multi-node production service.

## 2. Assessment method and implementation inventory

The assessment reviewed the source under `backend/app`, `backend/tests`, `frontend/src`, the three Alembic revisions, configuration files, and project documentation. Claims were checked against executable behavior where the local environment supported it.

| Measure | Observed implementation |
|---|---:|
| Backend Python files | 35 |
| Backend and test source lines | 943 |
| Frontend JavaScript/JSX files | 12 |
| Frontend source lines | 240 |
| FastAPI route operations | 17 |
| SQLAlchemy domain entities | 13 |
| Alembic revisions | 3 |
| Automated tests | 2 |
| Workspace tabs | 8 |

The compact source size is a strength for auditability, although it also reflects the intentionally limited Phase 1 scope.

## 3. Scope and system boundaries

### 3.1 Implemented Phase 1 workflow

1. Create an authenticated study for classification, regression, or clustering.
2. Register a CSV as dataset evidence.
3. Parse the file and persist registration metadata.
4. Apply task-aware configuration and validate it against the study.
5. Promote the staged file into an immutable version location.
6. Generate file, schema, metadata, configuration, and combined fingerprints.
7. Link the version to its parent and record a lineage event.
8. For version 2 and later, compute semantic difference evidence.
9. Generate a deterministic global and task-specific profile.
10. Generate structured diagnosis findings, MLRS, and LRS.
11. Optionally ask Ollama to explain a persisted evidence record.

### 3.2 Explicit exclusions

The implementation deliberately does not generate dataset variants, train models, compare model performance, compute model-impact findings, or calculate a reproducibility score. These are suitable future phases because Phase 1 already exposes stable version, configuration, fingerprint, profile, diagnosis, and lineage identifiers.

## 4. Architecture

```text
React web client
        |
        v
FastAPI routes and JWT ownership checks
        |
        v
Application services
  |          |             |
  v          v             v
Repositories  Deterministic analysis  Optional AI explanation
  |          |             |
  v          v             v
PostgreSQL   Persisted JSONB evidence  Local Ollama
        \
         -> Local staged and immutable CSV storage
```

Routes are thin and mostly perform transport translation. `StudyService`, `DatasetWorkflowService`, and `ReportingService` coordinate use cases. Profiling, semantic difference, fingerprinting, and diagnosis are separate deterministic services. Repository ports and SQLAlchemy adapters provide a modest abstraction boundary for study and dataset access.

The strongest architectural decision is that AI does not sit in the calculation path. `AIExplanationService` accepts persisted evidence, uses a constrained prompt, stores the source evidence hash, and links the result to its semantic-diff, profile, or diagnosis source record.

## 5. Backend implementation

### 5.1 Authentication and tenancy

Registration and login issue HS256 JWT access tokens. Passwords use bcrypt through Passlib. Protected routes resolve the token subject to a user and filter studies, datasets, registrations, and versions by owner.

This is sufficient for single-role Phase 1 access control. There is no refresh-token lifecycle, revocation mechanism, role model, password reset, account lockout, or rate limiting.

### 5.2 Dataset registration and storage

`LocalFileStorage` enforces the Phase 1 CSV boundary, strips path components from uploaded names, generates server-side staging names, streams in 1 MiB chunks, rejects files beyond the configured 100 MiB limit, rejects empty files, and parses the CSV before registration. Duplicate columns and zero-column files are rejected.

The registration record stores file size, original name, notes, inferred dtypes, column names, missing values, duplicates, memory use, and validation status. Promotion verifies that the source is inside the staging tree, creates a study/dataset directory, and refuses to overwrite an existing version path.

### 5.3 Configuration and workflow transaction

`DatasetWorkflowService.configure_and_analyze` validates the task-specific configuration, calculates a canonical configuration hash, selects the previous dataset version, promotes the file, and creates all downstream records in one database transaction. If analysis fails, the transaction rolls back and the promoted file is moved back to staging when possible.

Repeated configuration of a completed registration is idempotent at the service boundary: the existing version is returned instead of creating a duplicate.

### 5.4 Fingerprinting and lineage

Every version stores:

- SHA-256 file hash
- schema hash
- metadata hash
- configuration hash
- combined fingerprint
- fingerprint algorithm version (`fingerprint-1.0`)
- parent version identifier
- lineage event with evidence

Combined fingerprints are indexed but are not globally unique after migration `0002`, allowing identical evidence to appear legitimately in different contexts.

### 5.5 Semantic change

For version 2 and later, `SemanticDiffService` records column additions and removals, dtype changes, row and column count changes, aggregate missingness change, numeric feature mean shifts, and supervised target-distribution change.

Schema Change Magnitude is bounded to 0–100:

```text
SCM = 100 × (0.55 × schema change
           + 0.25 × proportional row change
           + 0.20 × absolute missingness change)
```

Dataset Shift Indicator is also bounded to 0–100:

```text
DSI = 100 × (0.45 × average numeric distribution shift
           + 0.35 × target distribution shift
           + 0.20 × proportional row change)
```

The implementation is deterministic and versioned as `semantic-1.0`. The method is intentionally lightweight: numeric shift is standardized mean movement rather than a statistical distance or hypothesis test, and categorical feature shift is only calculated for the configured target.

### 5.6 Profiling

`ProfilingService` produces:

- dataset dimensions, missingness, duplicate counts, and type counts;
- per-column dtype, role, cardinality, and missingness;
- numeric quartiles, mean, standard deviation, skewness, and IQR outliers;
- top values for non-numeric columns;
- correlations at absolute value 0.8 or above for numeric datasets up to 200 columns;
- classification balance and minority-class evidence;
- regression target skew, outliers, missingness, and descriptive statistics;
- clustering scale spread, dimensionality, and high-dimensionality indicators.

The persisted report identifies `profile-1.0`, enabling later algorithm changes without silently altering earlier evidence.

### 5.7 Diagnosis and risk scores

Diagnosis rules cover missingness, duplicate observations, feature outliers, high correlations, class imbalance, skewed regression targets, incompatible clustering scales, dataset drift, and potential target leakage. Findings contain a stable code, issue, severity, evidence, risk statement, and recommendation.

ML Risk Score combines the most severe finding with average severity:

```text
MLRS = 0.55 × maximum severity weight
     + 0.45 × average severity weight
```

Severity weights are low 25, medium 50, high 75, and critical 100.

Lineage Risk Score is the bounded sum of missing-parent, undocumented-version, schema-change, and dataset-shift components:

```text
LRS = min(100,
          missing-parent penalty
        + documentation penalty
        + min(50, SCM × 0.50)
        + min(35, DSI × 0.35))
```

The ruleset is stored as `diagnosis-1.0`. Scores are transparent prioritization aids; they should not be interpreted as calibrated probabilities.

### 5.8 Optional AI explanation

AI is disabled by default. When enabled, the service calls Ollama with low temperature, caps response length, prohibits new calculations and invented findings in the prompt, and stores model name, prompt version, source record foreign key, source evidence hash, and generated text.

This design provides evidence binding and useful provenance. It does not provide output-schema validation, prompt-injection filtering for malicious dataset text, content moderation, or model availability management.

## 6. Data model and migrations

The 13 entities form a clear evidence graph:

| Area | Entities | Purpose |
|---|---|---|
| Identity | `users` | Account and ownership root |
| Research | `studies` | Task and research context |
| Evidence intake | `datasets`, `dataset_registrations` | Logical dataset and validated upload event |
| Reproducibility | `dataset_configurations`, `dataset_versions`, `dataset_fingerprints`, `lineage_events` | Immutable evidence definition and provenance |
| Analysis | `semantic_diff_reports`, `dataset_profile_reports`, `diagnosis_reports` | Versioned deterministic outputs |
| AI | `ai_generated_explanations` | Evidence-bound optional interpretation |
| Audit | `activity_logs` | User and workflow events |

PostgreSQL JSONB is used appropriately for structured reports that may evolve, while identifiers, ownership, version numbering, and scores remain relational and indexable. Unique constraints prevent multiple versions per registration and duplicate version numbers within a dataset. Foreign-key delete behavior was refined in migration `0002`, and migration `0003` added direct AI-to-evidence foreign keys.

## 7. API and frontend implementation

The API exposes authentication, dashboard, study CRUD subset, dataset registration, configuration, version detail, semantic difference, profiling, diagnosis, research findings, and AI explanation. OpenAPI documentation is mounted at `/api/docs`.

The React client uses protected routing, Axios API access, lazy-loaded pages, and an eight-tab study workspace:

1. Overview
2. Dataset Evidence
3. Dataset Configuration
4. Versioning & Fingerprints
5. Semantic Changes
6. Dataset Profiling
7. Data Diagnosis
8. AI Insights

Dashboard and diagnosis views use Recharts. The interface surfaces algorithm/ruleset identifiers and explicitly states that AI does not calculate SCM or DSI. The codebase uses plain CSS and compact reusable UI components.

Frontend strengths are direct mapping to the evidence lifecycle and low conceptual overhead. Current limitations include no frontend test suite, limited accessibility evidence, limited global error handling, no background-job progress model, and no administrative or operational interface.

## 8. Security and privacy assessment

### Implemented controls

- bcrypt password hashing;
- expiring signed JWTs;
- owner-scoped protected queries;
- CORS allowlist for local development;
- server-generated storage names;
- filename path stripping and slugging;
- staged-path containment check before promotion;
- upload size and extension enforcement;
- parameterized SQLAlchemy access;
- AI disabled by default;
- no raw CSV body stored in PostgreSQL.

### Material hardening needs

| Priority | Finding | Recommended action |
|---|---|---|
| Critical before public deployment | Default database credentials and JWT secret are present in configuration/documentation. | Require secrets from environment or a secret manager; fail startup when defaults are used outside development; rotate existing values. |
| High | Local files are not encrypted, replicated, or governed by retention policy. | Define encryption-at-rest, backup, retention, deletion, and restore procedures; use durable object storage for multi-node deployment. |
| High | Authentication lacks throttling, revocation, refresh tokens, and password lifecycle controls. | Add rate limits, security event logging, token rotation/revocation, password policy, and recovery flows. |
| High | CSV parsing can still consume substantial memory/CPU within the size limit. | Add row/column limits, parser timeouts or worker isolation, MIME/content checks, and resource quotas. |
| Medium | AI output is free text and prompts may contain untrusted evidence strings. | Add output validation, prompt-injection defenses, escaping/redaction policy, and explicit user-facing provenance. |
| Medium | No privacy classification or sensitive-column workflow exists. | Add PII detection/labeling, access policy, consent/retention metadata, and redaction/export controls. |

## 9. Verification results

Verification was rerun on 5 July 2026 in the supplied workspace.

| Check | Result | Evidence |
|---|---|---|
| Alembic upgrade | Passed | PostgreSQL reported `0003_ai_source_foreign_keys (head)` |
| Backend tests | Passed | 2 tests passed in 2.59 seconds |
| Deterministic contract test | Passed | SCM, DSI, profile, MLRS, LRS, and finding schema validated |
| Authenticated API workflow | Passed | Register, create study, upload, configure, fingerprint, profile, and diagnose |
| Frontend production build | Passed | Webpack 5.108.4 compiled successfully |
| Production dependency audit | Passed | 0 known production vulnerabilities; 74 production dependencies |

These checks establish that the principal workflow works in the current environment. They do not establish high coverage, performance under load, cross-browser behavior, disaster recovery, penetration resistance, or AI quality. The repository contains two automated tests, so the verification claim should remain deliberately narrow.

## 10. Quality assessment

### Strengths

- Evidence-first domain model with clear ownership and lineage.
- Deterministic, inspectable, versioned calculations.
- Transactional workflow with a filesystem compensation path.
- Strong separation between calculation and AI explanation.
- Task-aware behavior for classification, regression, and clustering.
- Compact codebase with clear extension points.
- Database constraints and migrations align with the service lifecycle.
- UI structure mirrors the research workflow.

### Limitations and technical debt

- Only two automated tests; many thresholds, validation branches, authorization cases, rollback paths, and migration behaviors are untested.
- Synchronous profiling and diagnosis will hold an API request for large datasets.
- Pandas loads complete CSVs into memory during registration and analysis.
- Concurrent configuration of two registrations for one dataset can race on version numbering.
- Local filesystem and database commit are not one atomic transaction; compensation reduces but cannot eliminate split-brain failure modes.
- Error translation maps domain `ValueError` to HTTP 400, including some not-found cases that would conventionally be 404.
- Reporting queries may become inefficient as studies and versions grow.
- No structured telemetry, correlation IDs, performance metrics, or health checks for PostgreSQL/storage/Ollama.
- No automated frontend, accessibility, end-to-end browser, load, security, or backup-restore tests.
- Version labels are constants in code rather than an externally governed algorithm registry.

## 11. Recommended roadmap

### Before external or production deployment

1. Remove development secrets from defaults and documentation; add environment validation.
2. Expand authorization and negative-path tests, including cross-owner access.
3. Introduce durable object storage, backups, retention rules, and restore testing.
4. Add rate limiting, security headers, audit monitoring, and token lifecycle controls.
5. Run analysis in background jobs with progress, retry, cancellation, and resource limits.
6. Add database locking or a version-allocation strategy to prevent concurrency races.

### Next engineering increment

1. Add unit tests for every deterministic threshold and task branch.
2. Add integration tests for version 2 semantic comparison, rollback, idempotency, and AI source linking.
3. Add React component and end-to-end workflow tests.
4. Add structured logging, request IDs, dependency health checks, and service metrics.
5. Define algorithm documentation and golden datasets for regression testing.
6. Improve API semantics with typed domain errors and 404/409/422 mappings.

### Phase 2 readiness

Future variant generation or model experiments should reference immutable version and configuration IDs. New calculated outputs should retain the same pattern used here: deterministic service, explicit algorithm version, persisted evidence, relational source link, and optional downstream explanation.

## 12. Conclusion

FedRepro Phase 1 implements its stated evidence-management objective. Its central design choices—immutable dataset versions, canonical fingerprints, explicit lineage, deterministic and versioned analysis, structured findings, and evidence-bound optional AI—create a credible foundation for reproducible ML research.

The system is ready for continued research use and Phase 2 development. Production readiness depends on operational and security hardening, broader automated verification, and a scalable execution/storage model rather than a redesign of the core domain.
