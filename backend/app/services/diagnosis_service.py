from typing import Any


class DiagnosisService:
    ruleset_version = "diagnosis-2.0"
    severity_weight = {"low": 25, "medium": 50, "high": 75, "critical": 100}

    @staticmethod
    def finding(issue: str, severity: str, evidence: dict, risk: str, recommendation: str, code: str) -> dict:
        return {"code": code, "issue": issue, "severity": severity, "evidence": evidence, "risk": risk, "recommendation": recommendation}

    def diagnose(self, profile: dict, semantic_diff: dict | None, lineage: dict, configuration: dict) -> dict[str, Any]:
        summary, task_profile = profile["summary"], profile.get("task_profile", {})
        findings = []
        missing = summary["missing_ratio"]
        if missing >= .05:
            severity = "critical" if missing >= .4 else "high" if missing >= .2 else "medium"
            findings.append(self.finding("High missingness", severity, {"missing_ratio": missing, "missing_cells": summary["missing_cells"]}, "Biased samples, unstable preprocessing, and reduced usable evidence.", "Document missingness mechanisms and compare deterministic imputation policies.", "MISSINGNESS"))
        if summary["duplicate_ratio"] >= .01:
            findings.append(self.finding("Duplicate observations", "high" if summary["duplicate_ratio"] >= .1 else "medium", {"duplicate_ratio": summary["duplicate_ratio"], "duplicate_rows": summary["duplicate_rows"]}, "Duplicates can overweight observations and leak across future splits.", "Confirm duplicate semantics and evaluate a deduplicated evidence version.", "DUPLICATES"))
        outlier_columns = [{"column": row["name"], "ratio": row.get("outlier_ratio", 0)} for row in profile["columns"] if row.get("outlier_ratio", 0) >= .05 and row["role"] != "target"]
        if outlier_columns:
            findings.append(self.finding("Feature outlier risk", "medium", {"columns": outlier_columns}, "Extreme values may dominate scaling and distance calculations.", "Validate extreme observations and compare robust scaling or bounded treatment.", "OUTLIERS"))
        if profile["high_correlations"]:
            findings.append(self.finding("High feature correlation", "medium", {"pairs": profile["high_correlations"][:20]}, "Redundant signals can reduce stability and interpretability.", "Review correlated features and document any controlled feature-selection policy.", "CORRELATION"))
        if profile["task_type"] == "classification" and (task_profile.get("imbalance_ratio") or 0) >= 2:
            ratio = task_profile["imbalance_ratio"]
            findings.append(self.finding("Class imbalance", "critical" if ratio >= 10 else "high" if ratio >= 4 else "medium", {"imbalance_ratio": ratio, "distribution": task_profile.get("class_distribution")}, "Aggregate metrics can hide poor minority-class behavior.", "Use stratified validation and report class-sensitive metrics.", "CLASS_IMBALANCE"))
        if profile["task_type"] == "regression" and abs(task_profile.get("target_skewness") or 0) >= 1:
            findings.append(self.finding("Skewed regression target", "medium", {"target_skewness": task_profile["target_skewness"]}, "A heavy target tail can make average errors unstable.", "Use robust evaluation metrics and test a documented target transformation.", "TARGET_SKEW"))
        if profile["task_type"] == "clustering" and task_profile.get("scaling_required"):
            findings.append(self.finding("Incompatible feature scales", "high", {"spread_ratio": task_profile["spread_ratio"]}, "Large-scale features can dominate distance-based structure.", "Apply the configured deterministic scaling strategy before future clustering.", "SCALING"))
        if semantic_diff and semantic_diff.get("dsi_score", 0) >= 30:
            findings.append(self.finding("Dataset drift risk", "high" if semantic_diff["dsi_score"] >= 60 else "medium", {"dsi_score": semantic_diff["dsi_score"], "scm_score": semantic_diff["scm_score"]}, "The current evidence may represent a changed population or collection process.", "Treat versions as separate evidence conditions and investigate the largest shifts.", "DRIFT"))
        target = configuration.get("target_column")
        leakage_pairs = [pair for pair in profile["high_correlations"] if target in {pair["left"], pair["right"]} and abs(pair["correlation"]) >= .98]
        if leakage_pairs:
            findings.append(self.finding("Potential target leakage", "critical", {"target_column": target, "correlations": leakage_pairs}, "A feature may encode the outcome and invalidate future evaluation.", "Remove or justify proxy features before any model experiment.", "TARGET_LEAKAGE"))
        breakdown = self.score_breakdown(profile, semantic_diff, lineage, configuration, findings)
        return {
            "findings": findings,
            "mlrs_score": breakdown["mlrs_score"],
            "lrs_score": breakdown["lrs_score"],
            "score_breakdown": breakdown,
            "mlrs_components": breakdown["mlrs_components"],
            "lrs_components": breakdown["lrs_components"],
            "ruleset_version": self.ruleset_version,
        }

    def score_breakdown(self, profile: dict, semantic_diff: dict | None, lineage: dict, configuration: dict, findings: list[dict]) -> dict[str, Any]:
        summary, task_profile = profile["summary"], profile.get("task_profile", {})
        columns = profile.get("columns") or []
        semantic = semantic_diff or {}
        semantic_report = semantic.get("report") or {}
        target = configuration.get("target_column")
        feature_columns = [row for row in columns if row.get("role") != "target"]
        target_column = next((row for row in columns if row.get("name") == target), None)

        missing_columns = [row["name"] for row in columns if row.get("missing_count", 0) > 0]
        outlier_columns = [row["name"] for row in feature_columns if row.get("outlier_ratio", 0) >= .05]
        high_corr_pairs = profile.get("high_correlations") or []
        drift_columns = sorted(set((semantic_report.get("feature_shift_scores") or {}).keys()) | set((semantic_report.get("missingness_changes_by_column") or {}).keys()))
        class_ratio = task_profile.get("imbalance_ratio") or 1

        mlrs_components = {
            "missingness": self._cap(summary.get("missing_ratio", 0) * 125, 25),
            "duplicates": self._cap(summary.get("duplicate_ratio", 0) * 150, 15),
            "imbalance": self._cap(max(class_ratio - 1, 0) * 5, 20) if profile.get("task_type") == "classification" else 0,
            "outliers": self._cap(max([row.get("outlier_ratio", 0) for row in feature_columns] or [0]) * 75, 15),
            "correlation": self._cap(len(high_corr_pairs) * 4, 10),
            "target_quality": self._target_quality_score(profile, task_profile, target_column),
            "drift": self._cap((semantic.get("dsi_score", 0) * .18) + (semantic.get("scm_score", 0) * .08), 20),
        }
        lrs_components = {
            "target_correlation": self._cap(max([abs(pair.get("correlation", 0)) for pair in high_corr_pairs if target in {pair.get("left"), pair.get("right")}] or [0]) * 50, 50),
            "target_name_similarity": self._target_name_similarity_score(target, columns),
            "post_outcome_columns": self._post_outcome_score(target, columns),
            "split_contamination": self._cap(summary.get("duplicate_ratio", 0) * 200, 20),
        }
        reproducibility_components = {
            "missing_parent": 0 if lineage.get("source_version_id") or lineage.get("version_number") == 1 else 25,
            "undocumented_version": 15 if not lineage.get("version_notes") else 0,
            "semantic_change": self._cap(semantic.get("scm_score", 0) * .5, 50),
            "dataset_shift": self._cap(semantic.get("dsi_score", 0) * .35, 35),
        }
        component_details = {
            "mlrs": {
                "missingness": self._detail("Missingness", missing_columns, "Training rows may need imputation, filtering, or missingness-aware variants.", "Compare deterministic imputation and missing-indicator variants."),
                "duplicates": self._detail("Duplicates", [], "Repeated rows can overweight samples and contaminate validation splits.", "Create a deduplicated variant and compare metric stability."),
                "imbalance": self._detail("Class imbalance", [target] if target else [], "Minority-class behavior may be hidden by aggregate metrics.", "Use stratified validation and class-sensitive metrics."),
                "outliers": self._detail("Feature outliers", outlier_columns, "Extreme feature values can dominate scaling and model coefficients.", "Compare robust scaling, clipping, and inspected-clean variants."),
                "correlation": self._detail("High feature correlation", sorted(set(sum(([pair.get("left"), pair.get("right")] for pair in high_corr_pairs), []))), "Redundant signals can reduce interpretability and make findings unstable.", "Review correlated features before automated feature selection."),
                "target_quality": self._detail("Target quality", [target] if target else [], "Target missingness, skew, or unsuitable scale can distort training conclusions.", "Inspect target distribution before final experiment design."),
                "drift": self._detail("Cross-version drift", drift_columns, "Current version may not be equivalent to previous evidence conditions.", "Treat changed versions as separate experiment baselines when needed."),
            },
            "lrs": {
                "target_correlation": self._detail("Target correlation", sorted(set(sum(([pair.get("left"), pair.get("right")] for pair in high_corr_pairs if target in {pair.get("left"), pair.get("right")}), []))), "A feature may encode the answer directly or indirectly.", "Quarantine suspicious target-proxy columns before modeling."),
                "target_name_similarity": self._detail("Target-like names", self._target_like_columns(target, columns), "Columns with target-like names can represent labels, outcomes, or post-event values.", "Require human confirmation before using these columns."),
                "post_outcome_columns": self._detail("Post-outcome indicators", self._post_outcome_columns(columns), "Post-event variables can make validation scores look unrealistically strong.", "Exclude post-outcome fields from baseline variants unless justified."),
                "split_contamination": self._detail("Split contamination", [], "Duplicate rows can appear across train and validation splits.", "Deduplicate before train/test splitting or use group-aware splitting."),
            },
        }
        mlrs = round(min(100.0, sum(mlrs_components.values())), 2)
        lrs = round(min(100.0, sum(lrs_components.values())), 2)
        return {
            "ruleset_version": self.ruleset_version,
            "score_meaning": {
                "mlrs_score": "Overall ML training readiness risk. Higher means more evidence issues should be resolved before downstream experiments.",
                "lrs_score": "True leakage risk. Higher means stronger evidence that features, duplicates, or post-outcome fields may invalidate evaluation.",
            },
            "mlrs_score": mlrs,
            "lrs_score": lrs,
            "mlrs_components": {key: round(value, 2) for key, value in mlrs_components.items()},
            "lrs_components": {key: round(value, 2) for key, value in lrs_components.items()},
            "reproducibility_components": {key: round(value, 2) for key, value in reproducibility_components.items()},
            "component_details": component_details,
            "variant_generator_hints": self._variant_hints(mlrs_components, lrs_components, component_details),
        }

    @staticmethod
    def _cap(value: float, maximum: float) -> float:
        return min(max(float(value or 0), 0), maximum)

    @staticmethod
    def _detail(label: str, columns: list[str], effect: str, next_action: str) -> dict[str, Any]:
        return {"label": label, "columns": [column for column in columns if column], "effect": effect, "next_action": next_action}

    def _target_quality_score(self, profile: dict, task_profile: dict, target_column: dict | None) -> float:
        if not target_column:
            return 15 if profile.get("task_type") in {"classification", "regression"} else 0
        missing_score = self._cap(target_column.get("missing_ratio", 0) * 150, 10)
        if profile.get("task_type") == "regression":
            skew_score = self._cap(abs(task_profile.get("target_skewness") or 0) * 4, 10)
            outlier_score = self._cap((task_profile.get("target_outlier_count") or 0) * 2, 5)
            return missing_score + skew_score + outlier_score
        return missing_score

    @staticmethod
    def _target_like_columns(target: str | None, columns: list[dict]) -> list[str]:
        if not target:
            return []
        tokens = {part for part in str(target).lower().replace("-", "_").split("_") if len(part) >= 3}
        target_lower = str(target).lower()
        matches = []
        for row in columns:
            name = str(row.get("name", ""))
            lower = name.lower()
            if lower == target_lower:
                continue
            if target_lower in lower or any(token in lower for token in tokens):
                matches.append(name)
        return matches

    def _target_name_similarity_score(self, target: str | None, columns: list[dict]) -> float:
        return self._cap(len(self._target_like_columns(target, columns)) * 7.5, 15)

    @staticmethod
    def _post_outcome_columns(columns: list[dict]) -> list[str]:
        markers = ("outcome", "result", "final", "after", "post", "diagnosis", "diagnosed", "approved", "placed", "status")
        return [str(row.get("name")) for row in columns if any(marker in str(row.get("name", "")).lower() for marker in markers)]

    def _post_outcome_score(self, target: str | None, columns: list[dict]) -> float:
        candidates = [column for column in self._post_outcome_columns(columns) if column and column != target]
        return self._cap(len(candidates) * 7.5, 15)

    @staticmethod
    def _variant_hints(mlrs_components: dict, lrs_components: dict, component_details: dict) -> list[dict]:
        hints = []
        for family, components in (("mlrs", mlrs_components), ("lrs", lrs_components)):
            for key, score in components.items():
                if score <= 0:
                    continue
                detail = component_details[family][key]
                hints.append({"family": family, "component": key, "score": round(score, 2), "columns": detail["columns"], "recommended_action": detail["next_action"], "expected_effect": detail["effect"]})
        return sorted(hints, key=lambda item: item["score"], reverse=True)
