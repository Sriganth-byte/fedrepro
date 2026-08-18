import json
import logging
import threading
import time
from datetime import datetime, timezone

import httpx
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.database import SessionLocal
from app.models.entities import AIGeneratedExplanation, AIInsightJob, Dataset, DatasetVersion, Study
from app.services.ai_context_builder import AIContextBuilder
from app.services.ai_explanation_service import AIExplanationService
from app.utilities.hashing import canonical_hash

logger = logging.getLogger(__name__)


class AIInsightJobService:
    task_type = "version_analysis"
    prompt_version = "version-analysis-3.0"
    required_fields = (
        "executive_summary",
        "quality_interpretation",
        "diagnosis_interpretation",
        "semantic_change_interpretation",
        "risk_interpretation",
        "recommended_actions",
    )
    _model_cache: list[str] | None = None
    _model_cache_lock = threading.Lock()
    _worker_gate: threading.BoundedSemaphore | None = None
    _worker_gate_size: int | None = None

    def __init__(self, db: Session):
        self.db = db
        self.settings = get_settings()

    def status_for_version(self, version_id: int) -> dict | None:
        job = self.db.query(AIInsightJob).filter(
            AIInsightJob.version_id == version_id,
            AIInsightJob.task_type == self.task_type,
        ).order_by(AIInsightJob.queued_at.desc()).first()
        return self.job_payload(job) if job else None

    def cached_version_analysis(self, study_id: int, version_id: int) -> AIGeneratedExplanation | None:
        context, evidence_hash, _context_hash = self._context_and_hashes(study_id, version_id)
        record = self.db.query(AIGeneratedExplanation).filter(
            AIGeneratedExplanation.study_id == study_id,
            AIGeneratedExplanation.explanation_type == self.task_type,
            AIGeneratedExplanation.source_entity_id == version_id,
            AIGeneratedExplanation.source_evidence_hash == evidence_hash,
            AIGeneratedExplanation.prompt_version == self.prompt_version,
        ).order_by(AIGeneratedExplanation.created_at.desc()).first()
        if record and not AIExplanationService.is_fallback_content(record.content):
            return record
        return None

    def enqueue_version_analysis(self, study_id: int, version_id: int, priority: int = 5, force: bool = False) -> dict:
        context, evidence_hash, context_hash = self._context_and_hashes(study_id, version_id)
        cached = None if force else self.cached_version_analysis(study_id, version_id)
        if cached:
            return {"status": "completed", "cached": True, "record": self.record_payload(cached)}
        active = None if force else self.db.query(AIInsightJob).filter(
            AIInsightJob.version_id == version_id,
            AIInsightJob.task_type == self.task_type,
            AIInsightJob.evidence_hash == evidence_hash,
            AIInsightJob.context_hash == context_hash,
            AIInsightJob.prompt_version == self.prompt_version,
            AIInsightJob.status.in_(("queued", "running")),
        ).order_by(AIInsightJob.queued_at.desc()).first()
        if active:
            return {"status": active.status, "cached": False, "job": self.job_payload(active)}
        pending = self.db.query(AIInsightJob).filter(AIInsightJob.status.in_(("queued", "running"))).count()
        if pending >= self.settings.ai_max_pending_jobs:
            return {"status": "limited", "cached": False, "message": "AI job queue is full"}
        job = AIInsightJob(
            version_id=version_id,
            study_id=study_id,
            task_type=self.task_type,
            priority=priority,
            evidence_hash=evidence_hash,
            context_hash=context_hash,
            prompt_version=self.prompt_version,
            model_name=self._preferred_model(),
            status="queued",
        )
        self.db.add(job)
        self.db.commit()
        self.db.refresh(job)
        if self.settings.ai_enabled and self.settings.ai_prefetch_enabled:
            threading.Thread(target=self.run_job_by_id, args=(job.id,), name=f"ai-insight-job-{job.id}", daemon=True).start()
        return {"status": job.status, "cached": False, "job": self.job_payload(job), "context": context}

    def run_job_by_id(self, job_id: int) -> None:
        db = SessionLocal()
        try:
            self.__class__(db).run_job(job_id)
        except Exception as exc:
            db.rollback()
            logger.info("AI insight background job %s stopped: %s", job_id, exc)
        finally:
            db.close()

    def run_job(self, job_id: int) -> bool:
        job = self.db.get(AIInsightJob, job_id)
        if not job or job.status == "completed":
            return False
        gate = self._worker_gate_for(self.settings.ai_max_workers)
        with gate:
            start = time.perf_counter()
            job.status = "running"
            job.started_at = datetime.now(timezone.utc)
            job.error_message = None
            self.db.commit()
            last_error = None
            for _ in range(max(1, self.settings.ai_job_max_attempts)):
                job.attempts += 1
                self.db.commit()
                try:
                    study = self.db.get(Study, job.study_id)
                    version = self.db.get(DatasetVersion, job.version_id)
                    if not study or not version:
                        raise ValueError("AI job source version no longer exists")
                    context = AIContextBuilder(self.db).version_analysis(study, version)
                    content = self._generate_structured_analysis(context, job.model_name or self._preferred_model())
                    record = AIGeneratedExplanation(
                        study_id=job.study_id,
                        explanation_type=self.task_type,
                        source_entity_type=self.task_type,
                        source_entity_id=job.version_id,
                        model=job.model_name or self.settings.ollama_model,
                        prompt_version=self.prompt_version,
                        source_evidence_hash=job.evidence_hash,
                        content=json.dumps(content, ensure_ascii=False),
                    )
                    self.db.add(record)
                    job.status = "completed"
                    job.completed_at = datetime.now(timezone.utc)
                    job.execution_time_seconds = round(time.perf_counter() - start, 3)
                    self.db.commit()
                    return True
                except Exception as exc:
                    last_error = exc
                    logger.info("AI insight job %s attempt failed: %s", job.id, exc)
            job.status = "failed"
            job.completed_at = datetime.now(timezone.utc)
            job.execution_time_seconds = round(time.perf_counter() - start, 3)
            job.error_message = str(last_error)[:2000] if last_error else "Unknown AI failure"
            self.db.commit()
            return False

    def _generate_structured_analysis(self, context: dict, model: str) -> dict:
        prompt = (
            "You are FedRepro's evidence-bound AI analyst. Use only this compact deterministic evidence. "
            "Do not calculate or modify MLRS, LRS, SCM, DSI, VRS, findings, fingerprints, profiles, diagnosis, or variant ranking. "
            "Return only valid JSON with these string/list fields: executive_summary, quality_interpretation, "
            "diagnosis_interpretation, semantic_change_interpretation, risk_interpretation, recommended_actions. "
            "Keep the whole answer concise and practical.\nEvidence:\n"
            f"{json.dumps(context, default=str)}"
        )
        payload = {
            "model": model,
            "prompt": prompt,
            "stream": False,
            "keep_alive": "10m",
            "format": "json",
            "options": {
                "temperature": 0.1,
                "num_predict": self.settings.ai_version_analysis_max_tokens,
            },
        }
        response = httpx.post(
            f"{self.settings.ollama_base_url.rstrip('/')}/api/generate",
            json=payload,
            timeout=httpx.Timeout(self.settings.ai_job_timeout_seconds, connect=10),
        )
        response.raise_for_status()
        parsed = json.loads(response.json()["response"])
        if not isinstance(parsed, dict):
            raise ValueError("Ollama did not return a JSON object")
        for field in self.required_fields:
            if field not in parsed:
                raise ValueError(f"Ollama omitted {field}")
        return parsed

    def _context_and_hashes(self, study_id: int, version_id: int) -> tuple[dict, str, str]:
        study = self.db.get(Study, study_id)
        version = self.db.get(DatasetVersion, version_id)
        if not study or not version:
            raise ValueError("Version analysis source not found")
        dataset = self.db.get(Dataset, version.dataset_id)
        if not dataset or dataset.study_id != study.id:
            raise ValueError("Version analysis source does not belong to the study")
        context = AIContextBuilder(self.db).version_analysis(study, version)
        return context, canonical_hash(context), canonical_hash({"prompt_version": self.prompt_version, "context": context})

    def _preferred_model(self) -> str:
        models = self._preferred_models()
        return models[0] if models else self.settings.ollama_model

    def _preferred_models(self) -> list[str]:
        if not self.settings.ai_enabled:
            return [self.settings.ollama_model]
        with self._model_cache_lock:
            if self._model_cache is not None:
                return self._model_cache
            names = [self.settings.ollama_model]
            try:
                response = httpx.get(f"{self.settings.ollama_base_url.rstrip('/')}/api/tags", timeout=3)
                response.raise_for_status()
                names = [item.get("name") or item.get("model") for item in response.json().get("models", [])]
                names = [name for name in names if name]
            except Exception as exc:
                logger.info("Could not list Ollama models; using configured model: %s", exc)
            self._model_cache = sorted(dict.fromkeys(names), key=self._model_rank) or [self.settings.ollama_model]
            return self._model_cache

    @classmethod
    def _worker_gate_for(cls, size: int) -> threading.BoundedSemaphore:
        size = max(1, int(size or 1))
        if cls._worker_gate is None or cls._worker_gate_size != size:
            cls._worker_gate = threading.BoundedSemaphore(size)
            cls._worker_gate_size = size
        return cls._worker_gate

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

    @staticmethod
    def record_payload(record: AIGeneratedExplanation | None) -> dict | None:
        if not record:
            return None
        structured = None
        try:
            structured = json.loads(record.content)
        except json.JSONDecodeError:
            pass
        return {
            "id": record.id,
            "type": record.explanation_type,
            "model": record.model,
            "prompt_version": record.prompt_version,
            "source_evidence_hash": record.source_evidence_hash,
            "content": record.content,
            "structured_content": structured,
            "created_at": record.created_at,
        }

    @staticmethod
    def job_payload(job: AIInsightJob | None) -> dict | None:
        if not job:
            return None
        return {
            "id": job.id,
            "version_id": job.version_id,
            "study_id": job.study_id,
            "task_type": job.task_type,
            "priority": job.priority,
            "status": job.status,
            "attempts": job.attempts,
            "evidence_hash": job.evidence_hash,
            "context_hash": job.context_hash,
            "prompt_version": job.prompt_version,
            "model_name": job.model_name,
            "queued_at": job.queued_at,
            "started_at": job.started_at,
            "completed_at": job.completed_at,
            "execution_time_seconds": job.execution_time_seconds,
            "error_message": job.error_message,
        }
