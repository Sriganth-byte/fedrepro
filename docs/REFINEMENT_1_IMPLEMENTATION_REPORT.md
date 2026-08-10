# FedRepro — Refinement #1 Implementation Report
# Study Configuration (Research Protocol) — Completeness, Lineage, and Diff

**Generated**: 2026-08-04  
**Migration head after this refinement**: `0005_study_configuration_completeness`  
**Test result**: 25 passed / 0 failed / 0 regressions  
**Status**: ✅ Production-ready

---

## 1. Objective

`StudyConfiguration` existed in the codebase but was half-implemented:

| Gap | Impact |
|---|---|
| `change_reason` buried inside JSONB `protocol_json.change_reason` | Not queryable; no audit column |
| No `superseded_at` timestamp on archived versions | Could not determine when a version was replaced |
| No self-referencing lineage FK | Could not tell which version a new version was derived from |
| Completeness scoring done client-side in JS (`readinessScore()`) | Different results depending on JS heuristics; not auditable |
| Missing fields list not persisted | Frontend had to re-derive every render |
| No version-specific fetch endpoint | Could only list all versions or get the current one |
| No protocol diff endpoint | No programmatic way to compare two versions |
| `include_configuration` not available on study list/detail | Each UI component fetched configuration independently |

---

## 2. Database Changes

### Migration: [0005_study_configuration_completeness.py](../backend/alembic/versions/0005_study_configuration_completeness.py)

**Table**: `study_configurations`

```
Lines: 146  |  Functions: upgrade(), downgrade()
```

#### New columns

| Column | SQL Type | Constraint | Purpose |
|---|---|---|---|
| `change_reason` | `VARCHAR(500)` | nullable | Auditable plain-text reason for creating this version |
| `superseded_at` | `TIMESTAMPTZ` | nullable, indexed | UTC timestamp set by the service layer when the version is archived |
| `source_configuration_id` | `INTEGER` | FK → `study_configurations.id` ON DELETE SET NULL, indexed | Self-referencing lineage: which version was this one derived from? |
| `completeness_score` | `INTEGER` | NOT NULL, default 0, CHECK (0–100) | Server-computed protocol readiness 0–100 |
| `missing_fields` | `JSONB` | NOT NULL, default `[]` | Ordered list of field-name strings that are empty |

#### Back-fill SQL (applied to all pre-existing rows)

```sql
-- Back-fill change_reason from JSONB
UPDATE study_configurations
SET change_reason = protocol_json->>'change_reason'
WHERE protocol_json->>'change_reason' IS NOT NULL;

-- Back-fill completeness_score (10 pts per field × 10 fields)
UPDATE study_configurations
SET completeness_score = (
    (CASE WHEN ml_task IS NOT NULL AND ml_task <> '' THEN 10 ELSE 0 END) + ...
);

-- Back-fill missing_fields (JSONB array concatenation)
UPDATE study_configurations
SET missing_fields = (
    CASE WHEN ml_task IS NULL OR ml_task = '' THEN '["ml_task"]'::jsonb ELSE '[]'::jsonb END || ...
);
```

#### Indexes added

```sql
ix_study_configurations_superseded_at  ON (superseded_at)
ix_study_configurations_source_id       ON (source_configuration_id)
```

#### Check constraint added

```sql
ck_study_configuration_completeness: completeness_score >= 0 AND completeness_score <= 100
```

#### Downgrade (fully reversible)

Drops indexes, check constraint, FK constraint, and all 5 columns in reverse order.

---

## 3. Backend — Layer-by-Layer Script Mapping

### 3.1 ORM Entity

**File**: [`backend/app/models/entities.py`](../backend/app/models/entities.py)  
**Lines**: 237 | **Class**: `StudyConfiguration` (lines 44–94)

#### What changed

