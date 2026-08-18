# FedRepro UI Reference

**Last updated:** 2026-08-16
**Stack:** React 18, React Router, Axios, Recharts, lucide-react, Webpack
**Design:** token-based CSS with full light/dark support

This document describes the current UI implementation. For user workflow instructions, see `docs/UI_PAGE_GUIDE.md`.

## Design System

All global styles live in `frontend/src/styles.css`.

Important token families:

- colors: `--color-primary`, `--color-success`, `--color-warning`, `--color-danger`, `--color-surface`, `--color-text`, `--color-border`
- spacing: `--sp-1` through `--sp-8`
- radius: `--radius-sm`, `--radius-md`, `--radius-lg`, `--radius-full`
- shadows: `--shadow-1` through `--shadow-4`
- motion: `--duration-fast`, `--duration-enter`, `--ease-out`
- layout: `--topbar-height`, modal and overlay z-index tokens

The theme is stored in `localStorage.fedrepro-theme` and applied to `<html data-theme="dark">`. `index.jsx` initializes the theme before React renders.

## Shared Components

`frontend/src/components/UI.jsx` provides:

| Component | Purpose |
|---|---|
| `Card` | bordered surface for repeated items and tools |
| `Button` | primary, secondary, ghost, compact, loading states |
| `Field` | form label, control, hint wrapper |
| `Badge` | semantic status/severity chip |
| `Notice` | error, warning, success, neutral alert |
| `PageHeader` | page-level title area |
| `Empty` | empty state |
| `MetricCard` | dashboard KPI card |
| `DataTable` | sortable table |
| `Skeleton`, `SkeletonCard` | loading placeholders |
| `CopyButton` | clipboard copy affordance |
| `ThemeToggle` | persisted light/dark toggle |
| `StatusDot` | small status indicator |

## App Shell

`frontend/src/layouts/AppLayout.jsx`

Authenticated routes render inside the app shell:

- left sidebar navigation
- collapsible sidebar state
- mobile drawer behavior
- topbar title/subtitle
- theme toggle
- authenticated researcher chip
- sign-out action

Primary routes:

| URL | Page |
|---|---|
| `/login` | Auth page |
| `/dashboard` | Dashboard |
| `/studies` | Study directory and creation |
| `/studies/:studyId` | Study workspace |
| `/findings` | Cross-study research findings |

## Study Workspace

`frontend/src/pages/StudyWorkspace.jsx` owns the active study state.

It loads:

- study detail
- dataset list
- current study configuration
- selected version analysis
- profile evidence
- diagnosis evidence
- diagnosis contract
- semantic timeline

Workspace tabs:

1. Overview
2. Dataset Evidence
3. Versions & Fingerprints
4. Diagnosis
5. Variant Generator

`selectVersion(idOrVersion, nextActive)` fetches `/api/versions/{id}/analysis`, stores selected version/profile/diagnosis/timeline, attempts the diagnosis contract when diagnosis exists, and optionally switches tabs.

## Diagnosis Dashboard

`DiagnosisPanel` in `frontend/src/features/studies/WorkspacePanels.jsx` is the active diagnosis workspace. Older diagnosis implementations are quarantined below it and should not be reactivated.

Required flow rendered in the panel:

```text
Dataset Quality -> Diagnosis Metrics -> Risk Explorer -> Risk Map -> Interventions -> Human Decisions -> Variant Plan -> Evidence -> AI Explanation
```

### Version Selection

The diagnosis page shows every dataset version available in the study, including:

- manual uploaded baseline versions
- normal revisions
- variant-generated versions

Each selector row exposes:

- version number
- generation method
- diagnosis status
- MLRS when available
- LRS when available

Statuses are derived from backend `diagnosis_status` plus local request state:

- `Not Diagnosed`
- `Diagnosed`
- `Recompute Available`
- `Running`
- `Failed`

### Run/Recompute Controls

The page uses `datasetApi.runDiagnosis(versionId, recompute)`.

