# FedRepro — UI Component & Page Reference

**Last Updated**: 2026-08-05  
**Stack**: React 18, React Router 6, Recharts, lucide-react, Webpack 5  
**Design System**: Token-based CSS with light/dark mode (`data-theme` attribute)

---

## 1. Design System Overview

All styling lives in `frontend/src/styles.css`. It uses CSS custom properties (design tokens) for every value — color, spacing, radius, shadow, duration.

### 1.1 Token Architecture

```css
/* Color tokens — set on :root (light) and [data-theme="dark"] */
--color-primary         /* Indigo-600 */
--color-primary-soft    /* Indigo translucent bg */
--color-secondary       /* Blue-500 */
--color-success         /* Emerald-500 */
--color-warning         /* Amber-500 */
--color-danger          /* Red-500 */
--color-surface         /* Page card background */
--color-surface-2       /* Slightly elevated surface */
--color-surface-3       /* Hover/input states */
--color-border          /* Subtle 1px border */
--color-text            /* Primary text */
--color-text-soft       /* Body text */
--color-text-muted      /* Labels, secondary info */
--color-text-subtle     /* Disabled / placeholder */
--chart-grid            /* Recharts grid line color */

/* Spacing tokens */
--sp-1 → --sp-8         /* 4px → 40px scale */

/* Radius tokens */
--radius-sm, --radius-md, --radius-lg, --radius-full

/* Shadow tokens */
--shadow-1 → --shadow-4  /* Elevation levels */

/* Motion tokens */
--duration-fast, --duration-enter
--ease-out
```

### 1.2 Theme Toggle
- Theme is persisted to `localStorage.fedrepro-theme` (`"light"` | `"dark"`).
- Applied to `document.documentElement` as `data-theme="dark"`.
- Initial theme applied in `index.jsx` BEFORE React renders to prevent FOUC.
- `ThemeToggle` component in `AppLayout.jsx` topbar handles switching.

---

## 2. Shared Component Library (`components/UI.jsx`)

| Component | Props | Usage |
|---|---|---|
| `Card` | `className`, `...rest` | Standard content card with border + shadow |
| `Button` | `variant`, `loading`, `className` | Primary/secondary/ghost; shows spinner when `loading=true` |
| `Field` | `label`, `full`, `hint` | Form field wrapper with label and optional hint text |
| `Badge` | `tone` | Inline status chip. Tones: `success`, `warning`, `high`, `medium`, `low`, `info`, `neutral` |
| `Notice` | `error`, `warning`, `success` | Semantic alert block with icon (AlertCircle/AlertTriangle/CheckCircle2) |
| `PageHeader` | `eyebrow`, `title`, `description`, `action` | Page-level heading section with right-side action slot |
| `Empty` | `icon`, `action` | Empty state with optional icon and CTA button |
| `MetricCard` | `icon`, `label`, `value`, `trend`, `trendLabel` | KPI card with trend indicator |
| `DataTable` | `columns`, `rows`, `empty`, `emptyIcon` | Sortable table with built-in empty state |
| `Skeleton` | `width`, `height`, `radius` | Animated loading placeholder |
| `SkeletonCard` | `lines` | Card-shaped skeleton with N placeholder lines |
| `CopyButton` | `value` | Clipboard copy button with tick-on-success |
| `ThemeToggle` | — | Light/dark mode switcher persisted to localStorage |
| `StatusDot` | `status` | Colored dot: `active/completed` = green, `running` = amber, `failed` = red |

---

## 3. Application Shell (`AppLayout.jsx`)

**Route**: all authenticated routes  
**Role**: persistent sidebar + topbar wrapper using `<Outlet />`

### Sidebar
- FedRepro brand link → `/dashboard`
- Navigation items: Dashboard, ML Studies, Research Findings
- Each item has icon + label + description (hidden when collapsed)
- `Collapse` button saves sidebar width preference in component state
- Phase I Active status card at bottom (shows when expanded)
- Mobile: hamburger → drawer overlay with scrim close

### Topbar
- Context title + subtitle (derived from current route path)
- `ThemeToggle` (moon/sun icon toggles dark mode)
- Researcher chip (avatar initials + "Authenticated" label)
- Sign out button → calls `logout()` + navigates to `/login`