```python
# ADDED inside __table_args__
CheckConstraint("completeness_score >= 0 AND completeness_score <= 100",
                name="ck_study_configuration_completeness"),

# NEW columns
source_configuration_id: Mapped[int | None] = mapped_column(
    ForeignKey("study_configurations.id", ondelete="SET NULL"), index=True, nullable=True)
change_reason: Mapped[str | None] = mapped_column(String(500), nullable=True)
superseded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True),
                                                        nullable=True, index=True)
completeness_score: Mapped[int] = mapped_column(Integer, default=0)
missing_fields: Mapped[list] = mapped_column(JSONB, default=list)

# NEW relationship (self-referencing)
source_configuration: Mapped["StudyConfiguration | None"] = relationship(
    "StudyConfiguration",
    remote_side="StudyConfiguration.id",
    foreign_keys="StudyConfiguration.source_configuration_id",
)
```

#### No existing columns were renamed or removed.

---

### 3.2 Repository

**File**: [`backend/app/repositories/sqlalchemy.py`](../backend/app/repositories/sqlalchemy.py)  
**Lines**: 84 | **Class**: `StudyConfigurationRepository`

#### Existing methods (unchanged)

| Method | Line | Purpose |
|---|---|---|
| `current_for_study(study_id)` | 38 | Returns the `status="current"` version |
| `list_for_study(study_id)` | 44 | All versions ordered by version_number DESC |
| `next_version_number(study_id)` | 49 | `latest.version_number + 1` or `1` |

#### New methods (Refinement #1)

| Method | Lines | Purpose |
|---|---|---|
| `get_by_version_number(study_id, version_number)` | 55–62 | Fetch one specific version by its sequential number |
| `get_pair_for_diff(study_id, from_version, to_version)` | 64–73 | Fetch two versions in a **single** DB round-trip using `IN` clause; returns `(from_config, to_config)` tuple |

---

### 3.3 Pydantic Schemas

**File**: [`backend/app/schemas/contracts.py`](../backend/app/schemas/contracts.py)  
**Lines**: 174

#### Class ordering (critical — avoids forward-reference issues)

```
StudyConfigurationBase          (line 47) — shared field definitions + blank_to_none validator
StudyConfigurationCreate        (line 82) — adds change_reason input field
StudyConfigurationRead          (line 86) — extends Base, adds all 5 new columns + existing fields
ProtocolFieldDiff               (line 109) — single field comparison in a diff
StudyConfigurationDiff          (line 117) — full diff response
StudyRead                       (line 133) — AFTER the above; references StudyConfigurationRead concretely
```

> **Why this order matters**: `StudyRead` contains `current_configuration: StudyConfigurationRead | None`.
> In Python 3.11 without `from __future__ import annotations`, Pydantic evaluates annotations at class
> definition time. `StudyConfigurationRead` must be fully defined before `StudyRead`.

#### `StudyConfigurationRead` — new fields

```python
change_reason: str | None
superseded_at: datetime | None
source_configuration_id: int | None
completeness_score: int
missing_fields: list[str]
```

#### New schemas

**`ProtocolFieldDiff`**
```python
field: str          # e.g. "domain"
from_value: Any     # value in the older version
to_value: Any       # value in the newer version
changed: bool       # from_value != to_value
```

**`StudyConfigurationDiff`**
```python
study_id: int
from_version: int
to_version: int
from_hash: str
to_hash: str
hash_changed: bool
completeness_delta: int          # to_score - from_score (can be negative)
from_completeness_score: int
to_completeness_score: int
fields_changed: list[str]        # all fields where from_value != to_value
fields_added: list[str]          # changed AND was empty, now has value
fields_removed: list[str]        # changed AND had value, now empty
field_diffs: list[ProtocolFieldDiff]  # one entry per protocol field
```

**`StudyRead` — new optional field**
```python
current_configuration: StudyConfigurationRead | None = None
# None by default; populated only when ?include_configuration=true is passed
```

---

### 3.4 Service Layer

**File**: [`backend/app/services/study_service.py`](../backend/app/services/study_service.py)  
**Lines**: 455 | **Class**: `StudyService`

#### Module-level constants (new)