Button labels:

- `Run Diagnosis` when diagnosis/profile evidence is missing
- `Recompute Diagnosis` when backend status is `Recompute Available`

The UI does not silently recompute existing evidence. It waits for an explicit user action, except backend startup warmup may fill missing/stale evidence in the background.

### Compact Cards

The default view intentionally stays compact. It renders:

- rows
- columns
- missing cells
- missing ratio
- duplicate rows
- numeric feature count
- categorical feature count
- outlier evidence
- high-correlation evidence
- low-information feature evidence
- target distribution or imbalance evidence
- MLRS
- LRS
- SCM
- DSI
- VRS for variant-origin versions
- finding count
- intervention count
- severity distribution
- fingerprint status
- lineage status
- reproducibility status

Unavailable metrics render as `N/A` or `Not computed`. Baseline SCM/DSI is unavailable because a baseline has no parent.

### Smart Figures

The page uses analytical visual components rather than long text blocks:

- radial/linear risk gauges
- mini bars for missingness, duplicates, outliers, correlations
- class distribution bars
- severity distribution bars
- feature by risk matrix
- lineage/status indicators
- compact component strips for MLRS/LRS/SCM/DSI/VRS

### Detail Workspace

All clickable cards call `openDetail(type, payload)` and render `DetailDrawer`.

The current detail view is not a centered modal. It is a fixed right-side detail workspace on desktop and a bottom sheet on mobile. This prevents the user from hunting for an expanded card at the bottom of the page.

Detail workspace sections:

- Summary
- Evidence
- Advanced, only when raw evidence exists

The advanced/debug JSON stays hidden in a disclosure.

Clickable detail sources include:

- MLRS
- LRS
- SCM
- DSI
- VRS
- missingness
- duplicates
- outliers
- correlations
- low-information features
- target distribution
- individual findings
- risk map cells
- intervention cards
- operation chips
- human-decision rows
- fingerprint
- lineage
- reproducibility
- variant plan rows
- AI explanation summary

## Variant Generator UI

`VariantGeneratorPanel` uses the selected diagnosed version and diagnosis evidence.

Main controls:

- optimization goal cards
- maximum pipelines/variants
- transformation constraints
- allowed/excluded transformation inputs
- generate button
- job status polling
- ranked variant result cards
- VRS and component evidence
- register/promote variant action
- previous job history

When a variant is registered, it becomes a normal immutable dataset version and appears in version selectors and diagnosis flows.

## API Client

`frontend/src/api/client.js` exposes:

- `authApi`
- `dashboardApi`
- `studyApi`
- `datasetApi`
- `aiApi`
- `variantApi`

Important diagnosis methods:

```javascript
datasetApi.analysis(versionId)
datasetApi.diagnosis(versionId)
datasetApi.runDiagnosis(versionId, recompute)
datasetApi.diagnosisContract(versionId)
datasetApi.diagnosisReport(versionId)
aiApi.versionExecutiveSummary(studyId, versionId)
aiApi.versionExecutiveSummaryStream(studyId, versionId, onChunk)
aiApi.diagnosisInterpretation(studyId, versionId)
```

## Responsive Behavior

- Desktop diagnosis detail view: fixed right-side workspace.
- Mobile diagnosis detail view: bottom sheet.
- Workspace tabs collapse to horizontal scroll where needed.
- Card grids move to single-column layouts on narrow screens.
- Text-heavy JSON is hidden under disclosures.
- Buttons and cards use stable dimensions to avoid layout shift.

## Styling Guidance For Future Edits

- Use semantic colors only for severity, risk, success, and warnings.
- Keep diagnosis cards compact and clickable.
- Keep raw JSON hidden.
- Use lucide icons for actions.
- Do not create nested cards.
- Do not add decorative gradients or non-analytical charts.
- Preserve light/dark tokens.
- Keep the detail workspace discoverable: a click should visibly open the side/bottom panel every time.
