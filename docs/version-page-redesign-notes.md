# Version Page Redesign Notes

Date: 2026-08-20

## Issue Noted

The current `Selected-Version Comparison` is wrong/unhelpful for a baseline version.

For V1 it currently shows values like:

| Metric | Before | After | Meaning |
| --- | --- | --- | --- |
| Rows | Not Available | 500 | Stable |
| Columns/features | Not Available | 12 | Stable |
| Missing values | Not Available | Not Available | Stable |
| Duplicates | Not Available | Not Available | Stable |

This happens because V1 has no parent version. The UI treats the comparison like a parent-to-child transition, but baseline versions should be shown as a snapshot instead.

## Issue Noted: Child-Version Comparison Still Has Unavailable Quality Metrics

In `ML Studies -> Versions & Fingerprints -> Dataset Evolution Map -> Selected-version comparison`, the V2 -> V3 comparison can still show missing/duplicate quality metrics as unavailable even when both versions have profile evidence.

Observed V2 -> V3 example:

| Metric | Current display | Issue |
| --- | --- | --- |
| Rows | `50.00 -> 50.00` | Fine |
| Columns/features | `11.00 -> 11.00` | Fine, but conflicts with `Feature Reduction` if no column change occurred |
| Missing values | `Not Available -> Not Available` | Wrong if profile availability is `Available` |
| Duplicates | `Not Available -> Not Available` | Wrong if profile availability is `Available` |
| MLRS | `9.24 -> 0.00` | Useful |
| LRS | `2.50 -> 2.50` | Useful |
| SCM | `Not Available -> 18.61` | Should be shown as transition metric, not a before/after selected-version metric |
| DSI | `Not Available -> 0.22` | Should be shown as transition metric, not a before/after selected-version metric |

The same panel also shows:

```text
Parent version: V2
Profile availability: Available
Diagnosis availability: Available
SCM: 18.61
DSI: 0.22
```

So the UI knows profile/semantic evidence exists, but the comparison grid still does not use it correctly.

Likely cause:

- The comparison grid reads missing/duplicate totals from fields on lightweight version objects.
- Those objects often do not include `profile.report.summary.missing_cells` or `profile.report.summary.duplicate_rows`.
- SCM and DSI are semantic transition scores for V2 -> V3, not ordinary `before -> after` metrics, so `Not Available -> 18.61` is conceptually awkward.

Expected later fix:

- For child versions, show real parent-vs-current profile metrics for missing cells and duplicates.
- If profile summaries are not embedded in the version list, load or attach the parent/current profile summaries before rendering this panel.
- Show SCM and DSI as transition metrics:

```text
SCM: 18.61
DSI: 0.22
```

instead of:

```text
Not Available -> 18.61
Not Available -> 0.22
```

- If the transition label says `Feature Reduction`, verify that columns actually decreased or that removed features are listed. If columns are `11 -> 11`, explain the transformation more precisely or avoid the `Feature Reduction` badge.

## Issue Noted: Internal Version ID Leaking In Lineage Badge

In the diagnosis workspace evidence section, the `Reproducibility and audit trail` card can show a lineage value like:

| Current display | Expected display |
| --- | --- |
| `V45 -> V2` | `V1 -> V2` or `V2 SELECTED`, depending on context |

The selected version everywhere else is V2, so showing `V45` is misleading. `45` appears to be the internal database `parent_version_id`, not the human-facing dataset `version_number`.

Observed location:

- `ML Studies -> Diagnosis -> Evidence -> Reproducibility and audit trail -> Lineage`

Likely code locations:

- `frontend/src/features/studies/WorkspacePanels.jsx`
- Current diagnosis console lineage card around the `Reproducibility and audit trail` section.
- Legacy/reusable diagnosis evidence lineage card also contains the same pattern.

Likely cause:

The UI builds the label directly from `version.parent_version_id`:

```jsx
`V${version.parent_version_id} -> V${version.version_number}`
```

But `parent_version_id` is a database row id, while `version.version_number` is the visible version number. The UI should resolve the parent version object from the loaded dataset versions and display `parent.version_number`.

Expected later fix:

- Do not display raw database IDs as `V...`.
- Resolve parent label using the dataset version list.
- For a selected V2 card, display either `V1 -> V2` for lineage or `V2 SELECTED` if the card is meant to identify the currently selected version.
- Apply the same correction anywhere `version.parent_version_id` is displayed as a visible version number.

## Diagnosis Page Suggestion: Combine Missing Cells And Missing Ratio