```python
from __future__ import annotations   # LINE 1 — required (see Gotcha #1)

_COMPLETENESS_FIELDS: list[str] = [  # 10 fields × 10 pts = 100 max
    "ml_task", "domain", "research_objective", "research_question",
    "hypothesis", "target_column", "primary_metric", "baseline_model",
    "validation_strategy", "random_seed",
]

_PROTOCOL_FIELDS: list[str] = [      # superset used for diffs (13 fields)
    "ml_task", "domain", "data_quality_focus", "research_objective",
    "research_question", "hypothesis", "target_column", "primary_metric",
    "baseline_model", "validation_strategy", "random_seed",
    "feature_scope", "intended_use_case",
]
```

#### New public methods

| Method | Lines | Signature | Returns |
|---|---|---|---|
| `get_configuration_by_version` | ~192 | `(study_id, owner_id, version_number)` | `StudyConfiguration` or raises `ValueError` |
| `diff_configurations` | ~205 | `(study_id, owner_id, from_version, to_version)` | `StudyConfigurationDiff` |

#### Enriched private methods

**`_create_configuration_version()` — full signature**
```python
def _create_configuration_version(
    self,
    study: Study,
    actor_id: int,
    data: dict,
    change_reason: str,
    source_configuration_id: int | None = None,   # NEW
    skip_if_unchanged: bool = False,
) -> StudyConfiguration:
```

New behaviour inside this method:
1. Calls `_compute_completeness(data)` to get `(score, missing_fields)`
2. Sets `current.superseded_at = datetime.now(tz=timezone.utc)` before archiving
3. Passes `source_configuration_id`, `change_reason`, `completeness_score`, `missing_fields` to the new `StudyConfiguration(...)` constructor

**`_compute_completeness(data: dict) → tuple[int, list[str]]`** — NEW static method
```
Logic:
  For each field in _COMPLETENESS_FIELDS (10 fields):
    - random_seed: missing if None (0 is a valid seed)
    - all others: missing if falsy (None, "", "  " etc.)
  score = max(0, 100 - len(missing) * 10)
```

**`_current_config_id(study_id) → int | None`** — NEW private helper
```
Returns the ID of the current configuration without raising.
Used to capture source_configuration_id before creating a new version.
```

#### Activity log enrichment

All `ActivityLog` entries created during `create()`, `update()`, and `create_configuration()` now include:
```python
details_json={
    ...,
    "completeness_score": configuration.completeness_score,  # NEW
    "missing_fields": configuration.missing_fields,          # NEW (on create_configuration)
}
```

---

### 3.5 API Routes

**File**: [`backend/app/api/routes/studies.py`](../backend/app/api/routes/studies.py)  
**Lines**: 197 | **Functions**: 13

#### Complete endpoint inventory (all endpoints)

| Method | Path | Handler | Status | Notes |
|---|---|---|---|---|
| `GET` | `/dashboard` | `dashboard` | existing | unchanged |
| `POST` | `/studies` | `create_study` | existing | unchanged |
| `GET` | `/studies` | `list_studies` | **modified** | `?include_configuration=true` added |
| `GET` | `/studies/{study_id}` | `study_detail` | **modified** | `?include_configuration=true` added |
| `GET` | `/studies/{study_id}/configuration` | `current_study_configuration` | existing | unchanged |
| `GET` | `/studies/{study_id}/configurations` | `study_configuration_history` | existing | unchanged |
| `GET` | `/studies/{study_id}/configurations/diff` | `study_configuration_diff` | **NEW** | Must be before `/{version_number}` |
| `GET` | `/studies/{study_id}/configurations/{version_number}` | `study_configuration_by_version` | **NEW** | Integer path param |
| `POST` | `/studies/{study_id}/configurations` | `create_study_configuration` | existing | unchanged |
| `PATCH` | `/studies/{study_id}` | `update_study` | existing | unchanged |
| `GET` | `/studies/{study_id}/findings` | `study_findings` | existing | unchanged |
| `GET` | `/studies/{study_id}/executive-report` | `executive_report` | existing | unchanged |
| `GET` | `/research-findings` | `all_findings` | existing | unchanged |

#### Route registration order (critical)