### Theme Initialization
`index.jsx` runs `localStorage.getItem("fedrepro-theme")` before `createRoot` to set `data-theme` on `<html>` — prevents flash of unstyled content.

---

## 4. Auth Page (`AuthPage.jsx`)

**Route**: `/login` (public)

### Layout
Split two-panel: left visual panel (hidden on mobile) + right form panel.

### Left Panel (Visual)
- FedRepro brand
- Hero copy: "Evidence before experimentation."
- Three proof-point cards: Deterministic, Reproducible, Evidence-first

### Right Panel (Form)
- Mode toggle: **login** ↔ **register** (no page navigation — state switch)
- Login fields: Email, Password
- Register fields: Name, Email, Password
- Submit button shows `<Loader2 className="spin">` while `loading=true`
- Error displayed via `<Notice error>`
- `authApi.login()` / `authApi.register()` → sets token → navigates to `/dashboard`

---

## 5. Dashboard Page (`DashboardPage.jsx`)

**Route**: `/dashboard`  
**Data**: `dashboardApi.get()` → single API call

### Loading State
4 `<SkeletonCard>` in a grid while data is null.

### KPI Strip (4 `MetricCard` components)
| Card | Value source |
|---|---|
| Total studies | `data.total_studies` |
| Datasets registered | `data.total_datasets` |
| Dataset versions | `data.total_versions` |
| High-risk studies | `data.high_risk_studies` (MLRS ≥ 70) |

### Risk Chart (`BarChart` via Recharts)
- Data: `data.recent_diagnoses` — last N diagnosed versions
- X-axis: `V{version_id}`
- Bars: MLRS (color-coded by score) + LRS (fixed blue)
- MLRS bar color: green if <40, amber if 40–69, red if ≥70 (via `<Cell>` per bar)
- Custom tooltip using CSS variable colors (works in dark mode)

### Activity Feed
- Data: `data.recent_activity` — recent `ActivityLog` events
- Displayed via `<DataTable>` with columns: Activity, Type (Badge), Time

### Quick-Access Navigation Cards
Three cards linking to Studies, Dataset Evidence, Research Findings.

---

## 6. Studies Page (`StudiesPage.jsx`)

**Route**: `/studies`  
**Purpose**: Create a new study + browse existing studies

### Left Column — Protocol Builder Form

Three numbered sections:

**Section 1 — Study Identity**
- Study name (required)
- Dataset domain
- ML task (select: classification / regression / clustering)

**Section 2 — Research Intent**
- Data quality focus
- Primary evaluation metric
- Target column (hidden for clustering)
- Feature scope / Grouping goal
- Research objective (textarea)
- Research question (textarea)
- Hypothesis (textarea)

**Section 3 — Reproducibility Controls**
- Controlled baseline model
- Validation strategy
- Random seed (numeric)
- Intended research use (textarea)

**Submit**: `studyApi.create(payload)` → navigates to `/studies/{id}`  
Button shows spinner while `creating=true`.

### Right Column — Protocol Preview Card

- **Readiness bar**: animated CSS width, color = red/amber/green based on score
- **Score**: computed by `readinessScore(form)` — checks 9 boolean conditions
- **Readiness message**: encourages completion if < 80%
- **Three protocol preview rows**: Research question, Objective, Reproducibility controls

### Right Column — Study Directory

- Search input (Enter key triggers filter)
- ML task dropdown filter
- Filter button → `studyApi.list(search, taskFilter)`
- `<DataTable>` with columns: Study (link), Task (Badge), Status (Badge), Updated

---

## 7. Study Workspace (`StudyWorkspace.jsx`)

**Route**: `/studies/:studyId`  
**Purpose**: Top-level workspace state owner + tab router

### Initial Load
`Promise.all([studyApi.get, datasetApi.list, studyApi.currentConfiguration])` runs on mount.

### Loading State
`<WorkspaceSkeleton>` renders header + tab placeholders while study is null.