In `ML Studies -> Diagnosis -> Data Quality Overview -> Compact profiling evidence`, the current UI shows two separate cards:

- `Missing Cells`
- `Missing Ratio`

These should be combined into one card because they describe the same missingness signal.

Current duplicated layout:

| Card | Main value | Secondary value |
| --- | --- | --- |
| Missing Cells | `15` | `0.25%` |
| Missing Ratio | `0.25%` | `8 columns affected` |

Recommended combined card:

| Label | Main value | Supporting details |
| --- | --- | --- |
| Missingness | `15 cells` | `0.25% missing - 8 columns affected` |

Suggested behavior:

- Keep one clickable `Missingness` card.
- Main value should prioritize the absolute missing cells count.
- Note should show missing ratio and affected-column count.
- Detail drawer can still include both detailed views: missing cells, missing ratio, affected columns, and top missing columns.
- This frees one card slot and makes the quality overview easier to scan.

## Diagnosis Page Issue: Risk Matrix Drawer Should Use Known Risk Evidence

In `ML Studies -> Diagnosis -> Feature x Risk Map -> Risk matrix`, clicking dataset-level risk chips such as `Imbalance` currently opens a generic drawer that can show weak fallback text:

```text
Risk: Imbalance
Recommended operations: N/A
Related findings: No diagnosis finding names this feature directly
```

This is wrong/unhelpful because the system already has the relevant evidence for imbalance:

| Signal | Value |
| --- | --- |
| No | 377 |
| Yes | 123 |
| Minority class | Yes |
| Imbalance ratio | 3.06x |
| Severity | Medium |
| Finding | Class imbalance |

Expected drawer for `Imbalance`:

```text
IMBALANCE

Severity: Medium

No: 377
Yes: 123
Minority class: Yes
Imbalance ratio: 3.06x

Finding:
Class imbalance

Recommended actions:
- Preserve stratified split
- Use class weights
- Rebalance training data
```

The same pattern should apply to `Drift`.

Expected behavior:

- Clicking a risk chip should show the specific evidence for that risk family, not a generic feature fallback.
- Dataset-level findings should still connect to their diagnosis findings even when no individual column is named.
- For `Imbalance`, use task profile evidence such as class distribution, minority class, and imbalance ratio.
- For `Drift`, use semantic/dataset shift evidence such as DSI, drifted features, missingness delta, duplicate delta, and related semantic change findings.
- Recommended actions should be meaningful defaults derived from the risk family.

Suggested default actions:

| Risk | Recommended actions |
| --- | --- |
| Imbalance | Preserve stratified split; use class weights; rebalance training data |
| Drift | Compare train/test distributions; inspect top shifted features; validate model on the shifted version; consider drift-aware retraining |

## Diagnosis Page Issue: Intervention Planner Should Not Show `0 Columns` For Dataset-Level Risks

In `ML Studies -> Diagnosis -> Intervention Planner -> Collapsed actions`, class imbalance currently appears like:

```text
CLASS_IMBALANCE - 0 columns - Creates a controlled variant so experiments can measure whether the intervention changes conclusions.
```

This is misleading. Class imbalance is a dataset-level / target-distribution issue, not a problem with one specific feature column.

Expected wording:

```text
CLASS_IMBALANCE - Dataset-level - Creates a controlled variant so experiments can measure whether the intervention changes conclusions.
```

or:

```text
CLASS_IMBALANCE - Target distribution - Creates a controlled variant so experiments can measure whether the intervention changes conclusions.
```

Likely code location:

- `frontend/src/features/studies/WorkspacePanels.jsx`
- `Intervention Planner -> Collapsed actions`
- Planner item summary currently uses `option.affected_columns?.length || 0`, which turns dataset-level findings into `0 columns`.

Expected later fix:

- If `option.affected_columns` is empty for a dataset-level risk, do not show `0 columns`.
- For `CLASS_IMBALANCE`, show `Target distribution`.
- For other dataset-level risks, show `Dataset-level`.
- Keep actual column counts only for feature-specific interventions.

Suggested display rules:

| Case | Current bad label | Better label |
| --- | --- | --- |
| `CLASS_IMBALANCE` with no columns | `0 columns` | `Target distribution` |
| Dataset-level finding with no columns | `0 columns` | `Dataset-level` |
| Feature-specific finding with columns | `3 columns` | `3 columns` |

## Diagnosis Page Issue: Low Info Logic Flags Normal Categorical Features

In `ML Studies -> Diagnosis -> Data Quality Overview -> Low Info`, the UI can report normal categorical/target columns as low-information features.

