from collections import defaultdict, deque
from typing import Any


MLRS_COMPONENT_CAPS = {
    "missingness": 25.0,
    "duplicates": 18.0,
    "imbalance": 20.0,
    "outliers": 15.0,
    "correlation_redundancy": 10.0,
    "target_quality": 17.0,
    "evolution_readiness": 15.0,
}

LRS_COMPONENT_CAPS = {
    "direct_target_leakage": 35.0,
    "proxy_leakage": 25.0,
    "target_name_similarity": 8.0,
    "temporal_post_outcome": 18.0,
    "split_contamination": 12.0,
    "identifier_memorization": 8.0,
}

DIRECT_LEAKAGE_MARKERS = ("target", "label", "answer", "ground_truth", "actual")
POST_OUTCOME_MARKERS = ("outcome", "result", "final", "after", "post", "approved", "diagnosis", "diagnosed", "placed", "status")
IDENTIFIER_MARKERS = ("id", "uuid", "guid", "employeeid", "studentid", "customerid", "userid")


class DiagnosisService:
    ruleset_version = "diagnosis-2.0"
    severity_weight = {"low": 25, "medium": 50, "high": 75, "critical": 100}

    @staticmethod
    def finding(issue: str, severity: str, evidence: dict, risk: str, recommendation: str, code: str) -> dict:
        return {"code": code, "issue": issue, "severity": severity, "evidence": evidence, "risk": risk, "recommendation": recommendation}

    def diagnose(self, profile: dict, semantic_diff: dict | None, lineage: dict, configuration: dict) -> dict[str, Any]:
        summary, task_profile = profile["summary"], profile.get("task_profile", {})
        findings = []
        missing = summary.get("missing_ratio", 0)
        if missing >= .05:
            severity = "critical" if missing >= .4 else "high" if missing >= .2 else "medium"
            findings.append(self.finding("High missingness", severity, {"missing_ratio": missing, "missing_cells": summary.get("missing_cells", 0)}, "Biased samples, unstable preprocessing, and reduced usable evidence.", "Document missingness mechanisms and compare deterministic imputation policies.", "MISSINGNESS"))
        if summary.get("duplicate_ratio", 0) >= .01:
            findings.append(self.finding("Duplicate observations", "high" if summary.get("duplicate_ratio", 0) >= .1 else "medium", {"duplicate_ratio": summary.get("duplicate_ratio", 0), "duplicate_rows": summary.get("duplicate_rows", 0)}, "Duplicates can overweight observations. Split contamination is only confirmed when split overlap evidence exists.", "Confirm duplicate semantics and evaluate a deduplicated evidence version.", "DUPLICATES"))
        outlier_columns = [{"column": row["name"], "ratio": row.get("outlier_ratio", 0)} for row in profile.get("columns", []) if row.get("outlier_ratio", 0) >= .05 and row.get("role") != "target"]
        if outlier_columns:
            findings.append(self.finding("Feature outlier risk", "medium", {"columns": outlier_columns}, "Extreme values may dominate scaling and distance calculations.", "Validate extreme observations and compare robust scaling or bounded treatment.", "OUTLIERS"))
        if profile.get("high_correlations"):
            findings.append(self.finding("High feature redundancy", "medium", {"clusters": self._correlation_clusters(profile)}, "Redundant feature groups can reduce stability and interpretability.", "Review correlated clusters and document any controlled feature-selection policy.", "CORRELATION"))
        if profile.get("task_type") == "classification" and self._imbalance_score(task_profile) >= 5:
            ratio = task_profile.get("imbalance_ratio")
            findings.append(self.finding("Class imbalance", "critical" if (ratio or 1) >= 10 else "high" if (ratio or 1) >= 4 else "medium", {"imbalance_ratio": ratio, "distribution": task_profile.get("class_distribution")}, "Aggregate metrics can hide poor minority-class behavior.", "Use stratified validation and report class-sensitive metrics.", "CLASS_IMBALANCE"))
        if profile.get("task_type") == "regression" and abs(task_profile.get("target_skewness") or 0) >= 1:
            findings.append(self.finding("Skewed regression target", "medium", {"target_skewness": task_profile["target_skewness"]}, "A heavy target tail can make average errors unstable.", "Use robust evaluation metrics and test a documented target transformation.", "TARGET_SKEW"))
        if profile.get("task_type") == "clustering" and task_profile.get("scaling_required"):
            findings.append(self.finding("Incompatible feature scales", "high", {"spread_ratio": task_profile["spread_ratio"]}, "Large-scale features can dominate distance-based structure.", "Apply the configured deterministic scaling strategy before future clustering.", "SCALING"))

        breakdown = self.score_breakdown(profile, semantic_diff, lineage, configuration, findings)
        leakage_evidence = breakdown.get("leakage_evidence", {})
        if breakdown["lrs_score"] >= 30 or leakage_evidence.get("direct_features"):
            findings.append(self.finding("Potential target leakage", "critical" if breakdown["lrs_score"] >= 55 else "high", leakage_evidence, "A feature, split, or post-outcome field may encode the answer and invalidate evaluation.", "Quarantine direct/proxy/post-outcome fields and recompute leakage-safe variants.", "TARGET_LEAKAGE"))

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
        semantic_report = (semantic_diff or {}).get("report") or {}
        target = configuration.get("target_column")
        feature_columns = [row for row in columns if row.get("role") != "target"]
        target_column = next((row for row in columns if row.get("name") == target), None)

        missing_columns = [row["name"] for row in columns if row.get("missing_count", 0) > 0]
        outlier_columns = [row["name"] for row in feature_columns if row.get("outlier_ratio", 0) >= .05]
        high_corr_pairs = profile.get("high_correlations") or []

        mlrs_components = {
            "missingness": self._missingness_score(summary, columns),
            "duplicates": self._duplicate_score(profile, semantic_report),
            "imbalance": self._imbalance_score(task_profile) if profile.get("task_type") == "classification" else 0.0,
            "outliers": self._outlier_score(feature_columns),
            "correlation_redundancy": self._correlation_score(profile),
            "target_quality": self._target_quality_score(profile, task_profile, target_column),
            "evolution_readiness": self._evolution_readiness_score(semantic_report, target),
        }
        leakage = self._leakage_components(profile, configuration)
        lrs_components = leakage["components"]
        reproducibility_components = {
            "missing_parent": 0 if lineage.get("source_version_id") or lineage.get("version_number") == 1 else 25,
            "undocumented_version": 15 if not lineage.get("version_notes") else 0,
            "semantic_change": self._cap((semantic_diff or {}).get("scm_score", 0) * .5, 50),
            "dataset_shift": self._cap((semantic_diff or {}).get("dsi_score", 0) * .35, 35),
        }
        component_details = {
            "mlrs": {
                "missingness": self._detail("Missingness", missing_columns, "Training rows may need imputation, filtering, or missingness-aware variants.", "Compare deterministic imputation and missing-indicator variants."),
                "duplicates": self._detail("Duplicates", [], "Repeated or conflicting rows can overweight samples and destabilize training.", "Create exact-deduplicated and conflict-reviewed variants."),
                "imbalance": self._detail("Class imbalance", [target] if target else [], "Minority-class behavior may be hidden by aggregate metrics.", "Use stratified validation and class-sensitive metrics."),
                "outliers": self._detail("Feature outliers", outlier_columns, "Extreme feature values can dominate scaling and model coefficients.", "Compare robust scaling, clipping, and inspected-clean variants."),
                "correlation_redundancy": self._detail("Correlation clusters", self._cluster_columns(high_corr_pairs), "Redundant feature groups can reduce interpretability and make findings unstable.", "Review correlated clusters before automated feature selection."),
                "target_quality": self._detail("Target quality", [target] if target else [], "Target missingness, skew, imbalance, or unsuitable scale can distort training conclusions.", "Inspect target distribution before final experiment design."),
                "evolution_readiness": self._detail("Readiness degradation", self._worsened_columns(semantic_report, target), "The new version worsened concrete readiness evidence such as missingness or duplicates.", "Compare readiness components before accepting the changed version."),
            },
            "lrs": {
                "direct_target_leakage": self._detail("Direct target leakage", leakage["evidence"]["direct_features"], "A feature appears to duplicate, invert, or deterministically encode the target.", "Remove or justify direct target-derived fields before modeling."),
                "proxy_leakage": self._detail("Proxy leakage", leakage["evidence"]["proxy_features"], "A feature has unusually strong target association plus leakage context.", "Quarantine suspicious proxies and validate with leakage-safe features."),
                "target_name_similarity": self._detail("Target-like names", leakage["evidence"]["target_like_features"], "Target-like naming is supporting evidence, not proof of leakage.", "Require human confirmation before using target-like fields."),
                "temporal_post_outcome": self._detail("Post-outcome indicators", leakage["evidence"]["post_outcome_features"], "Post-event variables can make validation scores look unrealistically strong.", "Exclude post-outcome fields from baseline variants unless justified."),
                "split_contamination": self._detail("Split overlap", leakage["evidence"]["split_overlap_features"], "The same entity or row appears in multiple explicit data splits.", "Deduplicate or group split before evaluation."),
                "identifier_memorization": self._detail("Identifier memorization", leakage["evidence"]["identifier_features"], "High-cardinality identifiers may memorize examples but are low risk alone.", "Drop or group identifiers unless they are required for joins only."),
            },
        }
        mlrs = round(self._cap(sum(mlrs_components.values()), 100.0), 2)
        lrs = round(self._cap(sum(lrs_components.values()), 100.0), 2)
        return {
            "ruleset_version": self.ruleset_version,
            "metric_algorithm_versions": {"mlrs": "2.0", "lrs": "2.0"},
            "score_meaning": {
                "mlrs_score": "ML training readiness risk. Higher means more deterministic data-quality issues should be resolved before experiments.",
                "lrs_score": "Leakage risk. Higher means stronger deterministic evidence that features, identifiers, splits, or post-outcome fields may invalidate evaluation.",
            },
            "mlrs_score": mlrs,
            "lrs_score": lrs,
            "mlrs_components": {key: round(value, 2) for key, value in mlrs_components.items()},
            "lrs_components": {key: round(value, 2) for key, value in lrs_components.items()},
            "reproducibility_components": {key: round(value, 2) for key, value in reproducibility_components.items()},
            "component_details": component_details,
            "component_evidence": {
                "mlrs": {
                    "correlation_clusters": self._correlation_clusters(profile),
                    "missingness": self._missingness_evidence(summary, columns),
                    "evolution_readiness": self._evolution_evidence(semantic_report, target),
                },
                "lrs": leakage["evidence"],
            },
            "leakage_evidence": leakage["evidence"],
            "variant_generator_hints": self._variant_hints(mlrs_components, lrs_components, component_details),
        }

    @staticmethod
    def _cap(value: float, maximum: float) -> float:
        return min(max(float(value or 0), 0), maximum)

    @staticmethod
    def _detail(label: str, columns: list[str], effect: str, next_action: str) -> dict[str, Any]:
        return {"label": label, "columns": [column for column in columns if column], "effect": effect, "next_action": next_action}

    def _missingness_score(self, summary: dict, columns: list[dict]) -> float:
        ratios = [row.get("missing_ratio", 0) for row in columns]
        affected_ratio = sum(ratio > 0 for ratio in ratios) / max(len(ratios), 1)
        max_ratio = max(ratios or [0])
        score = (
            self._cap(summary.get("missing_ratio", 0) * 100, 12)
            + self._cap(affected_ratio * 12, 6)
            + self._cap(max_ratio * 35, 7)
        )
        return self._cap(score, MLRS_COMPONENT_CAPS["missingness"])

    @staticmethod
    def _missingness_evidence(summary: dict, columns: list[dict]) -> dict:
        ratios = [row.get("missing_ratio", 0) for row in columns]
        return {
            "overall_missing_ratio": summary.get("missing_ratio", 0),
            "affected_feature_ratio": round(sum(ratio > 0 for ratio in ratios) / max(len(ratios), 1), 6),
            "max_feature_missing_ratio": max(ratios or [0]),
        }

    def _duplicate_score(self, profile: dict, semantic_report: dict) -> float:
        summary = profile.get("summary", {})
        exact = self._cap(summary.get("duplicate_ratio", 0) * 100, 10)
        conflict_ratio = (
            profile.get("conflicting_duplicate_ratio")
            or semantic_report.get("conflicting_duplicate_ratio")
            or 0
        )
        conflicting = self._cap(conflict_ratio * 120, 8)
        return self._cap(exact + conflicting, MLRS_COMPONENT_CAPS["duplicates"])

    def _imbalance_score(self, task_profile: dict) -> float:
        distribution = task_profile.get("class_distribution") or {}
        counts = [float(value) for value in distribution.values() if value is not None and float(value) > 0]
        if len(counts) < 2:
            return 0.0
        total = sum(counts)
        largest = max(counts) / total
        ideal = 1 / len(counts)
        normalized = (largest - ideal) / max(1 - ideal, 1e-9)
        minority_ratio = min(counts) / max(max(counts), 1)
        ratio_penalty = max(0.0, 1 - minority_ratio)
        return self._cap((0.7 * normalized + 0.3 * ratio_penalty) * MLRS_COMPONENT_CAPS["imbalance"], MLRS_COMPONENT_CAPS["imbalance"])

    def _outlier_score(self, feature_columns: list[dict]) -> float:
        ratios = [row.get("outlier_ratio", 0) for row in feature_columns]
        if not ratios:
            return 0.0
        affected = sum(ratio >= .05 for ratio in ratios) / len(ratios)
        average = sum(ratios) / len(ratios)
        score = self._cap(affected * 9, 9) + self._cap(average * 75, 6)
        return self._cap(score, MLRS_COMPONENT_CAPS["outliers"])

    def _correlation_score(self, profile: dict) -> float:
        clusters = self._correlation_clusters(profile)
        feature_count = max(len([row for row in profile.get("columns", []) if row.get("role") != "target"]), 1)
        clustered_features = len({column for cluster in clusters for column in cluster["columns"]})
        largest = max([len(cluster["columns"]) for cluster in clusters] or [0])
        score = (clustered_features / feature_count) * 6 + (largest / feature_count) * 3 + min(len(clusters), 3)
        return self._cap(score, MLRS_COMPONENT_CAPS["correlation_redundancy"])

    def _target_quality_score(self, profile: dict, task_profile: dict, target_column: dict | None) -> float:
        if not target_column:
            return 15 if profile.get("task_type") in {"classification", "regression"} else 0
        missing_score = self._cap(target_column.get("missing_ratio", 0) * 120, 8)
        if profile.get("task_type") == "regression":
            skew_score = self._cap(abs(task_profile.get("target_skewness") or 0) * 3, 6)
            target_count = max((profile.get("summary") or {}).get("row_count", 1), 1)
            outlier_score = self._cap(((task_profile.get("target_outlier_count") or 0) / target_count) * 60, 3)
            return self._cap(missing_score + skew_score + outlier_score, MLRS_COMPONENT_CAPS["target_quality"])
        if profile.get("task_type") == "classification":
            return self._cap(missing_score + self._cap(self._imbalance_score(task_profile) * .25, 5), MLRS_COMPONENT_CAPS["target_quality"])
        return missing_score

    def _evolution_readiness_score(self, semantic_report: dict, target: str | None) -> float:
        evidence = self._evolution_evidence(semantic_report, target)
        score = (
            self._cap(evidence["overall_missingness_worsening"] * 100, 5)
            + self._cap(evidence["max_feature_missingness_worsening"] * 45, 6)
            + self._cap(evidence["duplicate_ratio_worsening"] * 120, 4)
        )
        return self._cap(score, MLRS_COMPONENT_CAPS["evolution_readiness"])

    @staticmethod
    def _evolution_evidence(semantic_report: dict, target: str | None) -> dict:
        missing_changes = semantic_report.get("missingness_changes_by_column") or {}
        worsening = [value.get("ratio_delta", 0) for value in missing_changes.values() if value.get("ratio_delta", 0) > 0]
        duplicate_rows = semantic_report.get("duplicate_rows") or {}
        row_count = max(semantic_report.get("row_count_current") or 1, 1)
        duplicate_delta_ratio = max(0.0, (duplicate_rows.get("delta") or 0) / row_count)
        return {
            "overall_missingness_worsening": max(0.0, semantic_report.get("missing_ratio_change") or 0),
            "max_feature_missingness_worsening": max(worsening or [0.0]),
            "duplicate_ratio_worsening": duplicate_delta_ratio,
            "target_missingness_worsened": bool(target and (missing_changes.get(target) or {}).get("ratio_delta", 0) > 0),
        }

    @staticmethod
    def _worsened_columns(semantic_report: dict, target: str | None) -> list[str]:
        missing_changes = semantic_report.get("missingness_changes_by_column") or {}
        return [column for column, value in missing_changes.items() if value.get("ratio_delta", 0) > 0 and column != target]

    def _leakage_components(self, profile: dict, configuration: dict) -> dict:
        columns = profile.get("columns") or []
        target = configuration.get("target_column")
        target_like = self._target_like_columns(target, columns)
        post_outcome = [column for column in self._post_outcome_columns(columns) if column != target]
        identifiers = self._identifier_columns(columns, target)
        target_pairs = self._target_association_pairs(profile, target)

        direct_features, proxy_features = [], []
        for pair in target_pairs:
            feature = pair["feature"]
            association = abs(pair["association"])
            lower = feature.lower()
            has_direct_name = any(marker in lower for marker in DIRECT_LEAKAGE_MARKERS) or feature in target_like
            has_temporal_name = feature in post_outcome
            if association >= .999 and (has_direct_name or pair.get("association_type") in {"exact_copy", "inverse_mapping", "deterministic_mapping"}):
                direct_features.append(feature)
            elif association >= .98 and (has_temporal_name or has_direct_name):
                proxy_features.append(feature)

        split_overlap = profile.get("split_overlap") or profile.get("split_contamination") or {}
        overlap_ratio = float(split_overlap.get("overlap_ratio", 0) if isinstance(split_overlap, dict) else 0)
        duplicate_ratio = (profile.get("summary") or {}).get("duplicate_ratio", 0)

        components = {
            "direct_target_leakage": self._diminishing_score(len(set(direct_features)), 22, LRS_COMPONENT_CAPS["direct_target_leakage"]),
            "proxy_leakage": self._diminishing_score(len(set(proxy_features)), 12, LRS_COMPONENT_CAPS["proxy_leakage"]),
            "target_name_similarity": self._diminishing_score(len(set(target_like)), 3, LRS_COMPONENT_CAPS["target_name_similarity"]),
            "temporal_post_outcome": self._diminishing_score(len(set(post_outcome)), 7, LRS_COMPONENT_CAPS["temporal_post_outcome"]),
            "split_contamination": self._cap(overlap_ratio * 100, LRS_COMPONENT_CAPS["split_contamination"]) if overlap_ratio else self._cap(duplicate_ratio * 25, 4),
            "identifier_memorization": self._diminishing_score(len(set(identifiers)), 2.5, LRS_COMPONENT_CAPS["identifier_memorization"]),
        }
        evidence = {
            "target_column": target,
            "direct_features": sorted(set(direct_features)),
            "proxy_features": sorted(set(proxy_features)),
            "target_like_features": target_like,
            "post_outcome_features": post_outcome,
            "identifier_features": identifiers,
            "target_associations": target_pairs[:20],
            "split_overlap_features": split_overlap.get("columns", []) if isinstance(split_overlap, dict) else [],
            "split_overlap_ratio": overlap_ratio,
            "duplicate_rows_used_as_low_confidence_signal": bool(duplicate_ratio and not overlap_ratio),
        }
        return {"components": components, "evidence": evidence}

    @staticmethod
    def _diminishing_score(count: int, first_item_points: float, cap: float) -> float:
        if count <= 0:
            return 0.0
        return min(cap, first_item_points * (1 - (0.6 ** count)) / 0.4)

    @staticmethod
    def _target_association_pairs(profile: dict, target: str | None) -> list[dict]:
        if not target:
            return []
        pairs = []
        for pair in profile.get("high_correlations") or []:
            if target not in {pair.get("left"), pair.get("right")}:
                continue
            feature = pair.get("right") if pair.get("left") == target else pair.get("left")
            pairs.append({"feature": feature, "association": pair.get("correlation", 0), "association_type": "numeric_correlation"})
        for pair in profile.get("target_associations") or []:
            feature = pair.get("feature") or pair.get("column")
            if feature:
                pairs.append({"feature": str(feature), "association": pair.get("association", pair.get("score", 0)), "association_type": pair.get("type", "deterministic")})
        return sorted(pairs, key=lambda item: abs(item.get("association", 0)), reverse=True)

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
        return sorted(matches)

    @staticmethod
    def _post_outcome_columns(columns: list[dict]) -> list[str]:
        return sorted(str(row.get("name")) for row in columns if any(marker in str(row.get("name", "")).lower() for marker in POST_OUTCOME_MARKERS))

    @staticmethod
    def _identifier_columns(columns: list[dict], target: str | None) -> list[str]:
        matches = []
        for row in columns:
            name = str(row.get("name", ""))
            lower = name.lower().replace("_", "")
            if name == target:
                continue
            id_like = lower in IDENTIFIER_MARKERS or lower.endswith("id") or "uuid" in lower or "guid" in lower
            high_cardinality = row.get("unique_ratio", 0) >= .95
            if id_like or high_cardinality and row.get("role") != "target":
                matches.append(name)
        return sorted(set(matches))

    def _correlation_clusters(self, profile: dict) -> list[dict]:
        graph: dict[str, set[str]] = defaultdict(set)
        target = (profile.get("configuration") or {}).get("target_column")
        for pair in profile.get("high_correlations") or []:
            left, right = pair.get("left"), pair.get("right")
            if not left or not right or target in {left, right}:
                continue
            graph[left].add(right)
            graph[right].add(left)
        seen, clusters = set(), []
        for start in sorted(graph):
            if start in seen:
                continue
            queue, members = deque([start]), set()
            while queue:
                node = queue.popleft()
                if node in seen:
                    continue
                seen.add(node)
                members.add(node)
                queue.extend(sorted(graph[node] - seen))
            if len(members) >= 2:
                clusters.append({"columns": sorted(members), "size": len(members)})
        return sorted(clusters, key=lambda item: item["size"], reverse=True)

    @staticmethod
    def _cluster_columns(high_corr_pairs: list[dict]) -> list[str]:
        return sorted(set(sum(([pair.get("left"), pair.get("right")] for pair in high_corr_pairs), [])))

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