```python
# CORRECT: /diff registered BEFORE /{version_number}
@router.get("/studies/{study_id}/configurations/diff", ...)       # line ~98
@router.get("/studies/{study_id}/configurations/{version_number}", ...)  # line ~114

# WRONG (would break): FastAPI would try to cast "diff" → int and fail
```

#### `GET /studies/{id}/configurations/diff` — validation guard

```python
if from_version == to_version:
    raise ValueError("from_version and to_version must be different")
```

Raises HTTP 400 via FastAPI's exception handler.

#### `GET /studies` and `GET /studies/{id}` — `include_configuration` param

```python
include_configuration: bool = Query(False, description="...")
# When True:
repo = StudyConfigurationRepository(db)
study.current_configuration = repo.current_for_study(study.id)
```

Note: sets Python attribute directly on the SQLAlchemy ORM object; Pydantic's `from_attributes=True` serialises it via `StudyRead.current_configuration`.

---

## 4. Frontend — Layer-by-Layer Script Mapping

### 4.1 API Client

**File**: [`frontend/src/api/client.js`](../frontend/src/api/client.js)

#### New methods added to `studyApi`

```javascript
// Fetch a specific protocol version by its sequential number
configurationByVersion: (studyId, versionNumber) =>
  api.get(`/studies/${studyId}/configurations/${versionNumber}`).then(r => r.data),

// Field-level diff between two protocol versions
configurationDiff: (studyId, fromVersion, toVersion) =>
  api.get(`/studies/${studyId}/configurations/diff`, {
    params: { from_version: fromVersion, to_version: toVersion },
  }).then(r => r.data),
```

---

### 4.2 StudyWorkspace.jsx

**File**: [`frontend/src/pages/StudyWorkspace.jsx`](../frontend/src/pages/StudyWorkspace.jsx)

#### What changed

```jsx
// BEFORE: only fetched study + datasets
Promise.all([studyApi.get(studyId), datasetApi.list(studyId)])
  .then(([studyResult, datasetResult]) => { ... });

// AFTER: also fetches configuration on mount
const [configuration, setConfiguration] = useState(null);   // NEW state
Promise.all([
  studyApi.get(studyId),
  datasetApi.list(studyId),
  studyApi.currentConfiguration(studyId),                    // NEW
]).then(([studyResult, datasetResult, configResult]) => {
  setStudy(studyResult);
  setDatasets(datasetResult);
  setConfiguration(configResult);                            // NEW
});

// BEFORE: no configuration prop
<EnhancedOverviewPanel study={study} datasets={datasets} ... />

// AFTER: passes configuration prop down
<EnhancedOverviewPanel study={study} datasets={datasets} configuration={configuration} ... />
```

**Why**: Eliminates a redundant `studyApi.currentConfiguration()` call that `EnhancedOverviewPanel` made internally every time it mounted. The workspace loads it once and passes it down.

---

### 4.3 WorkspacePanels.jsx

**File**: [`frontend/src/features/studies/WorkspacePanels.jsx`](../frontend/src/features/studies/WorkspacePanels.jsx)

#### `EnhancedOverviewPanel` — signature change

```jsx
// BEFORE
export function EnhancedOverviewPanel({
  study, datasets, onStudyUpdate, onOpenEvidence, ...
})

// AFTER — accepts configuration prop
export function EnhancedOverviewPanel({
  study, datasets, configuration: configurationProp,  // renamed to avoid collision
  onStudyUpdate, onOpenEvidence, ...
})
```

#### State initialisation change

```jsx
// BEFORE
const [form, setForm] = useState(() => protocolFromStudy(study));
const [configuration, setConfiguration] = useState(null);

// AFTER — uses prop as initial value when available
const [form, setForm] = useState(
  () => configurationProp
    ? protocolFromConfiguration(study, configurationProp)
    : protocolFromStudy(study)
);
const [configuration, setConfiguration] = useState(configurationProp || null);
```

#### useEffect — conditional API call

