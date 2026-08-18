# FedRepro UI Page Guide

**Last updated:** 2026-08-16

This guide explains how to use each page in the current FedRepro UI.

## 1. Login

Open `/login`.

Use this page to:

- register a researcher account
- log in with email and password
- enter the protected workspace

After authentication, FedRepro stores the access token locally and redirects to the Dashboard.

## 2. Dashboard

Open `/dashboard`.

Use this page for a quick system overview:

- total studies
- registered datasets
- dataset versions
- high-risk studies
- recent diagnosis risk chart
- recent activity

Click a study or navigation item to continue into the study workflow.

## 3. Studies

Open `/studies`.

Use the left panel to create a study protocol. Fill the study identity, research intent, target/evaluation setup, and reproducibility controls.

The protocol completeness preview helps you see what is missing before you create the study. The server stores the final completeness score and missing-field list.

Use the study directory to:

- search studies
- filter by ML task
- open an existing workspace

## 4. Study Workspace

Open `/studies/{studyId}`.

This is the main work area. Use the tabs from left to right:

```text
Overview -> Dataset Evidence -> Versions & Fingerprints -> Diagnosis -> Variant Generator
```

## 5. Overview Tab

Use Overview to understand the study state:

- research protocol
- protocol completeness
- workflow readiness
- evidence gaps
- recent activity
- exports

When a gap appears, use the action button on that row to jump to the page that fixes it.

## 6. Dataset Evidence Tab

Use Dataset Evidence to upload and configure CSV data.

Workflow:

1. Upload a CSV.
2. Add a dataset name and version notes.
3. Register the dataset.
4. Select the registration.
5. Configure target column, primary metric, validation strategy, selected features, and scaling.
6. Submit configuration.

After configuration, FedRepro creates an immutable dataset version and runs fingerprint, semantic diff when applicable, profile, and diagnosis.

## 7. Versions & Fingerprints Tab

Use this page to audit version identity and reproducibility.

You can inspect:

- version number
- row/column counts
- parent version
- generation method
- file hash
- schema hash
- metadata hash
- combined fingerprint
- configuration hash
- semantic diff
- recreation bundle
- CSV verification against a recreation bundle
- cross-version comparison

Use this page when you need to prove exactly which dataset version was used.

## 8. Diagnosis Tab

Use Diagnosis for the full research dashboard.

The page flow is:

```text
Dataset Quality -> Diagnosis Metrics -> Risk Explorer -> Risk Map -> Interventions -> Human Decisions -> Variant Plan -> Evidence -> AI Explanation
```

### Selecting A Version

Pick any version from the selector. The list includes baseline uploads, normal revisions, and variant-generated versions.

The compact status line tells you:

- version number
- generation method
- diagnosis status
- MLRS when available
- LRS when available

### Running Diagnosis

If evidence is missing, click `Run Diagnosis`.

If evidence is stale, click `Recompute Diagnosis`.

FedRepro then runs the deterministic `ProfilingService -> DiagnosisService` workflow and saves the result for that immutable version.

### Reading Metrics

The compact dashboard exposes:

- MLRS: training readiness risk
- LRS: leakage risk
- SCM: semantic change magnitude from parent version
- DSI: distribution shift from parent version
- VRS: variant readiness score when the version came from a generated variant
- finding count
- intervention count
- severity distribution
- fingerprint/reproducibility status

`N/A` means the metric is legitimately unavailable. For example, baseline versions do not have SCM/DSI because there is no previous version.

### Opening Details

Click any card, metric, risk, risk-map cell, intervention, operation, evidence item, or variant-plan row. A fixed detail workspace opens on the right side of desktop screens and as a bottom sheet on mobile.

Use the detail workspace to inspect:

- summary
- evidence rows
- mini bars/charts
- related findings
- recommendations
- raw JSON under Advanced

The raw JSON is intentionally hidden until you expand Advanced.

### Planning Interventions

Intervention cards are generated from the diagnosis contract. Select interventions to build a variant plan. Review:

- selected interventions
- generated operations
- affected columns
- human decisions
- recommended metrics
- constraints

When ready, open the Variant Generator.

## 9. Variant Generator Tab

Use this page after a version is diagnosed.

Workflow:

1. Select an optimization goal.
2. Set constraints.
3. Generate variants.
4. Wait for job completion.
5. Review ranked pipelines.
6. Compare VRS, MLRS before/after, LRS, affected rows/features, and explanations.
7. Register the best variant as a new dataset version.

After registration, the variant appears in the version and diagnosis lists. It supports the same diagnosis, fingerprint, report, AI, and recompute workflow as every other version.

## 10. Research Findings

Open `/findings`.

Use this page for a cross-study overview of diagnosis evidence:

- study-level risk summaries
- dataset counts
- version counts
- average and peak risk
- quick links back to workspaces

## 11. Reports And Exports

Available exports include:

- diagnosis DOCX report
- study executive DOCX report
- diagnosis contract JSON
- recreation bundle JSON
- generated dataset explanation report

Reports use persisted deterministic evidence. AI report text is included only when AI generation is enabled and available.

## 12. First-Run Behavior

When the backend starts, it can scan all existing dataset versions and fill missing evidence in the background. This makes later UI rendering faster.

The startup warmup handles missing or stale:

- profile evidence
- diagnosis evidence
- SCM/DSI semantic evidence
- deterministic version reports
- AI interpretations and summaries when enabled

Disable it with:

```env
EVIDENCE_WARMUP_ON_STARTUP=false
```
