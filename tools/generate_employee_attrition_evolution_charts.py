from __future__ import annotations

import csv
import html
import json
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from app.services.diagnosis_service import DiagnosisService
from app.services.profiling_service import ProfilingService
from app.services.semantic_diff_service import SemanticDiffService


DATASETS = [
    ("V1", "Raw Baseline", Path(r"C:\Users\Subiksha\Downloads\employee_attrition_V1_raw_baseline.csv")),
    ("V2", "Quality Improved", Path(r"C:\Users\Subiksha\Downloads\employee_attrition_V2_quality_improved.csv")),
    ("V3", "ML Ready", Path(r"C:\Users\Subiksha\Downloads\employee_attrition_V3_ml_ready.csv")),
    ("V4", "Feature Engineered", Path(r"C:\Users\Subiksha\Downloads\employee_attrition_V4_feature_engineered.csv")),
]
TARGET_COLUMN = "Attrition"
TASK_TYPE = "classification"
OUTPUT_DIR = ROOT / "reports" / "employee_attrition_evolution_charts"


def clamp(value: float, low: float = 0.0, high: float = 100.0) -> float:
    return max(low, min(high, float(value)))


def fmt(value, digits: int = 2) -> str:
    if value is None:
        return "N/A"
    return f"{float(value):.{digits}f}".rstrip("0").rstrip(".")


def categorical_consistency(frame: pd.DataFrame) -> dict:
    total = 0
    inconsistent = 0
    columns = []
    for column in frame.columns:
        if column == TARGET_COLUMN or pd.api.types.is_numeric_dtype(frame[column]):
            continue
        values = frame[column].dropna().astype(str)
        total += len(values)
        groups = {}
        for value in values:
            key = " ".join(value.strip().lower().replace("_", " ").replace("-", " ").split())
            groups.setdefault(key, set()).add(value)
        variants = {key: sorted(raw) for key, raw in groups.items() if len(raw) > 1}
        if variants:
            raw_values = {item for group in variants.values() for item in group}
            affected = int(values.isin(raw_values).sum())
            inconsistent += affected
            columns.append({"column": column, "affected_cells": affected, "variants": variants})
    return {"ratio": inconsistent / max(total, 1), "columns": columns}


def quality_scores(profile: dict, diagnosis: dict, frame: pd.DataFrame) -> dict:
    summary = profile["summary"]
    numeric_features = [
        item for item in profile["columns"]
        if item["role"] != "target" and pd.api.types.is_numeric_dtype(frame[item["name"]])
    ]
    outlier_count = sum(item.get("outlier_count", 0) for item in numeric_features)
    outlier_denominator = max(len(frame) * max(len(numeric_features), 1), 1)
    consistency = categorical_consistency(frame)
    class_distribution = profile.get("task_profile", {}).get("class_distribution") or {}
    minority_pct = 0.0
    if class_distribution:
        minority_pct = min(class_distribution.values()) / max(sum(class_distribution.values()), 1) * 100
    constant_count = sum(1 for item in profile["columns"] if item.get("unique_count", 0) <= 1)
    categorical_features = [
        item for item in profile["columns"]
        if item["role"] != "target" and not pd.api.types.is_numeric_dtype(frame[item["name"]])
    ]
    high_cardinality_count = sum(
        1 for item in categorical_features
        if item.get("unique_ratio", 0) >= 0.5 and item.get("unique_count", 0) >= 20
    )
    invalid_target = 0
    if TARGET_COLUMN in frame.columns:
        valid = {"yes", "no"}
        invalid_target = int((~frame[TARGET_COLUMN].dropna().astype(str).str.strip().str.lower().isin(valid)).sum())
    target_total = max(int(frame[TARGET_COLUMN].notna().sum()), 1) if TARGET_COLUMN in frame.columns else 1
    return {
        "Completeness": round(clamp(100 - summary["missing_ratio"] * 100), 2),
        "Uniqueness": round(clamp(100 - summary["duplicate_ratio"] * 100), 2),
        "Consistency": round(clamp(100 - consistency["ratio"] * 100), 2),
        "Outlier Health": round(clamp(100 - outlier_count / outlier_denominator * 100), 2),
        "Class Balance": round(clamp(minority_pct * 2), 2),
        "Leakage Safety": round(clamp(100 - diagnosis["lrs_score"]), 2),
        "Schema Quality": round(clamp(100 - (constant_count / max(summary["column_count"], 1) * 50) - (high_cardinality_count / max(summary["column_count"], 1) * 30)), 2),
        "Validity": round(clamp(100 - invalid_target / target_total * 100), 2),
    }