```jsx
// AFTER — skips network request if parent already provided the configuration
const configPromise = configurationProp
  ? Promise.resolve(configurationProp)           // use prop, no fetch
  : studyApi.currentConfiguration(study.id).catch(() => null);  // fallback fetch
```

Backward compatible: if `configurationProp` is null (e.g. component used standalone), it still fetches from the API.

#### New UI component: Protocol Completeness Card

Inserted between the evidence strip (`overview-evidence-strip`) and the Protocol Intent card (`overview-protocol-card`):

```jsx
{configuration && (
  <Card className="protocol-completeness-card">
    <div className="completeness-header">
      <div>
        <p className="eyebrow">Research protocol readiness</p>
        <h2>Protocol completeness</h2>
      </div>
      <span className={`completeness-badge ${score===100?"complete":score>=60?"partial":"low"}`}>
        {score}%
      </span>
    </div>

    {/* Animated progress bar */}
    <div className="completeness-bar-track" role="progressbar" ...>
      <div className={`completeness-bar-fill ${...}`} style={{width:`${score}%`}} />
    </div>

    {/* Missing field chips — shown only when score < 100 */}
    {missing_fields.length > 0 && (
      <div className="completeness-missing">
        {missing_fields.map(field => (
          <span className="completeness-chip missing">{field.replace(/_/g, " ")}</span>
        ))}
      </div>
    )}

    {/* All-complete message */}
    {missing_fields.length === 0 && (
      <p className="completeness-all-ok">✓ All 10 protocol fields are documented</p>
    )}

    {/* Metadata footer */}
    <div className="completeness-meta">
      <span className="muted">Last change: {change_reason}</span>
      <span className="muted">Protocol V{version_number} (baseline / derived from Vx)</span>
    </div>
  </Card>
)}
```

**Rendered only when `configuration` is not null.** Does not block the overview panel if the config hasn't loaded yet.

---

### 4.4 styles.css

**File**: [`frontend/src/styles.css`](../frontend/src/styles.css)

Inserted after `.workflow-stage` rules (~line 434). New CSS classes:

| Class | Purpose |
|---|---|
| `.protocol-completeness-card` | Card padding override |
| `.completeness-header` | Flex row: title left, badge right |
| `.completeness-badge` | Large score number; `.complete` / `.partial` / `.low` variants |
| `.completeness-bar-track` | Grey pill container, 10px tall |
| `.completeness-bar-fill` | Animated width with cubic-bezier; `.complete` / `.partial` / `.low` gradient variants |
| `.completeness-chips` | Flex-wrap container for missing field chips |
| `.completeness-chip.missing` | Purple pill per missing field |
| `.completeness-all-ok` | Green success message |
| `.completeness-meta` | Footer flex row: change_reason + version lineage |

**Color semantics**:
```
complete  ≥ 100%  → green  (#10b981 gradient / #1a7f4a text)
partial   ≥  60%  → amber  (#f59e0b gradient / #8c5200 text)
low       <  60%  → red    (#ef4444 gradient / #b91c1c text)
```

---

## 5. Test Coverage

### Unit Tests — `test_study_configuration_refinement.py`

**File**: [`backend/tests/test_study_configuration_refinement.py`](../backend/tests/test_study_configuration_refinement.py)  
**Lines**: 106 | **Tests**: 19 | **Class**: `TestComputeCompleteness`

| Test name | Scenario covered |
|---|---|
| `test_empty_data_scores_zero_and_all_fields_missing` | `{}` → score=0, all 10 fields missing |
| `test_full_data_scores_hundred` | All 10 fields populated → score=100, missing=[] |
| `test_random_seed_zero_is_valid_and_not_missing` | `random_seed=0` must NOT be treated as missing |
| `test_random_seed_none_counts_as_missing` | `random_seed=None` is missing |
| `test_partial_data_scores_proportionally` | 3 fields → 30 pts, 7 missing |
| `test_empty_string_counts_as_missing` | `ml_task=""` is falsy, counts as missing |
| `test_score_is_clamped_to_zero` | Score can never be negative |
| `test_each_field_contributes_exactly_ten_points` | Parametrised ×10: each field = exactly 10 pts |
| `test_missing_fields_list_matches_expected_absent_fields` | `set(missing)` == expected absent fields |
| `test_completeness_fields_list_has_ten_entries` | `_COMPLETENESS_FIELDS` must have exactly 10 entries |