### State Owned
| State | Description |
|---|---|
| `study` | Study record |
| `datasets` | All datasets with versions |
| `configuration` | Current study configuration |
| `active` | Active tab ID |
| `version` | Selected `DatasetVersion` |
| `profile` | Profile report for selected version |
| `diagnosis` | Diagnosis report for selected version |
| `diagnosisContract` | Contract for variant planning |
| `semanticHistory` | Timeline events |
| `versionLoading` | True while `selectVersion()` is running |
| `versionStatus` | Status/error message string |

### `selectVersion(idOrVersion, nextActive)` 
Calls `datasetApi.analysis(id)` → populates version/profile/diagnosis/semanticHistory. Optionally calls `datasetApi.diagnosisContract(id)`. Switches to `nextActive` tab on success.

### Tab Bar (5 tabs)
| Tab | Panel Component | Key Props Passed |
|---|---|---|
| Overview | `EnhancedOverviewPanel` | study, datasets, configuration, selectedVersion, diagnosis, diagnosisContract |
| Dataset Evidence | `EnhancedEvidencePanel` | study, datasets, refresh, onVersion |
| Versions & Fingerprints | `VersionPanel` | study, datasets, selectedVersion, profile, semanticHistory, onVersion, onDelete |
| Diagnosis | `DiagnosisPanel` | study, datasets, version, profile, diagnosis, initialContract, onOpenVariants |
| Variant Generator | `VariantGeneratorPanel` | version, diagnosis |

Tab switch: `key={active}` on workspace-body triggers CSS enter animation.

### Header Area
- Back link → `/studies`
- `<PageHeader>` with task label + dataset count
- Version loading spinner (inline, only when `versionLoading`)
- `V{id} selected` Badge when a version is active
- `<Notice>` for `versionStatus` (auto-detects success/error tone from message content)

---

## 8. Research Findings Page (`ResearchFindingsPage.jsx`)

**Route**: `/findings`  
**Data**: `studyApi.allFindings()` → list of `{study, evidence}` objects

### Loading State
3 `<SkeletonCard>` while `loading=true`.

### Empty State
`<Empty icon={BookOpenCheck}>` with explanation text.

### Per-Study Card
For each study:
- **Header**: study name, ML task, back-link to workspace
- **Stats strip**: dataset count, version count, average MLRS, peak risk Badge (color-coded)
- **Dataset grid**: each dataset shows name, version count, latest MLRS Badge, latest LRS Badge

---

## 9. Workspace Panels (`WorkspacePanels.jsx`)

2,500-line file housing all five tab panels plus many sub-components.

### 9.1 `EnhancedOverviewPanel`

**Shows**: Study protocol, workflow stage checklist, evidence integrity panel, gaps list, activity timeline, AI brief, export actions.

**Protocol editing**: `editing=true` shows an inline protocol form using `StudyConfiguration` fields. On save, `studyApi.createConfiguration()` creates a new configuration version with `completeness_score` computed server-side.

**Workflow stages** (8 stages, computed booleans):
`Protocol → Dataset Evidence → Configuration → Versioning → Diagnosis → Variant Planning → Experiments → Research Findings`

Each stage has: label, status (Completed / Needs Review / Pending), enabled flag, and action callback.

