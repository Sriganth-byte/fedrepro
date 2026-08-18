from sqlalchemy.orm import Session

from app.models.entities import ActivityLog, Dataset, DatasetProfileReport, DatasetVersion, DiagnosisReport, SemanticDiffReport, Study, VariantGenerationRecord
from app.utilities.hashing import canonical_hash


class InstantInsightService:
    action = "dataset.instant_insight"
    insight_version = "instant-insight-1.0"

    def __init__(self, db: Session):
        self.db = db

    def ensure_for_version(self, study: Study, version: DatasetVersion) -> dict:
        payload = self.build(study, version)
        evidence_hash = canonical_hash(payload.get("evidence", {}))
        existing = self.latest(version.id)
        if existing and existing.details_json.get("evidence_hash") == evidence_hash:
            return existing.details_json
        record = ActivityLog(
            study_id=study.id,
            actor_id=None,
            action=self.action,
            entity_type="dataset_version",
            entity_id=version.id,
            details_json={**payload, "evidence_hash": evidence_hash},
        )
        self.db.add(record)
        self.db.flush()
        return record.details_json

    def latest(self, version_id: int):
        return self.db.query(ActivityLog).filter(
            ActivityLog.action == self.action,
            ActivityLog.entity_type == "dataset_version",
            ActivityLog.entity_id == version_id,
        ).order_by(ActivityLog.created_at.desc()).first()

    def latest_payload(self, version_id: int) -> dict | None:
        row = self.latest(version_id)
        return row.details_json if row else None

    def build(self, study: Study, version: DatasetVersion) -> dict:
        dataset = self.db.get(Dataset, version.dataset_id)
        profile = self.db.query(DatasetProfileReport).filter(DatasetProfileReport.version_id == version.id).first()
        diagnosis = self.db.query(DiagnosisReport).filter(DiagnosisReport.version_id == version.id).first()
        semantic = self.db.query(SemanticDiffReport).filter(SemanticDiffReport.current_version_id == version.id).first()
        variant = self.db.query(VariantGenerationRecord).filter(VariantGenerationRecord.variant_version_id == version.id).order_by(VariantGenerationRecord.created_at.desc()).first()
        summary = (profile.report_json or {}).get("summary", {}) if profile else {}
        findings = diagnosis.findings_json if diagnosis else []
        high = [item for item in findings if item.get("severity") in {"critical", "high"}]
        top_findings = [item.get("issue") or item.get("code") for item in findings[:5]]
        quality_parts = [
            f"{summary.get('missing_cells', 0)} missing cells",
            f"{summary.get('duplicate_rows', 0)} duplicate rows",
            f"{summary.get('numeric_columns', 'N/A')} numeric features",
            f"{summary.get('categorical_columns', 'N/A')} categorical features",
        ]
        semantic_text = (
            f"SCM {semantic.scm_score} and DSI {semantic.dsi_score} versus parent version."
            if semantic else "Baseline version; SCM and DSI are not applicable."
        )
        if version.parent_version_id and not semantic:
            semantic_text = "Semantic comparison is not yet persisted for this child version."
        actions = []
        if diagnosis:
            if diagnosis.mlrs_score >= 45:
                actions.append("Review readiness findings before model experimentation.")
            if diagnosis.lrs_score >= 20:
                actions.append("Inspect leakage-related evidence before training.")
        if semantic:
            actions.append("Check whether parent-to-child semantic movement was intentional.")
        if variant:
            actions.append("Compare variant VRS and MLRS movement before promoting to experiments.")
        if not actions:
            actions.append("Continue with reproducibility review and export the version bundle when needed.")
        return {
            "insight_type": "instant_version_insight",
            "insight_version": self.insight_version,
            "version_id": version.id,
            "study_id": study.id,
            "summary": f"{dataset.name if dataset else 'Dataset'} V{version.version_number}: MLRS {self._metric(diagnosis.mlrs_score if diagnosis else None)}, LRS {self._metric(diagnosis.lrs_score if diagnosis else None)}. {semantic_text}",
            "quality_interpretation": f"Profile evidence records {', '.join(quality_parts)}.",
            "diagnosis_interpretation": (
                f"{len(findings)} finding(s), including {len(high)} high-priority finding(s)."
                if diagnosis else "Diagnosis evidence is not available yet."
            ),
            "semantic_change_interpretation": semantic_text,
            "risk_interpretation": top_findings or ["No deterministic finding crossed reporting thresholds."],
            "recommended_actions": actions,
            "evidence": {
                "profile_id": profile.id if profile else None,
                "diagnosis_id": diagnosis.id if diagnosis else None,
                "semantic_id": semantic.id if semantic else None,
                "variant_record_id": variant.id if variant else None,
                "mlrs_score": diagnosis.mlrs_score if diagnosis else None,
                "lrs_score": diagnosis.lrs_score if diagnosis else None,
                "scm_score": semantic.scm_score if semantic else None,
                "dsi_score": semantic.dsi_score if semantic else None,
                "vrs_score": variant.vrs_score if variant else None,
                "findings": findings,
            },
        }

    @staticmethod
    def _metric(value) -> str:
        return "N/A" if value is None else f"{float(value):.1f}"