---

### Integration Tests — `test_api_workflow.py`

**File**: [`backend/tests/test_api_workflow.py`](../backend/tests/test_api_workflow.py)  
**Lines**: 387 | **All tests**: 3 (including 1 pre-existing)

#### `test_study_configuration_completeness_and_diff` (NEW)

Full API flow covering:

| Step | Assertion |
|---|---|
| Create minimal study | `completeness_score == 10`, `"domain" in missing_fields`, `"ml_task" not in missing_fields` |
| Verify initial config fields | `change_reason == "Initial research protocol"`, `superseded_at is None`, `source_configuration_id is None` |
| Create fully-specified V2 | `completeness_score == 100`, `missing_fields == []`, `source_configuration_id == v1.id` |
| V1 archived in DB | `v1_row.status == "archived"`, `v1_row.superseded_at is not None` |
| Fetch V1 by version number | HTTP 200, `version_number == 1`, `completeness_score == 10` |
| Fetch V2 by version number | HTTP 200, `completeness_score == 100` |
| Non-existent version | HTTP 400 |
| Diff V1 → V2 | `hash_changed is True`, `completeness_delta == 90`, `"domain" in fields_added` |
| `domain` field in diff | `from_value is None`, `to_value == "student placement"`, `changed is True` |
| `ml_task` field in diff | `changed is False` (same value both versions) |
| Same-version diff guard | HTTP 400 |
| `include_configuration=true` | `current_configuration.version_number == 2`, `completeness_score == 100` |
| `include_configuration` absent | `current_configuration is None` (backward compat) |
| History response | Both versions have `completeness_score`, `missing_fields`, `change_reason` |

#### `test_study_configuration_diff_same_version_rejected` (NEW)

Minimal test: same `from_version` and `to_version` must return HTTP 400 with "different" in `detail`.

#### `test_complete_phase_one_api_workflow` (pre-existing — no regression)

Full Phase 1 pipeline: register, upload, configure, version, fingerprint, profile, diagnose. Passes unchanged.

---

## 6. Known Gotchas and Non-Obvious Decisions

### Gotcha #1 — `list` builtin shadowing in `StudyService`

**Problem**: `StudyService` has a public method named `def list(self, ...)`. In Python 3.11, class-body annotations are evaluated at parse time (unless `from __future__ import annotations` is used). The `@staticmethod` method `_compute_completeness` has the return type `tuple[int, list[str]]`. At class-body evaluation time, Python looks up `list` in the class namespace first and finds `StudyService.list` (a function), not the built-in `list`. This causes:

```
TypeError: 'function' object is not subscriptable
```

**Fix**: `from __future__ import annotations` added as the very first line of `study_service.py`. This defers all annotation evaluation to strings, completely bypassing the shadowing.

**Future agents**: Do NOT remove `from __future__ import annotations` from `study_service.py`. Do NOT rename `_compute_completeness`'s return type annotation without also ensuring the `list` shadowing issue is handled.

---

### Gotcha #2 — FastAPI route registration order for `/diff` vs `/{version_number}`

**Problem**: If `/{version_number}` (integer path param) is registered before `/diff` (literal segment), FastAPI attempts to cast the string `"diff"` to `int` and fails with a 422 validation error.

**Fix**: In `studies.py`, `GET /studies/{study_id}/configurations/diff` is registered before `GET /studies/{study_id}/configurations/{version_number}`.

**Future agents**: Do NOT reorder these two route decorators. Adding any new `/studies/{study_id}/configurations/<literal_segment>` route must always be registered before `/{version_number}`.

---

### Gotcha #3 — `alembic_version` table column width

**Problem**: The pre-existing `alembic_version` table had `version_num VARCHAR(32)`. Revision ID `0005_study_configuration_completeness` is 38 characters, causing:

