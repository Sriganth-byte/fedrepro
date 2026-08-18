import logging
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.entities import (
    ActivityLog,
    Dataset,
    DatasetConfiguration,
    DatasetProfileReport,
    DatasetRegistration,
    DatasetVersion,
    DiagnosisReport,
    SemanticDiffReport,
    Study,
)
from app.services.ai_insight_job_service import AIInsightJobService
from app.services.dataset_explanation_report_service import DatasetExplanationReportService
from app.services.dataset_workflow_service import DatasetWorkflowService
from app.services.diagnosis_service import DiagnosisService
from app.services.profiling_service import ProfilingService
from app.services.semantic_diff_service import SemanticDiffService

logger = logging.getLogger(__name__)


class EvidenceWarmupService:
    """Best-effort startup cache warmer for persisted deterministic and AI evidence."""

    def __init__(self, db: Session):
        self.db = db
        self.settings = get_settings()

    def warm_all(self) -> dict:
        summary = {"versions": 0, "diagnosis_generated": 0, "reports_cached": 0, "ai_tasks": 0, "ai_generated": 0, "errors": 0}
        ai_candidates: list[tuple[int, int]] = []
        studies = self.db.query(Study).order_by(Study.id).all()
        for study in studies:
            versions = (
                self.db.query(DatasetVersion)
                .join(Dataset)
                .filter(Dataset.study_id == study.id)
                .order_by(DatasetVersion.id)
                .all()
            )
            for version in versions:
                summary["versions"] += 1
                try:
                    diagnosis = self._ensure_diagnosis(study, version)
                    if diagnosis:
                        summary["diagnosis_generated"] += 1
                    current_diagnosis = self.db.query(DiagnosisReport).filter(DiagnosisReport.version_id == version.id).first()
                    if self._ensure_version_report(study, version):
                        summary["reports_cached"] += 1
                    if self.settings.ai_enabled and self.settings.ai_prefetch_enabled and current_diagnosis:
                        ai_candidates.append((study.id, version.id))
                except Exception as exc:
                    summary["errors"] += 1
                    self.db.rollback()
                    logger.info("Warmup skipped version %s: %s", version.id, exc)
        if self.settings.ai_enabled and self.settings.ai_prefetch_enabled and ai_candidates:
            limited = self._warmup_candidates(ai_candidates)
            service = AIInsightJobService(self.db)
            for study_id, version_id in limited:
                result = service.enqueue_version_analysis(study_id, version_id, priority=8)
                if result.get("job") or result.get("status") in {"queued", "running"}:
                    summary["ai_tasks"] += 1
        logger.info("Evidence warmup complete: %s", summary)
        return summary

    def _ensure_diagnosis(self, study: Study, version: DatasetVersion) -> bool:
        profile = self.db.query(DatasetProfileReport).filter(DatasetProfileReport.version_id == version.id).first()
        diagnosis = self.db.query(DiagnosisReport).filter(DiagnosisReport.version_id == version.id).first()
        semantic = self.db.query(SemanticDiffReport).filter(SemanticDiffReport.current_version_id == version.id).first()
        needs = not profile or not diagnosis or (version.parent_version_id and not semantic)
        stale = bool(
            (profile and profile.profiler_version != ProfilingService.profiler_version)
            or (diagnosis and diagnosis.ruleset_version != DiagnosisService.ruleset_version)
            or (semantic and semantic.ruleset_version != SemanticDiffService.ruleset_version)
        )
        if not needs:
            if not stale:
                return False
        should_recompute = stale or bool(version.parent_version_id and not semantic and diagnosis)
        DatasetWorkflowService(self.db).run_diagnosis(study, None, version.id, recompute=should_recompute, generate_ai=False)
        return True

    def _ensure_version_report(self, study: Study, version: DatasetVersion) -> bool:
        existing = self.db.query(ActivityLog).filter(
            ActivityLog.action == "dataset.version_report",
            ActivityLog.entity_type == "dataset_version",
            ActivityLog.entity_id == version.id,
        ).first()
        if existing:
            return False
        dataset = self.db.get(Dataset, version.dataset_id)
        registration = self.db.get(DatasetRegistration, version.registration_id)
        configuration = self.db.get(DatasetConfiguration, version.configuration_id)
        profile = self.db.query(DatasetProfileReport).filter(DatasetProfileReport.version_id == version.id).first()
        diagnosis = self.db.query(DiagnosisReport).filter(DiagnosisReport.version_id == version.id).first()
        semantic = self.db.query(SemanticDiffReport).filter(SemanticDiffReport.current_version_id == version.id).first()
        if not dataset or not registration or not configuration:
            return False
        payload = DatasetExplanationReportService.version_report(
            study,
            dataset,
            registration,
            version,
            configuration,
            version.fingerprint,
            profile,
            diagnosis,
            semantic,
        )
        self.db.add(ActivityLog(study_id=study.id, actor_id=None, action="dataset.version_report", entity_type="dataset_version", entity_id=version.id, details_json=payload))
        self.db.commit()
        return True

    def _warmup_candidates(self, candidates: list[tuple[int, int]]) -> list[tuple[int, int]]:
        if self.settings.ai_warmup_mode != "recent":
            return candidates[: self.settings.ai_warmup_max_jobs]
        recent = []
        for study_id in sorted({study_id for study_id, _ in candidates}):
            version_ids = [version_id for candidate_study_id, version_id in candidates if candidate_study_id == study_id]
            recent.extend((study_id, version_id) for version_id in version_ids[-self.settings.ai_warmup_recent_versions:])
        return recent[-self.settings.ai_warmup_max_jobs:]