def analyze() -> dict:
    profiler = ProfilingService()
    diagnoser = DiagnosisService()
    semantic = SemanticDiffService()
    frames = []
    versions = []
    transitions = []
    config = {
        "target_column": TARGET_COLUMN,
        "primary_metric": "accuracy",
        "validation_strategy": "stratified_holdout",
        "feature_selection_mode": "all",
        "selected_features": [],
        "scaling_strategy": "none",
    }
    for index, (version, name, path) in enumerate(DATASETS, start=1):
        if not path.exists():
            raise FileNotFoundError(path)
        frame = pd.read_csv(path)
        if TARGET_COLUMN not in frame.columns:
            raise ValueError(f"{path.name} does not contain target column {TARGET_COLUMN}")
        target_values = set(frame[TARGET_COLUMN].dropna().astype(str).str.strip())
        if not target_values.issubset({"Yes", "No"}):
            raise ValueError(f"{path.name} has unexpected target values: {sorted(target_values)}")
        previous_frame = frames[-1] if frames else None
        semantic_payload = semantic.compare(previous_frame, frame, TARGET_COLUMN) if previous_frame is not None else None
        profile = profiler.profile(frame, TASK_TYPE, config)
        diagnosis = diagnoser.diagnose(
            profile,
            semantic_payload,
            {"source_version_id": index - 1 if index > 1 else None, "version_number": index, "version_notes": name},
            config,
        )
        quality = quality_scores(profile, diagnosis, frame)
        numeric_features = [
            item for item in profile["columns"]
            if item["role"] != "target" and pd.api.types.is_numeric_dtype(frame[item["name"]])
        ]
        outlier_count = sum(item.get("outlier_count", 0) for item in numeric_features)
        class_distribution = profile["task_profile"]["class_distribution"]
        versions.append({
            "version": version,
            "name": name,
            "rows": profile["summary"]["row_count"],
            "columns": profile["summary"]["column_count"],
            "missing_pct": round(profile["summary"]["missing_ratio"] * 100, 2),
            "duplicate_pct": round(profile["summary"]["duplicate_ratio"] * 100, 2),
            "outlier_pct": round(outlier_count / max(len(frame) * max(len(numeric_features), 1), 1) * 100, 2),
            "class_distribution": class_distribution,
            "minority_class_pct": round(min(class_distribution.values()) / max(sum(class_distribution.values()), 1) * 100, 2),
            "mlrs": diagnosis["mlrs_score"],
            "lrs": diagnosis["lrs_score"],
            "findings": len(diagnosis["findings"]),
            "quality": quality,
            "leakage_risk_features": sorted({
                col
                for detail in diagnosis["score_breakdown"]["component_details"]["lrs"].values()
                for col in detail.get("columns", [])
                if col != TARGET_COLUMN
            }),
        })
        if semantic_payload:
            report = semantic_payload["report"]
            transitions.append({
                "label": f"{DATASETS[index - 2][0]} -> {version}",
                "scm": semantic_payload["scm_score"],
                "dsi": semantic_payload["dsi_score"],
                "columns_added": len(report["columns_added"]),
                "columns_removed": len(report["columns_removed"]),
                "missingness_change_pct": round(report["missing_ratio_change"] * 100, 3),
            })
        frames.append(frame)
    for previous, current in zip([None] + versions[:-1], versions):
        current["mlrs_delta"] = None if previous is None else round(current["mlrs"] - previous["mlrs"], 2)
        current["lrs_delta"] = None if previous is None else round(current["lrs"] - previous["lrs"], 2)
    return {"versions": versions, "transitions": transitions, "variants": []}


def svg_line_chart(title: str, items: list[dict], key: str, y_label: str, color: str) -> str:
    width, height = 920, 430
    left, right, top, bottom = 78, 36, 58, 70
    plot_w, plot_h = width - left - right, height - top - bottom
    values = [float(item[key]) for item in items]
    y_max = max(100, max(values) * 1.1)
    points = []
    for index, item in enumerate(items):
        x = left + index * (plot_w / max(len(items) - 1, 1))
        y = top + plot_h - (float(item[key]) / y_max) * plot_h
        points.append((x, y, item))
    polyline = " ".join(f"{x:.1f},{y:.1f}" for x, y, _ in points)
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
        '<rect width="100%" height="100%" fill="#ffffff"/>',
        f'<text x="{left}" y="32" font-family="Inter, Arial" font-size="22" font-weight="700" fill="#111827">{html.escape(title)}</text>',
        f'<text x="20" y="{top + plot_h / 2}" transform="rotate(-90 20 {top + plot_h / 2})" font-family="Inter, Arial" font-size="13" fill="#475569">{html.escape(y_label)}</text>',
    ]
    for tick in range(0, 101, 20):
        y = top + plot_h - (tick / y_max) * plot_h
        parts.append(f'<line x1="{left}" x2="{width - right}" y1="{y:.1f}" y2="{y:.1f}" stroke="#e5e7eb"/>')
        parts.append(f'<text x="{left - 12}" y="{y + 4:.1f}" text-anchor="end" font-family="Inter, Arial" font-size="11" fill="#64748b">{tick}</text>')
    parts.append(f'<polyline points="{polyline}" fill="none" stroke="{color}" stroke-width="3"/>')
    for x, y, item in points:
        label = f'{item["version"]} - {item["name"]}'
        delta = "baseline" if item.get(f"{key}_delta") is None else f'{item[f"{key}_delta"]:+.2f}'
        parts.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="5" fill="{color}"><title>{html.escape(label)}&#10;{key.upper()}: {fmt(item[key])}&#10;Change: {delta}</title></circle>')
        parts.append(f'<text x="{x:.1f}" y="{height - 38}" text-anchor="middle" font-family="Inter, Arial" font-size="12" fill="#334155">{item["version"]}</text>')
        parts.append(f'<text x="{x:.1f}" y="{y - 12:.1f}" text-anchor="middle" font-family="Inter, Arial" font-size="12" font-weight="700" fill="#111827">{fmt(item[key])}</text>')
    parts.append("</svg>")
    return "\n".join(parts)


