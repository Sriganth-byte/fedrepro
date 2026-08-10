from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.entities import ActivityLog, Dataset, DatasetVersion, DiagnosisReport, Study


class ReportingService:
    def __init__(self, db: Session):
        self.db = db

    def dashboard(self, owner_id: int) -> dict:
        studies = self.db.query(Study.id).filter(Study.owner_id == owner_id).subquery()
        dataset_ids = self.db.query(Dataset.id).filter(Dataset.study_id.in_(studies)).subquery()
        version_ids = self.db.query(DatasetVersion.id).filter(DatasetVersion.dataset_id.in_(dataset_ids)).subquery()
        recent_diagnoses = self.db.query(DiagnosisReport, DatasetVersion).join(DatasetVersion).filter(DiagnosisReport.version_id.in_(version_ids)).order_by(DiagnosisReport.created_at.desc()).limit(6).all()
        activity = self.db.query(ActivityLog).filter(ActivityLog.study_id.in_(studies)).order_by(ActivityLog.created_at.desc()).limit(8).all()
        return {"total_studies": self.db.query(Study).filter(Study.owner_id == owner_id).count(), "total_datasets": self.db.query(Dataset).filter(Dataset.id.in_(dataset_ids)).count(), "total_versions": self.db.query(DatasetVersion).filter(DatasetVersion.id.in_(version_ids)).count(), "high_risk_studies": self.db.query(func.count(func.distinct(Dataset.study_id))).join(DatasetVersion, DatasetVersion.dataset_id == Dataset.id).join(DiagnosisReport, DiagnosisReport.version_id == DatasetVersion.id).filter(Dataset.study_id.in_(studies), DiagnosisReport.mlrs_score >= 60).scalar() or 0, "recent_activity": [{"id": row.id, "action": row.action, "entity_type": row.entity_type, "details": row.details_json, "created_at": row.created_at} for row in activity], "recent_diagnoses": [{"id": report.id, "version_id": version.id, "mlrs_score": report.mlrs_score, "lrs_score": report.lrs_score, "finding_count": len(report.findings_json), "created_at": report.created_at} for report, version in recent_diagnoses]}

    def study_findings(self, study_id: int) -> dict:
        datasets = self.db.query(Dataset).filter(Dataset.study_id == study_id).all()
        rows = []
        for dataset in datasets:
            versions = self.db.query(DatasetVersion).filter(DatasetVersion.dataset_id == dataset.id).order_by(DatasetVersion.version_number).all()
            rows.append({"dataset": {"id": dataset.id, "name": dataset.name}, "versions": [{"id": version.id, "version_number": version.version_number, "file_hash": version.file_hash, "diagnosis": self._diagnosis(version.id)} for version in versions]})
        return {"study_id": study_id, "datasets": rows}

    def _diagnosis(self, version_id: int):
        report = self.db.query(DiagnosisReport).filter(DiagnosisReport.version_id == version_id).first()
        return None if not report else {"mlrs_score": report.mlrs_score, "lrs_score": report.lrs_score, "findings": report.findings_json}