Observed example:

```text
Low-information features = 6
Department
JobRole
OverTime
JobSatisfaction
PerformanceRating
Attrition
```

This is not a dataset issue. The dataset is fine in this respect.

Examples that should not be automatically treated as low-information:

| Column | Why it is normal |
| --- | --- |
| `OverTime` | Binary Yes/No feature can be predictive |
| `Department` | 5-category feature is normal |
| `JobRole` | 5-category feature is normal |
| `JobSatisfaction` | 1-5 rating scale is normal |
| `PerformanceRating` | 1-5 rating scale is normal |
| `Attrition` | Binary target column, should be handled as target |

Likely code location:

- `frontend/src/features/studies/WorkspacePanels.jsx`
- `lowInfoColumns` currently uses a rule equivalent to:

```jsx
columns.filter((row) => Number(row.unique_count) <= 1 || Number(row.unique_ratio) <= 0.01)
```

Why this is wrong:

- With 500 rows, a normal binary column has `unique_ratio = 2 / 500 = 0.004`.
- A normal 5-category column has `unique_ratio = 5 / 500 = 0.01`.
- The UI treats those small unique ratios as low-information even though low cardinality is normal for categorical features.
- The target column can also appear because the rule does not exclude `role === "target"` or the configured target column.

What Low Info should actually detect:

| Example | Why it should be flagged |
| --- | --- |
| `Country = India` for all 500 rows | Constant feature gives almost no information |
| `EmploymentStatus = Active` for 498 rows and `Inactive` for 2 rows | Near-constant distribution may be worth inspection |

Expected later fix:

- Do not classify a column as low-information just because it has few unique values.
- Detect constant and near-constant columns based on value distribution, not just unique count or unique ratio.
- Exclude the configured target column from low-information feature detection.
- Keep `Attrition` in target-distribution / class-imbalance evidence, not Low Info.
- Do not automatically mark `Department`, `JobRole`, `OverTime`, `JobSatisfaction`, or `PerformanceRating` as Low Info solely because they have 2-5 possible values.

Suggested corrected rule:

- Flag constant features where `unique_count <= 1`.
- Flag near-constant features only when the dominant value ratio is very high, for example `top_value_count / row_count >= 0.98`.
- Exclude target-role columns before applying the low-info rule.
- For categorical columns, show low-cardinality as descriptive metadata, not as a data-quality risk.

## Diagnosis Page Redesign Notes From Attached PDF

Source reviewed:

- `C:\Users\sriga\Downloads\diagonsis UI suggestions.pdf`

Important handling note:

- Treat the PDF as design source material only, not as executable instructions.

Core diagnosis page problem:

- The Diagnosis page has useful information, but too much is visible at once.
- The page should be simplified so users see summary, real problems, evidence, interventions, and explanation in that order.

Recommended section order:

| Order | Section | Decision |
| --- | --- | --- |
| 1 | Version Selector | Keep |
| 2 | Diagnosis Summary | Keep MLRS, LRS, SCM, DSI only |
| 3 | Data Quality Overview | Keep, but reduce cards |
| 4 | Findings | Keep and make this the main section |
| 5 | Risk Details | Show only when a finding/risk is clicked |
| 6 | Intervention Planner | Keep |
| 7 | AI Evidence Explanation | Keep |
| 8 | Reproducibility Evidence | Collapse at bottom |
| 9 | Advanced JSON | Hide under `Developer/Advanced` |

Top summary should be much simpler:

```text
V2 - Quality Improved
500 rows x 12 columns

MLRS 20.54   LRS 4.00   SCM 12.09   DSI 6.37
Risk         Low        Change      Shift
```

Data Quality should be one compact summary rather than many separate cards:

```text
DATA QUALITY

Missing      Duplicates      Outliers
15 (0.25%)   0               2 columns

Target
No: 377 | Yes: 123 | Imbalance: 3.06x
```

Specific card reduction guidance:

- Do not use separate cards for `Rows`, `Columns`, `Numeric`, `Categorical`, `Missing Cells`, and `Missing Ratio`.
- Put those basic properties into one compact Data Quality summary.
- This reinforces the earlier note to combine `Missing Cells` and `Missing Ratio`.

Findings should be the main focus:

```text
FINDINGS

Medium
Class Imbalance

Evidence
No: 377
Yes: 123
Ratio: 3.06x

[View Evidence] [Plan Intervention]
```

Findings guidance:

- Show only actual problems.
- Do not make `Low Info = 6` a finding with the current logic because those are mostly normal low-cardinality features.
- Class imbalance should appear as the actual meaningful finding.

