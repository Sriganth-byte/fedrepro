from __future__ import annotations

from collections import Counter, defaultdict
from typing import Any


class DiagnosisContractService:
    family_labels = {
        "MISSINGNESS": "missingness",
        "DUPLICATES": "duplicates",
        "OUTLIERS": "outliers",
        "CORRELATION": "feature redundancy",
        "CLASS_IMBALANCE": "class imbalance",
        "TARGET_SKEW": "target quality",
        "SCALING": "scaling sensitivity",
        "DRIFT": "distribution shift",
        "TARGET_LEAKAGE": "leakage risk",
    }

    def build(self, study, version, profile_report, diagnosis_report) -> dict[str, Any]:
        profile = profile_report.report_json if profile_report else {}
        diagnosis = {
            "id": diagnosis_report.id,
            "version_id": diagnosis_report.version_id,
            "findings": diagnosis_report.findings_json or [],
            "mlrs_score": diagnosis_report.mlrs_score,
            "lrs_score": diagnosis_report.lrs_score,
            "ruleset_version": diagnosis_report.ruleset_version,
            "created_at": diagnosis_report.created_at,
        }
        findings = diagnosis["findings"]
        risk_families = self._risk_families(findings)
        interventions = [item for finding in findings for item in self._interventions_for(finding, study, version)]
        decisions = [decision for option in interventions for decision in option["required_decisions"]]
        return {
            "header": self._header(study, version, profile_report, diagnosis_report),
            "readiness": self._readiness(diagnosis, risk_families, interventions, decisions),
            "risk_families": risk_families,
            "intervention_options": interventions,
            "human_decisions": decisions,
            "selected_variant_plan": self._selected_plan(version, interventions, decisions),
            "experiment_handoff": self._experiment_handoff(study, version, diagnosis, interventions),
            "findings": findings,
            "column_impact": self._column_impact(profile, findings),
        }

    def _header(self, study, version, profile_report, diagnosis_report) -> dict[str, Any]:
        fingerprint = version.fingerprint
        return {
            "study_name": study.name,
            "ml_task": study.ml_task,
            "dataset_name": version.dataset.name if version.dataset else None,
            "version_id": version.id,
            "version_number": version.version_number,
            "diagnosis_report_id": diagnosis_report.id,
            "profile_report_id": profile_report.id if profile_report else None,
            "dataset_fingerprint": fingerprint.combined_fingerprint if fingerprint else None,
            "fingerprint_ruleset": fingerprint.algorithm_version if fingerprint else None,
            "diagnosis_ruleset": diagnosis_report.ruleset_version,
            "created_at": diagnosis_report.created_at,
        }

    def _risk_families(self, findings: list[dict]) -> list[dict]:
        grouped: dict[str, list[dict]] = defaultdict(list)
        for finding in findings:
            grouped[self.family_labels.get(finding.get("code"), finding.get("code", "diagnosis").lower())].append(finding)
        families = []
        for family, rows in grouped.items():
            severity_counts = Counter(row.get("severity", "low") for row in rows)
            columns = sorted({column for row in rows for column in self._columns(row)})
            families.append({
                "family": family,
                "finding_count": len(rows),
                "affected_columns": columns,
                "severity": self._dominant_severity(severity_counts),
                "intervention_available": True,
            })
        return families

    def _interventions_for(self, finding: dict, study, version) -> list[dict]:
        code = finding.get("code")
        columns = self._columns(finding)
        base = {
            "id": f"{str(code or 'finding').lower()}_v{version.id}",
            "triggered_by": [finding.get("code")],
            "source_findings": [finding.get("issue")],
            "affected_columns": columns,
            "severity": finding.get("severity"),
            "status": "recommended" if finding.get("severity") in {"high", "critical"} else "optional",
            "recommended_comparison": f"Compare generated variant against V{version.version_number} with the same validation strategy.",
        }
        if code == "MISSINGNESS":
            return [{**base, "title": "Missingness strategy variant", "objective": "Create variants that test whether missing values are changing model conclusions.", "operations": [
                self._op("add_missingness_indicators", columns, "Preserve missingness as a learnable signal when affected columns are used."),
                self._op("impute_numeric_median", columns, "Fill numeric missing cells with a deterministic median policy."),
                self._op("impute_categorical_mode", columns, "Fill categorical missing cells with a deterministic mode policy."),
            ], "expected_changes": ["Missing cells are replaced according to deterministic imputation rules.", "Indicator columns may be added for affected fields."], "metric_impact": self._metric_impact("missingness", study.ml_task), "risks_introduced": ["Imputation can introduce bias if missingness is systematic."], "required_decisions": []}]
        if code == "DUPLICATES":
            return [{**base, "title": "Duplicate-controlled variant", "objective": "Test whether repeated observations inflate validation evidence.", "operations": [self._op("drop_duplicate_rows", [], "Create a deduplicated candidate variant.")], "expected_changes": ["Exact duplicate rows are removed in the generated variant."], "metric_impact": self._metric_impact("duplicates", study.ml_task), "risks_introduced": ["If duplicates are legitimate repeated events, removal can discard signal."], "required_decisions": [self._decision("Confirm duplicate semantics", finding, "Treat exact duplicates as removable unless domain context says repeated events are meaningful.")]}]
        if code == "OUTLIERS":
            return [{**base, "title": "Outlier-robust variant", "objective": "Create a stable candidate for models sensitive to extreme values.", "operations": [self._op("winsorize_outliers", columns, "Bound extreme numeric values using a documented threshold."), self._op("robust_scale_numeric", columns, "Scale numeric fields using robust statistics.")], "expected_changes": ["Extreme numeric values are bounded or scaled more robustly."], "metric_impact": self._metric_impact("outliers", study.ml_task), "risks_introduced": ["Rare but meaningful cases may be softened by outlier treatment."], "required_decisions": [self._decision("Decide whether outliers are errors or rare valid cases", finding, "Preserve outliers unless evidence supports bounded treatment.")]}]
        if code == "CORRELATION":
            return [{**base, "title": "Feature compactness variant", "objective": "Reduce redundant feature signal and improve interpretability checks.", "operations": [self._op("review_correlated_features", columns, "Identify correlated feature groups."), self._op("lock_feature_set", columns, "Create an auditable reduced feature candidate when approved.")], "expected_changes": ["Feature set may become smaller after user-approved redundancy review."], "metric_impact": self._metric_impact("feature_reduction", study.ml_task), "risks_introduced": ["Removing correlated features can remove useful signal."], "required_decisions": [self._decision("Choose which correlated fields to keep", finding, "Keep the most interpretable or most causally appropriate field when domain knowledge exists.")]}]
        if code == "CLASS_IMBALANCE":
            return [{**base, "title": "Imbalance-aware variant", "objective": "Prepare variants and experiment constraints that expose minority-class behavior.", "operations": [self._op("preserve_stratified_split", [], "Keep class proportions controlled in validation."), self._op("class_weight_recommendation", [], "Pass class-weight guidance to experiments."), self._op("rebalance_training_data", [], "Create a training-only balancing candidate when approved.")], "expected_changes": ["Validation remains stratified; optional training-only balancing can be generated later."], "metric_impact": self._metric_impact("imbalance", study.ml_task), "risks_introduced": ["Balancing can distort real-world prevalence if used outside training folds."], "required_decisions": [self._decision("Approve training-only class balancing", finding, "Prefer class-sensitive reporting before changing class prevalence.")]}]
        if code == "TARGET_LEAKAGE":
            return [{**base, "title": "Leakage-safe variant", "objective": "Create a trustworthy experiment candidate by excluding leakage-like signals.", "operations": [self._op("drop_leakage_suspect_columns", columns, "Remove or quarantine target-proxy fields before modeling.")], "expected_changes": ["Suspected leakage columns are excluded from the generated modeling variant."], "metric_impact": self._metric_impact("leakage", study.ml_task), "risks_introduced": ["Removing an ambiguous field can reduce useful legitimate signal if it is not leakage."], "required_decisions": [self._decision("Confirm suspected leakage columns", finding, "Exclude only columns that are post-outcome, target-derived, or unjustifiable proxies.")]}]
        if code == "DRIFT":
            return [{**base, "title": "Distribution-shift review variant", "objective": "Keep version comparisons honest when the dataset population appears changed.", "operations": [self._op("treat_version_as_separate_condition", [], "Mark this version as a separate experimental condition."), self._op("compare_version_specific_results", [], "Require experiments to report version-specific metrics.")], "expected_changes": ["The dataset may not be merged into prior-version comparisons without explicit review."], "metric_impact": self._metric_impact("drift", study.ml_task), "risks_introduced": ["Treating versions separately can reduce pooled sample size."], "required_decisions": []}]
        if code in {"TARGET_SKEW", "SCALING"}:
            family = "target_quality" if code == "TARGET_SKEW" else "scaling"
            return [{**base, "title": "Metric stability variant", "objective": "Create a controlled candidate for evaluation stability.", "operations": [self._op("apply_configured_scaling_or_target_policy", columns, "Use the configured deterministic policy for the affected fields.")], "expected_changes": ["Configured transformation policy is carried forward to the variant generator."], "metric_impact": self._metric_impact(family, study.ml_task), "risks_introduced": ["Transformations can make final findings harder to interpret if not documented."], "required_decisions": [self._decision("Approve transformation policy", finding, "Use the simplest deterministic policy that preserves interpretability.")]}]
        return []

    @staticmethod
    def _op(operation: str, columns: list[str], purpose: str) -> dict[str, Any]:
        return {"operation": operation, "columns": columns, "purpose": purpose}

    @staticmethod
    def _decision(question: str, finding: dict, default: str) -> dict[str, Any]:
        return {"question": question, "finding_code": finding.get("code"), "affected_columns": DiagnosisContractService._columns(finding), "evidence": finding.get("evidence", {}), "recommended_default": default, "consequence_accept": "The generated variant will apply the related intervention.", "consequence_reject": "The issue remains documented as an experiment caution."}

    @staticmethod
    def _metric_impact(kind: str, task: str) -> dict[str, Any]:
        metrics = {
            "classification": ["primary metric", "precision", "recall", "F1", "confusion matrix"],
            "regression": ["primary metric", "MAE", "RMSE", "residual spread"],
            "clustering": ["primary metric", "cluster stability", "silhouette-style diagnostics"],
        }.get(task, ["primary metric"])
        templates = {
            "missingness": ("May improve usable signal by preserving rows.", "May reduce precision or increase error if imputation adds noise.", "If results change strongly across missingness strategies, final findings should state preprocessing sensitivity."),
            "duplicates": ("May improve generalization reliability.", "Validation metrics may decrease if duplicates previously inflated scores.", "Helps determine whether reported performance was affected by repeated records."),
            "outliers": ("May stabilize models sensitive to extreme numeric values.", "May harm rare-case generalization if extreme values are legitimate.", "Helps separate noise-sensitive performance from robust performance."),
            "imbalance": ("May improve minority-class recall or macro metrics.", "Accuracy or weighted metrics may decrease when minority behavior is exposed.", "Final findings should report whether performance is useful across classes."),
            "leakage": ("May make evaluation more trustworthy.", "Metrics may drop after leakage-like fields are removed.", "A large drop suggests previous performance was leakage-sensitive."),
            "feature_reduction": ("May improve generalization and interpretability.", "May reduce peak metric values if removed features contain signal.", "Helps determine whether final findings rely on compact stable features."),
            "drift": ("May clarify version-specific performance.", "Metrics may not be directly comparable across versions.", "Final findings should state whether dataset versions are separate evidence conditions."),
            "target_quality": ("May make error metrics more stable.", "Dataset size or target scale may change.", "Final findings should document target-treatment sensitivity."),
            "scaling": ("May improve stability for scale-sensitive models.", "Tree-style models may show less change.", "Final findings should document whether scale treatment affected results."),
        }
        positive, negative, finding = templates.get(kind, ("May change the primary metric.", "May introduce preprocessing sensitivity.", "Experiments must verify the effect."))
        return {"affected_metrics": metrics, "possible_positive_effect": positive, "possible_negative_effect": negative, "reliability_effect": "Creates a controlled variant so experiments can measure whether the intervention changes conclusions.", "final_finding_implication": finding, "verification_required": ["Compare against the raw source version.", "Keep target column and validation strategy fixed.", "Report the primary metric plus the listed secondary diagnostics."]}

    @staticmethod
    def _columns(finding: dict) -> list[str]:
        evidence = finding.get("evidence") or {}
        columns = []
        if evidence.get("columns"):
            for item in evidence["columns"]:
                columns.append(item.get("column") if isinstance(item, dict) else str(item))
        if evidence.get("target_column"):
            columns.append(evidence["target_column"])
        if evidence.get("correlations"):
            for item in evidence["correlations"]:
                columns.extend([item.get("left"), item.get("right")])
        if evidence.get("pairs"):
            for item in evidence["pairs"]:
                columns.extend([item.get("left"), item.get("right")])
        return sorted({column for column in columns if column})

    @staticmethod
    def _dominant_severity(counts: Counter) -> str:
        order = ["critical", "high", "medium", "low"]
        return next((item for item in order if counts.get(item)), "low")

    def _readiness(self, diagnosis: dict, risk_families: list[dict], interventions: list[dict], decisions: list[dict]) -> dict[str, Any]:
        critical = any(item.get("severity") == "critical" for item in diagnosis["findings"])
        high = any(item.get("severity") == "high" for item in diagnosis["findings"])
        status = "requires review before experiment" if critical else "variant generation recommended" if high or interventions else "ready with caution" if diagnosis["findings"] else "ready for baseline experiment"
        return {"status": status, "mlrs_score": diagnosis["mlrs_score"], "lrs_score": diagnosis["lrs_score"], "finding_count": len(diagnosis["findings"]), "detected_risk_families": [item["family"] for item in risk_families], "intervention_count": len(interventions), "required_decision_count": len(decisions), "experiment_caution_count": len([item for item in interventions if item.get("metric_impact")])}

    @staticmethod
    def _selected_plan(version, interventions: list[dict], decisions: list[dict]) -> dict[str, Any]:
        operations = [operation for option in interventions for operation in option["operations"]]
        columns = sorted({column for operation in operations for column in operation.get("columns", [])})
        return {"source_version_id": version.id, "source_version_number": version.version_number, "selected_option_ids": [item["id"] for item in interventions], "operation_count": len(operations), "affected_columns": columns, "unresolved_decisions": [item["question"] for item in decisions], "variant_names": [f"V{version.version_number} - {item['title']}" for item in interventions], "comparison_plan": [item["recommended_comparison"] for item in interventions]}

    @staticmethod
    def _experiment_handoff(study, version, diagnosis: dict, interventions: list[dict]) -> dict[str, Any]:
        metrics = []
        for item in interventions:
            metrics.extend(item.get("metric_impact", {}).get("affected_metrics", []))
        return {"source_version_id": version.id, "diagnosis_report_id": diagnosis["id"], "task_type": study.ml_task, "required_baseline": f"V{version.version_number}", "recommended_metrics": sorted(set(metrics)), "constraints": ["Use the same target column and validation strategy when comparing variants.", "Preserve fingerprint and configuration evidence for every generated variant.", "Treat interventions as hypotheses until experiments verify metric impact."], "cautions": [item.get("risk") for item in diagnosis["findings"] if item.get("risk")]}

    def _column_impact(self, profile: dict, findings: list[dict]) -> list[dict]:
        risk_by_column = defaultdict(set)
        ops_by_column = defaultdict(int)
        for finding in findings:
            family = self.family_labels.get(finding.get("code"), finding.get("code", "diagnosis").lower())
            for column in self._columns(finding):
                risk_by_column[column].add(family)
                ops_by_column[column] += 1
        rows = []
        for column in profile.get("columns", []):
            name = column.get("name")
            if not name or name not in risk_by_column:
                continue
            rows.append({"column": name, "role": column.get("role"), "data_type": column.get("data_type"), "missing_ratio": column.get("missing_ratio"), "unique_count": column.get("unique_count"), "outlier_count": column.get("outlier_count"), "risk_families": sorted(risk_by_column[name]), "recommended_operation_count": ops_by_column[name]})
        return rows