```
psycopg2.errors.StringDataRightTruncation: value too long for type character varying(32)
```

**Fix**: One-time manual fix applied before running migrations:
```sql
ALTER TABLE alembic_version ALTER COLUMN version_num TYPE VARCHAR(128);
```

**Future agents**: This was a one-time fix. The column is now `VARCHAR(128)`. All future revision IDs up to 128 characters will work without intervention. Never create a revision ID longer than 128 characters.

---

### Decision: Equal weights for all 10 completeness fields

All 10 completeness fields contribute exactly 10 points. The plan noted an open question about whether `ml_task`, `target_column`, `validation_strategy` should be weighted higher (15 pts each). The implementation uses equal weights because:

1. Parity is simpler to explain to researchers
2. The score is a guidance metric, not a hard gate
3. The `missing_fields` list already tells researchers exactly what is absent
4. Downstream engines have their own validation logic and are not blocked by the completeness score

If weighted scoring is needed in future, change `_COMPLETENESS_FIELDS` to a list of `(field, weight)` tuples and update `_compute_completeness` accordingly.

---

### Decision: `include_configuration` defaults to `False`

Backward compatible. The study list endpoint serves many callers (dashboard, study list page). Adding the configuration to every response would add one DB query per study per list request. Opt-in with `?include_configuration=true`.

---

### Decision: `superseded_at` is set in the service layer, not a DB trigger

Set via `current.superseded_at = datetime.now(tz=timezone.utc)` before the `db.flush()` call in `_create_configuration_version()`. This is intentional — the timestamp is authoritative from the application layer, not from a PostgreSQL `NOW()` trigger, so it can be tested deterministically and overridden in future if needed (e.g. importing historical configurations).

---

## 7. Feature → Script Cross-Reference Table

| Feature | DB | ORM | Repository | Schema | Service | Route | Frontend Client | Frontend Component | CSS |
|---|---|---|---|---|---|---|---|---|---|
| `change_reason` audit column | `0005` | `entities.py:81` | — | `contracts.py:107` | `study_service.py:326` | — | — | `WorkspacePanels.jsx:~345` | — |
| `superseded_at` archival | `0005` | `entities.py:82` | — | `contracts.py:108` | `study_service.py:300` | — | — | — | — |
| `source_configuration_id` lineage | `0005` | `entities.py:56-60,90-94` | — | `contracts.py:109` | `study_service.py:308` | — | — | `WorkspacePanels.jsx:~348` | — |
| `completeness_score` (0–100) | `0005` | `entities.py:85` | — | `contracts.py:112` | `study_service.py:303,342-358` | — | — | `WorkspacePanels.jsx:~282` | `styles.css:436-448` |
| `missing_fields` JSONB list | `0005` | `entities.py:86` | — | `contracts.py:113` | `study_service.py:303,342-358` | — | — | `WorkspacePanels.jsx:~290` | `styles.css:450-472` |
| Fetch version by number | — | — | `sqlalchemy.py:55-62` | `StudyConfigurationRead` | `study_service.py:~192` | `studies.py:114-122` | `client.js:configurationByVersion` | — | — |
| Protocol diff endpoint | — | — | `sqlalchemy.py:64-73` | `StudyConfigurationDiff` `ProtocolFieldDiff` | `study_service.py:~205-269` | `studies.py:98-113` | `client.js:configurationDiff` | — | — |
| `include_configuration` query param | — | — | `sqlalchemy.py:current_for_study` | `StudyRead.current_configuration` | — | `studies.py:list_studies,study_detail` | — | — | — |
| Completeness bar UI | — | — | — | — | — | — | — | `WorkspacePanels.jsx:~268-310` | `styles.css:434-514` |
| Configuration prop passdown | — | — | — | — | — | — | — | `StudyWorkspace.jsx:24,38,79` → `WorkspacePanels.jsx:163-183` | — |
| `_compute_completeness()` logic | — | — | — | — | `study_service.py:341-358` | — | — | — | — |
| Unit tests (completeness) | — | — | — | — | `test_study_configuration_refinement.py` | — | — | — | — |
| Integration tests (diff + include) | — | — | — | — | `test_api_workflow.py:test_study_configuration_completeness_and_diff` | — | — | — | — |