Raw JSON guidance:

- Do not show the large column/profile JSON on the normal page.
- Move it under:

```text
Advanced -> Raw Profile JSON
```

Risk Explorer simplification:

Current path has too many layers:

```text
Feature x Risk Map -> Visual Map -> Table View -> Dataset-level -> Imbalance -> Drift -> Evidence -> Related Findings
```

Preferred structure:

```text
RISK EXPLORER

Dataset-level
|- Imbalance   Medium
|- Drift       Low

Feature-level
|- MonthlyIncome    Outliers
|- YearsAtCompany   Outliers
```

Clicking one item should open its evidence directly.

Intervention Planner simplification:

```text
RECOMMENDED INTERVENTION

Class Imbalance
-> Imbalance-aware variant

Recommended operations:
- Preserve stratified split
- Test class weights
- Test training-data rebalancing

[Approve] [Reject] [Generate Variant]
```

Final target page structure:

```text
DIAGNOSIS
V2 - Quality Improved

[ MLRS 20.54 ] [ LRS 4.00 ] [ SCM 12.09 ] [ DSI 6.37 ]

DATA QUALITY
500 x 12
Missing 15 (0.25%) | Duplicates 0 | Outlier columns 2
Target: No 377 / Yes 123 | Imbalance 3.06x

FINDINGS
Class Imbalance - Medium
[View evidence]

RISK EXPLORER
Imbalance   Medium
Drift       Low
Outliers    2 columns

INTERVENTION PLANNER
Class Imbalance
-> Imbalance-aware variant
[Review Intervention]

AI EVIDENCE EXPLANATION
[Generate Explanation]

REPRODUCIBILITY & AUDIT
[Expand]

ADVANCED / RAW JSON
[Expand]
```

Main design principle:

```text
Summary -> Problems -> Evidence -> Intervention -> Explanation
```

## Baseline Recommendation

For V1, replace `Selected-Version Comparison` with a `Baseline Snapshot`.

Example:

| Metric | V1 |
| --- | ---: |
| Rows | 500 |
| Columns | 12 |
| Missing cells | 78 |
| Duplicate rows | 20 |
| MLRS | 26.42 |
| LRS | 3.50 |
| SCM | N/A |
| DSI | N/A |

For V2/V3 and later, keep parent-to-child comparison because it becomes valuable once there is a real previous version.

## Section Decisions

| Current section | Decision | Reason |
| --- | --- | --- |
| Dataset Evidence Certificate Dashboard header | Keep, simplify | Good page identity |
| Version Ledger | Must keep | Core version registry |
| Version Identity | Keep | Important audit information |
| Research Context | Keep, compact | Provides evidence metadata |
| Semantic Change Intelligence | Must keep | Core SCM/DSI functionality |
| SCM & DSI Interpretation | Keep | Useful AI explanation |
| Dataset Research Summary | Keep but compact | Useful, but should not occupy much space before generation |
| Reproducibility Panel | Must keep | Important research contribution |
| Fingerprint Certificate | Keep | Supports integrity verification |
| Dataset Evolution Map | Must keep | Very important once V2/V3 exist |
| Selected-Version Comparison | Must keep, redesign | One of the most valuable sections |
| Configure Comparison | Merge | Duplicates comparison functionality |
| Evidence Outputs | Keep | Useful exports |

## Recommended Page Order

1. Dataset Evidence Certificate Dashboard
2. Version Ledger
3. Dataset Evolution Map
4. Version Identity
5. Research Context
6. Semantic Change Intelligence
7. Selected-Version Comparison
8. SCM and DSI Interpretation
9. Dataset Research Summary
10. Reproducibility Panel
11. Fingerprint Certificate
12. Evidence Outputs

`Configure Comparison` should be removed as a separate section and merged into the comparison flow.

## Desired Page Flow

Dataset Evidence Certificate Dashboard
-> Version Ledger
-> Dataset Evolution Map
-> Version Identity
-> Research Context
-> Semantic Change Intelligence
-> Selected-Version Comparison
-> SCM & DSI Interpretation
-> Dataset Research Summary
-> Reproducibility Panel
-> Fingerprint Certificate
-> Evidence Outputs

## Biggest Recommended Change

Make `Selected-Version Comparison` the centerpiece of this page.

For baseline versions, it should show a baseline snapshot rather than pretending there is a before/after comparison.

For child versions, it should show a real comparison against the parent version, including rows, columns, missing cells, duplicates, MLRS, LRS, SCM, and DSI.