def svg_bar_chart(title: str, items: list[dict], key: str, y_label: str, color: str) -> str:
    width, height = 920, 430
    left, right, top, bottom = 78, 36, 58, 74
    plot_w, plot_h = width - left - right, height - top - bottom
    y_max = max(100, max([float(item[key]) for item in items] or [0]) * 1.1)
    bar_w = plot_w / max(len(items), 1) * 0.56
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
        '<rect width="100%" height="100%" fill="#ffffff"/>',
        f'<text x="{left}" y="32" font-family="Inter, Arial" font-size="22" font-weight="700" fill="#111827">{html.escape(title)}</text>',
        f'<text x="20" y="{top + plot_h / 2}" transform="rotate(-90 20 {top + plot_h / 2})" font-family="Inter, Arial" font-size="13" fill="#475569">{html.escape(y_label)}</text>',
    ]
    for tick in range(0, 101, 20):
        y = top + plot_h - (tick / y_max) * plot_h
        parts.append(f'<line x1="{left}" x2="{width - right}" y1="{y:.1f}" y2="{y:.1f}" stroke="#e5e7eb"/>')
        parts.append(f'<text x="{left - 12}" y="{y + 4:.1f}" text-anchor="end" font-family="Inter, Arial" font-size="11" fill="#64748b">{tick}</text>')
    for index, item in enumerate(items):
        x = left + index * (plot_w / max(len(items), 1)) + (plot_w / max(len(items), 1) - bar_w) / 2
        bar_h = (float(item[key]) / y_max) * plot_h
        y = top + plot_h - bar_h
        parts.append(f'<rect x="{x:.1f}" y="{y:.1f}" width="{bar_w:.1f}" height="{bar_h:.1f}" rx="4" fill="{color}"><title>{html.escape(item["label"])}&#10;{key.upper()}: {fmt(item[key])}&#10;DSI: {fmt(item.get("dsi"))}</title></rect>')
        parts.append(f'<text x="{x + bar_w / 2:.1f}" y="{height - 38}" text-anchor="middle" font-family="Inter, Arial" font-size="12" fill="#334155">{html.escape(item["label"])}</text>')
        parts.append(f'<text x="{x + bar_w / 2:.1f}" y="{y - 10:.1f}" text-anchor="middle" font-family="Inter, Arial" font-size="12" font-weight="700" fill="#111827">{fmt(item[key])}</text>')
    parts.append("</svg>")
    return "\n".join(parts)


def svg_quality_heatmap(versions: list[dict]) -> str:
    dimensions = list(versions[0]["quality"].keys())
    cell_w, cell_h = 118, 48
    left, top = 138, 70
    width = left + cell_w * len(dimensions) + 36
    height = top + cell_h * len(versions) + 44
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
        '<rect width="100%" height="100%" fill="#ffffff"/>',
        f'<text x="28" y="34" font-family="Inter, Arial" font-size="22" font-weight="700" fill="#111827">Dataset Quality Distribution Across Versions</text>',
    ]
    for col, dimension in enumerate(dimensions):
        x = left + col * cell_w
        parts.append(f'<text x="{x + cell_w / 2}" y="{top - 18}" text-anchor="middle" font-family="Inter, Arial" font-size="11" font-weight="700" fill="#475569">{html.escape(dimension)}</text>')
    for row, version in enumerate(versions):
        y = top + row * cell_h
        parts.append(f'<text x="{left - 16}" y="{y + 30}" text-anchor="end" font-family="Inter, Arial" font-size="13" font-weight="700" fill="#111827">{version["version"]}</text>')
        for col, dimension in enumerate(dimensions):
            value = version["quality"][dimension]
            hue = int(value * 1.2)
            x = left + col * cell_w
            parts.append(f'<rect x="{x}" y="{y}" width="{cell_w - 4}" height="{cell_h - 4}" rx="4" fill="hsl({hue},72%,42%)"><title>{version["version"]} {dimension}: {fmt(value)}</title></rect>')
            parts.append(f'<text x="{x + (cell_w - 4) / 2}" y="{y + 29}" text-anchor="middle" font-family="Inter, Arial" font-size="13" font-weight="700" fill="#ffffff">{fmt(value)}</text>')
    parts.append("</svg>")
    return "\n".join(parts)