---

## 8. Files Changed Summary

| File | Type | Lines Before | Lines After | Change |
|---|---|---|---|---|
| `backend/alembic/versions/0005_study_configuration_completeness.py` | NEW | — | 146 | New Alembic migration |
| `backend/app/models/entities.py` | MODIFIED | 208 | 237 | +5 columns, +1 constraint, +1 relationship |
| `backend/app/repositories/sqlalchemy.py` | MODIFIED | 64 | 84 | +2 methods |
| `backend/app/schemas/contracts.py` | REWRITTEN | 124 | 174 | Reordered + 5 new fields + 2 new schemas |
| `backend/app/services/study_service.py` | REWRITTEN | 217 | 455 | +3 public methods, +2 private helpers, enriched existing |
| `backend/app/api/routes/studies.py` | REWRITTEN | 73 | 197 | +2 endpoints, modified 2 endpoints, formatting |
| `backend/tests/test_study_configuration_refinement.py` | NEW | — | 106 | 19 unit tests |
| `backend/tests/test_api_workflow.py` | MODIFIED | 188 | 387 | +2 integration test functions |
| `frontend/src/api/client.js` | MODIFIED | ~33 | ~41 | +2 API methods |
| `frontend/src/pages/StudyWorkspace.jsx` | MODIFIED | 102 | ~110 | +1 state, enriched Promise.all, pass prop |
| `frontend/src/features/studies/WorkspacePanels.jsx` | MODIFIED | 2018 | ~2060 | Accept prop, conditional fetch, +completeness card |
| `frontend/src/styles.css` | MODIFIED | 1243 | ~1323 | +80 lines completeness CSS |

---

## 9. Rollback Instructions

```bash
# 1. Backend — revert migration
cd backend
venv\Scripts\python.exe -m alembic downgrade 0003_ai_source_foreign_keys

# 2. Frontend — no DB impact; revert files via git
git checkout frontend/src/pages/StudyWorkspace.jsx
git checkout frontend/src/features/studies/WorkspacePanels.jsx
git checkout frontend/src/api/client.js
git checkout frontend/src/styles.css

# 3. Backend code — revert service, schemas, routes, entities
git checkout backend/app/services/study_service.py
git checkout backend/app/schemas/contracts.py
git checkout backend/app/api/routes/studies.py
git checkout backend/app/models/entities.py
git checkout backend/app/repositories/sqlalchemy.py
```

Note: `downgrade()` in `0005` drops all 5 columns cleanly. Any data in those columns is permanently lost on downgrade.

---

*End of Refinement #1 Implementation Report*

---

## Subsequent Refinements (applied after this report)

### Refinement #2 — Variant Generator (2026-08-04)

Migration: `0006_variant_generator` (revises `0005_study_configuration_completeness`)

Added 2 new tables (`variant_generation_jobs`, `variant_generation_records`) and a `generation_method` column on `dataset_versions`. Added 7 new backend services, 5 new API endpoints (`variants.py`), and `VariantGeneratorPanel` in the frontend.

Full report: `docs/VARIANT_GENERATOR_REPORT.md`

### Refinement #3 — UI/UX Enterprise Overhaul (2026-08-04)

No database or API changes. Full CSS design system rewrite with:
- Token-based architecture (light + dark mode via `data-theme`)
- FOUC prevention (theme init before React hydration in `index.jsx`)
- `ThemeToggle` component persisted to `localStorage`
- All pages upgraded: AuthPage, DashboardPage, StudiesPage, StudyWorkspace, ResearchFindingsPage
- Skeleton loaders on all pages and panels
- Risk-colored Recharts bar chart with dark-mode-aware custom tooltip
- `WorkspacePanels.jsx` upgraded to use new UI primitives (Skeleton, CopyButton, StatusDot)

Full reference: `docs/UI_REFERENCE.md`