**Protocol Completeness Card** (Refinement #1):
- Animated progress bar (red/amber/green)
- Score badge from `configuration.completeness_score` (server-computed)
- Missing field chips (purple pill per missing field name)
- Footer: `change_reason` + version lineage

**Evidence integrity panel**: hash values for file_hash, schema_hash, configuration_hash + boolean flags for fingerprint, contract, profile, semantic diff, recreation bundle.

**Gaps list**: computed by `overviewGaps()` — each gap has title, why, impact, and a CTA button.

**AI brief**: `runAi(type)` → `aiApi.explain()` — three explanation types selectable.

**Export actions**: diagnosis report (.docx), diagnosis contract (.json), recreation bundle (.json).

### 9.2 `EnhancedEvidencePanel`

**Left**: CSV upload form with progress bar, dataset name override, version notes.  
**Right**: Registered evidence table.  
**Below**: `EnhancedConfigurationPanel` — configure an uploaded registration.

**Configuration form**:
- Select registration from dropdown
- ML task, target column, train/test split ratio
- Encoding strategy (one-hot / label / none)
- Feature columns multi-select
- Submits to `datasetApi.configure(registrationId, payload)`

### 9.3 `VersionPanel`

**Left**: Version selector list (all datasets → all versions, ordered by creation).  
On version click: `onVersion(version.id)` → calls `selectVersion()` in workspace.

**When version selected — right side shows**:

1. **Version identity card**: version number, row/col counts, dataset name, parent version.
2. **Fingerprint evidence**: file_hash, schema_hash, combined_fingerprint with copy buttons (via `CopyButton`).
3. **Semantic diff card** (V2+): SCM score, DSI score, per-dimension change bars.
4. **Executive summary card**: AI narrative generation via `aiApi.versionExecutiveSummary()`.
5. **Risk action card**: MLRS severity + "Run Diagnosis" CTA.
6. **Reproducibility panel**: recreation bundle download + verification upload.
7. **Cross-version comparison**: select another version to compare on-demand.
8. **Delete version** button (with confirmation).

### 9.4 `DiagnosisPanel`

**Left**: Version selector (runs diagnosis on selected version).  
Calls `datasetApi.diagnosis(versionId)` and `datasetApi.diagnosisContract(versionId)`.

**Right — when diagnosis available**:

1. **MLRS + LRS score gauges** with severity label (Low / Medium / High / Critical).
2. **Score breakdown**: per-component contributions shown as bars.
3. **Finding cards**: each `DiagnosisReport.findings_json` entry shows code, severity, evidence values, and intervention recommendations.
4. **Diagnosis contract**: structured `intervention_options` list — each option shows step ID, human decision required flag, and evidence references.
5. **Export diagnosis report** (.docx) button.
6. **"Open Variant Generator"** CTA when contract is available — switches to Variants tab.
7. **Run Diagnosis** button when no diagnosis exists → `onVersion()` to load analysis.

**Also includes**: Diagnosis data diagnosis button (check first) → `onOpenVariants()`.

### 9.5 `VariantGeneratorPanel`

**Left — Job Configuration**:
1. **Goal selector**: 6 optimization goals as clickable cards.
2. **Constraints form**: max variants (1–8), allowed transformations checkboxes, excluded transformations, max execution cost.
3. **"Generate Variants"** button → `variantApi.createJob(versionId, payload)` → starts background job.

**Right — Pipeline Preview**: shows the planned pipeline steps from the planner before execution.

**Job status polling**: polls `variantApi.getJob(jobId)` every 2 seconds while `status=running`.

**Results table** (when job completed):
- Each `VariantGenerationRecord` shown as a card ranked by VRS
- Columns: Rank, Pipeline steps (badges), VRS score, MLRS before→after, LRS after, Goal satisfaction
- "Register as Version" button → `variantApi.registerVariant()` → promotes top variant to a new `DatasetVersion` with `generation_method="variant"`

**Previous jobs**: lists earlier jobs for the same version; click to reload.

---

## 10. Navigation & State Flow Diagram

```
/login (AuthPage)
  ↓ login success
/dashboard (DashboardPage)
  ├── "New study" → /studies
  └── Sidebar → /studies, /findings

/studies (StudiesPage)
  ├── Create form → /studies/:studyId
  └── Directory row → /studies/:studyId

/studies/:studyId (StudyWorkspace)
  ├── Overview tab    (EnhancedOverviewPanel)
  │     └── "Open Evidence" → Evidence tab
  │     └── "Open Versions" → Versions tab (+ selectVersion)
  │     └── "Open Diagnosis" → Diagnosis tab
  ├── Evidence tab    (EnhancedEvidencePanel)
  │     └── configure → selectVersion → Versions tab
  ├── Versions tab    (VersionPanel)
  │     └── version click → selectVersion (stays on Versions)
  │     └── "Open Diagnosis" → Diagnosis tab
  ├── Diagnosis tab   (DiagnosisPanel)
  │     └── "Open Variant Generator" → Variants tab
  └── Variants tab    (VariantGeneratorPanel)
        └── "Register as Version" → new DatasetVersion created

/findings (ResearchFindingsPage)
  └── "Open workspace" → /studies/:studyId
```

---

## 11. API Client Methods (`api/client.js`)

```javascript
authApi.login(payload)             // POST /auth/login
authApi.register(payload)          // POST /auth/register

dashboardApi.get()                 // GET /dashboard

studyApi.list(search, mlTask)       // GET /studies
studyApi.get(id)                   // GET /studies/{id}
studyApi.create(payload)           // POST /studies
studyApi.update(id, payload)       // PATCH /studies/{id}
studyApi.currentConfiguration(id)  // GET /studies/{id}/configuration
studyApi.configurationHistory(id)  // GET /studies/{id}/configurations
studyApi.createConfiguration(id, payload) // POST /studies/{id}/configurations
studyApi.configurationByVersion(id, n)    // GET /studies/{id}/configurations/{n}
studyApi.configurationDiff(id, from, to)  // GET /studies/{id}/configurations/diff
studyApi.executiveReport(id, includeAi)  // GET /studies/{id}/executive-report (blob)
studyApi.findings(id)              // GET /studies/{id}/findings
studyApi.allFindings()             // GET /research-findings

datasetApi.list(studyId)           // GET /studies/{id}/datasets
datasetApi.register(studyId, data, progress) // POST (multipart)
datasetApi.configure(regId, payload) // POST /registrations/{id}/configure
datasetApi.registrationReport(regId)  // GET explanation-report
datasetApi.version(versionId)       // GET /versions/{id}
datasetApi.analysis(versionId)      // GET /versions/{id}/analysis
datasetApi.deleteVersion(versionId) // DELETE /versions/{id}
datasetApi.diff(versionId)          // GET semantic-diff
datasetApi.compare(vId, againstId)  // GET compare
datasetApi.recreationBundle(vId)    // GET recreation-bundle
datasetApi.verifyRecreation(data)   // POST recreate/verify
datasetApi.profile(vId)            // GET profile
datasetApi.diagnosis(vId)          // GET diagnosis
datasetApi.diagnosisContract(vId)  // GET diagnosis-contract
datasetApi.diagnosisReport(vId)    // GET diagnosis-report (blob)

aiApi.explain(studyId, payload)
aiApi.semanticMetrics(studyId, diffId)
aiApi.semanticDiffInterpretation(studyId, diffId)
aiApi.versionExecutiveSummary(studyId, versionId)
aiApi.diagnosisInterpretation(studyId, versionId)

variantApi.createJob(versionId, payload)
variantApi.listJobs(versionId)
variantApi.getJob(jobId)
variantApi.registerVariant(jobId, recordId, payload)
variantApi.variantTree(versionId)
```

---

## 12. Key CSS Classes Reference

| Class | Description |
|---|---|
| `.card` | Surface card (border + radius + padding) |
| `.button` | Primary button; `.secondary`, `.ghost`, `.compact` variants |
| `.badge` | Inline pill; `.success`, `.warning`, `.high`, `.medium`, `.low`, `.info` |
| `.notice` | Alert block; `.error`, `.warning`, `.success` |
| `.field` | Form field wrapper; `.full` = span full width |
| `.page-header` | Page heading row with eyebrow + h1 + description + action |
| `.empty` | Centered empty state with icon slot |
| `.metric-card` | KPI card with metric-top, metric-value |
| `.table-wrap` | Scrollable table container |
| `.skeleton` | Animated shimmer placeholder |
| `.app-shell` | Root grid: sidebar + main column |
| `.sidebar` | Left navigation sidebar; `.sidebar-collapsed` narrows it |
| `.topbar` | Fixed header with context + actions |
| `.workspace-shell` | Workspace header + tab bar container |
| `.workspace-tabs` | Horizontal tab navigation |
| `.workspace-body` | Active panel content area (animated on tab change) |
| `.studies-layout` | Two-column layout for Studies page |
| `.protocol-form` | Study creation form |
| `.protocol-section` | Numbered section wrapper |
| `.protocol-preview-card` | Live readiness preview card |
| `.auth-page` | Split two-panel auth layout |
| `.auth-visual` | Left gradient visual panel |
| `.auth-card` | Right form card |
| `.finding-summary-grid` | Grid of dataset finding summary tiles |
| `.variant-ops-grid` | 2-col grid of operation selector cards |
| `.context-row` | Generic list row with icon + content |
| `.completeness-bar` | Animated readiness bar in overview |