def svg_empty_vrs() -> str:
    return """<svg xmlns="http://www.w3.org/2000/svg" width="920" height="280" viewBox="0 0 920 280">
<rect width="100%" height="100%" fill="#ffffff"/>
<text x="48" y="48" font-family="Inter, Arial" font-size="22" font-weight="700" fill="#111827">Variant Readiness Comparison</text>
<rect x="48" y="82" width="824" height="132" rx="8" fill="#f8fafc" stroke="#e2e8f0"/>
<text x="460" y="142" text-anchor="middle" font-family="Inter, Arial" font-size="16" font-weight="700" fill="#334155">No completed generated variants found</text>
<text x="460" y="170" text-anchor="middle" font-family="Inter, Arial" font-size="13" fill="#64748b">VRS is valid only for generated variants evaluated by FedRepro, not ordinary dataset versions.</text>
</svg>"""


def write_outputs(analytics: dict) -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    charts = {
        "mlrs_across_versions.svg": svg_line_chart("ML Readiness Across Dataset Versions", analytics["versions"], "mlrs", "ML Readiness Score", "#4f46e5"),
        "lrs_across_versions.svg": svg_line_chart("Leakage Risk Across Dataset Versions", analytics["versions"], "lrs", "Leakage Risk Score", "#dc2626"),
        "scm_across_versions.svg": svg_bar_chart("Semantic Change Magnitude Across Dataset Evolution", analytics["transitions"], "scm", "SCM", "#2563eb"),
        "dataset_quality_distribution.svg": svg_quality_heatmap(analytics["versions"]),
        "vrs_comparison.svg": svg_empty_vrs(),
    }
    for filename, content in charts.items():
        (OUTPUT_DIR / filename).write_text(content, encoding="utf-8")
    (OUTPUT_DIR / "analysis_summary.json").write_text(json.dumps(analytics, indent=2), encoding="utf-8")
    with (OUTPUT_DIR / "version_comparison.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["Metric", "V1", "V2", "V3", "V4"])
        for label, key in [
            ("Rows", "rows"),
            ("Columns", "columns"),
            ("Missing %", "missing_pct"),
            ("Duplicate %", "duplicate_pct"),
            ("Outlier %", "outlier_pct"),
            ("MLRS", "mlrs"),
            ("LRS", "lrs"),
            ("Findings", "findings"),
        ]:
            writer.writerow([label] + [item[key] for item in analytics["versions"]])
    links = "\n".join(
        f'<li><a download href="{name}">{name}</a></li>'
        for name in list(charts.keys()) + ["analysis_summary.json", "version_comparison.csv"]
    )
    embedded = "\n".join(f'<section><h2>{name}</h2><img src="{name}" alt="{name}"></section>' for name in charts)
    html_doc = f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>Employee Attrition Evolution Charts</title>
  <style>
    body {{ margin: 32px; font-family: Inter, Arial, sans-serif; color: #111827; background: #f8fafc; }}
    main {{ max-width: 1080px; margin: 0 auto; }}
    section {{ margin: 24px 0; padding: 20px; background: white; border: 1px solid #e2e8f0; border-radius: 8px; }}
    img {{ max-width: 100%; height: auto; display: block; }}
    a {{ color: #2563eb; }}
  </style>
</head>
<body>
<main>
  <h1>Employee Attrition Dataset Evolution Charts</h1>
  <p>All metric values were computed from the four CSV files using FedRepro profiling, diagnosis, and semantic-diff services. VRS is not fabricated for dataset versions.</p>
  <h2>Downloads</h2>
  <ul>{links}</ul>
  {embedded}
</main>
</body>
</html>"""
    (OUTPUT_DIR / "employee_attrition_evolution_report.html").write_text(html_doc, encoding="utf-8")


def main() -> None:
    analytics = analyze()
    write_outputs(analytics)
    print(f"Charts written to: {OUTPUT_DIR}")
    for item in analytics["versions"]:
        print(f"{item['version']}: rows={item['rows']} cols={item['columns']} MLRS={item['mlrs']} LRS={item['lrs']} findings={item['findings']}")
    for item in analytics["transitions"]:
        print(f"{item['label']}: SCM={item['scm']} DSI={item['dsi']}")


if __name__ == "__main__":
    main()
