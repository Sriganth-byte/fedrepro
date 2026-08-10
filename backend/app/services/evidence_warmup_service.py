import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from itertools import cycle

import httpx
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.database import SessionLocal
from app.models.entities import (
    AIGeneratedExplanation,
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
from app.services.ai_explanation_service import AIExplanationService
from app.services.dataset_explanation_report_service import DatasetExplanationReportService
from app.services.dataset_workflow_service import DatasetWorkflowService
from app.services.diagnosis_service import DiagnosisService
from app.services.profiling_service import ProfilingService
from app.services.semantic_diff_service import SemanticDiffService
from app.utilities.hashing import canonical_hash

logger = logging.getLogger(__name__)


class EvidenceWarmupService:
    """Best-effort startup cache warmer for persisted deterministic and AI evidence."""

    max_ai_workers = 3

    def __init__(self, db: Session):
        self.db = db
        self.settings = get_settings()

    def warm_all(self) -> dict:
        summary = {"versions": 0, "diagnosis_generated": 0, "reports_cached": 0, "ai_tasks": 0, "ai_generated": 0, "errors": 0}
        ai_tasks: list[tuple[int, int, str, int | None]] = []
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
                    if self.settings.ai_enabled and current_diagnosis:
                        ai_tasks.extend(self._missing_ai_tasks(study.id, version.id, current_diagnosis.id))
                except Exception as exc:
                    summary["errors"] += 1
                    self.db.rollback()
                    logger.info("Warmup skipped version %s: %s", version.id, exc)
        if self.settings.ai_enabled and ai_tasks:
            summary["ai_tasks"] = len(ai_tasks)
            summary["ai_generated"] = self._run_ai_tasks(ai_tasks)
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

    def _missing_ai_tasks(self, study_id: int, version_id: int, diagnosis_id: int) -> list[tuple[int, int, str, int | None]]:
        from app.api.routes.ai import resolve_evidence

        study = self.db.get(Study, study_id)
        tasks: list[tuple[int, int, str, int | None]] = []
        for explanation_type, source_id in (
            ("diagnosis_report_interpretation", diagnosis_id),
            ("dataset_executive_summary", version_id),
            ("dataset_explanation_report", version_id),
            ("version_analysis", version_id),
        ):
            evidence_source_id = version_id if explanation_type == "diagnosis_report_interpretation" else source_id
            try:
                evidence = resolve_evidence(self.db, study, explanation_type, evidence_source_id)
            except Exception as exc:
                logger.info("Warmup cannot resolve %s for version %s: %s", explanation_type, version_id, exc)
                continue
            if not self._has_cached_ai(study_id, explanation_type, source_id, evidence):
                tasks.append((study_id, source_id, explanation_type, version_id))
        for semantic in self.db.query(SemanticDiffReport).filter(SemanticDiffReport.current_version_id == version_id).all():
            for explanation_type in ("semantic_metrics", "semantic_diff_interpretation"):
                evidence = resolve_evidence(self.db, study, explanation_type, semantic.id)
                if not self._has_cached_ai(study_id, explanation_type, semantic.id, evidence):
                    tasks.append((study_id, semantic.id, explanation_type, version_id))
        return tasks

    def _has_cached_ai(self, study_id: int, explanation_type: str, source_entity_id: int, evidence: dict) -> bool:
        evidence_hash = canonical_hash(evidence)
        record = self.db.query(AIGeneratedExplanation).filter(
            AIGeneratedExplanation.study_id == study_id,
            AIGeneratedExplanation.explanation_type == explanation_type,
            AIGeneratedExplanation.source_entity_id == source_entity_id,
            AIGeneratedExplanation.source_evidence_hash == evidence_hash,
            AIGeneratedExplanation.prompt_version == AIExplanationService.prompt_version,
        ).order_by(AIGeneratedExplanation.created_at.desc()).first()
        return bool(record and not AIExplanationService.is_fallback_content(record.content))

    def _run_ai_tasks(self, tasks: list[tuple[int, int, str, int | None]]) -> int:
        models = self._preferred_ollama_models()
        generated = 0
        with ThreadPoolExecutor(max_workers=min(self.max_ai_workers, len(models), len(tasks))) as executor:
            futures = []
            model_cycle = cycle(models)
            for task in tasks:
                futures.append(executor.submit(self._run_one_ai_task, task, next(model_cycle)))
            for future in as_completed(futures):
                if future.result():
                    generated += 1
        return generated

    def _run_one_ai_task(self, task: tuple[int, int, str, int | None], model: str) -> bool:
        study_id, source_id, explanation_type, version_id = task
        db = SessionLocal()
        try:
            from app.api.routes.ai import resolve_evidence

            study = db.get(Study, study_id)
            evidence_id = version_id if explanation_type == "diagnosis_report_interpretation" and version_id else source_id
            evidence = resolve_evidence(db, study, explanation_type, evidence_id)
            if self._has_cached_ai_in_session(db, study_id, explanation_type, source_id, evidence):
                return False
            AIExplanationService(db, model=model).explain(study, explanation_type, source_id, evidence)
            return True
        except Exception as exc:
            logger.info("Warmup AI task skipped (%s/%s): %s", explanation_type, source_id, exc)
            return False
        finally:
            db.close()

    @staticmethod
    def _has_cached_ai_in_session(db: Session, study_id: int, explanation_type: str, source_entity_id: int, evidence: dict) -> bool:
        evidence_hash = canonical_hash(evidence)
        record = db.query(AIGeneratedExplanation).filter(
            AIGeneratedExplanation.study_id == study_id,
            AIGeneratedExplanation.explanation_type == explanation_type,
            AIGeneratedExplanation.source_entity_id == source_entity_id,
            AIGeneratedExplanation.source_evidence_hash == evidence_hash,
            AIGeneratedExplanation.prompt_version == AIExplanationService.prompt_version,
        ).order_by(AIGeneratedExplanation.created_at.desc()).first()
        return bool(record and not AIExplanationService.is_fallback_content(record.content))

    def _preferred_ollama_models(self) -> list[str]:
        names = [self.settings.ollama_model]
        try:
            response = httpx.get(f"{self.settings.ollama_base_url.rstrip('/')}/api/tags", timeout=3)
            response.raise_for_status()
            payload = response.json()
            names = [item.get("name") or item.get("model") for item in payload.get("models", [])]
            names = [name for name in names if name]
        except Exception as exc:
            logger.info("Could not list Ollama models; using configured model: %s", exc)
        ranked = sorted(dict.fromkeys(names), key=self._model_rank)
        return ranked[: self.max_ai_workers] or [self.settings.ollama_model]

    @staticmethod
    def _model_rank(name: str) -> tuple[int, int, str]:
        lowered = name.lower()
        preferred = ("qwen2.5", "qwen2", "llama3.2", "phi3", "gemma2", "mistral", "llama3.1")
        family = next((index for index, marker in enumerate(preferred) if marker in lowered), len(preferred))
        size = 99
        for marker, value in (("0.5b", 1), ("1b", 2), ("1.5b", 3), ("2b", 4), ("3b", 5), ("4b", 6), ("7b", 8), ("8b", 9), ("mini", 4), ("small", 5)):
            if marker in lowered:
                size = value
                break
        return (family, size, lowered)
