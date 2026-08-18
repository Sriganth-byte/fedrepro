from pathlib import Path
from uuid import uuid4

from fastapi.testclient import TestClient

from app.core.database import SessionLocal
from app.core.config import get_settings
from app.main import app
from app.models.entities import AIGeneratedExplanation, AIInsightJob, DatasetVersion, DiagnosisReport, User
from app.services.ai_insight_job_service import AIInsightJobService


def _create_diagnosed_version():
    client = TestClient(app)
    email = f"ai-jobs-{uuid4().hex}@example.com"
    token = client.post("/api/auth/register", json={"name": "AI Job Tester", "email": email, "password": "strong-password"}).json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    study = client.post("/api/studies", headers=headers, json={"name": "AI Cache Study", "ml_task": "classification"}).json()
    csv = b"age,score,placed\n20,40,no\n21,50,no\n22,,no\n23,70,yes\n24,80,yes\n"
    registration = client.post(
        f"/api/studies/{study['id']}/datasets/register",
        headers=headers,
        files={"file": ("placement.csv", csv, "text/csv")},
        data={"dataset_name": "AI Cache Dataset"},
    ).json()
    version = client.post(
        f"/api/registrations/{registration['id']}/configure",
        headers=headers,
        json={"target_column": "placed", "primary_metric": "f1_weighted", "validation_strategy": "stratified_holdout", "selected_features": []},
    ).json()
    return client, headers, email, study["id"], version["id"]


def test_ai_insight_cache_dedup_invalidation_and_analysis_fallback(monkeypatch):
    settings = get_settings()
    previous_prefetch = settings.ai_prefetch_enabled
    settings.ai_prefetch_enabled = False
    client, headers, email, study_id, version_id = _create_diagnosed_version()
    created_path = None
    try:
        analysis = client.get(f"/api/versions/{version_id}/analysis", headers=headers)
        assert analysis.status_code == 200, analysis.text
        payload = analysis.json()
        assert payload["instant_insight"]["summary"]
        assert payload["timeline"][0]["semantic_diff"] is None
        assert payload["ai_analysis"] is None

        def fail_if_analysis_calls_ollama(*_args, **_kwargs):
            raise AssertionError("/analysis must not call Ollama")

        monkeypatch.setattr(AIInsightJobService, "_generate_structured_analysis", fail_if_analysis_calls_ollama)
        assert client.get(f"/api/versions/{version_id}/analysis", headers=headers).status_code == 200

        first = client.post(
            f"/api/ai/studies/{study_id}/explain",
            headers=headers,
            json={"explanation_type": "version_analysis", "source_entity_id": version_id},
        ).json()
        second = client.post(
            f"/api/ai/studies/{study_id}/explain",
            headers=headers,
            json={"explanation_type": "version_analysis", "source_entity_id": version_id},
        ).json()
        assert first["job"]["id"] == second["job"]["id"]

        with SessionLocal() as db:
            version = db.get(DatasetVersion, version_id)
            created_path = Path(version.immutable_file_path)
            service = AIInsightJobService(db)
            context, evidence_hash, _ = service._context_and_hashes(study_id, version_id)
            record = AIGeneratedExplanation(
                study_id=study_id,
                explanation_type="version_analysis",
                source_entity_type="version_analysis",
                source_entity_id=version_id,
                model="test-model",
                prompt_version=AIInsightJobService.prompt_version,
                source_evidence_hash=evidence_hash,
                content='{"executive_summary":"cached","quality_interpretation":"quality","diagnosis_interpretation":"diagnosis","semantic_change_interpretation":"semantic","risk_interpretation":"risk","recommended_actions":["act"]}',
            )
            db.add(record)
            db.commit()
            cached = service.enqueue_version_analysis(study_id, version_id)
            assert cached["status"] == "completed"
            diagnosis = db.query(DiagnosisReport).filter(DiagnosisReport.version_id == version_id).first()
            diagnosis.mlrs_score = diagnosis.mlrs_score + 1
            db.commit()
            invalidated = service.enqueue_version_analysis(study_id, version_id)
            assert invalidated["status"] == "queued"
            assert invalidated["job"]["evidence_hash"] != evidence_hash

            failed_job = AIInsightJob(
                version_id=version_id,
                study_id=study_id,
                task_type="version_analysis",
                priority=1,
                evidence_hash=invalidated["job"]["evidence_hash"],
                context_hash=invalidated["job"]["context_hash"],
                prompt_version=AIInsightJobService.prompt_version,
                model_name="test-model",
            )
            db.add(failed_job)
            db.commit()
            db.refresh(failed_job)

            def fail_generation(_self, _context, _model):
                raise RuntimeError("ollama unavailable")

            monkeypatch.setattr(AIInsightJobService, "_generate_structured_analysis", fail_generation)
            assert service.run_job(failed_job.id) is False
            db.refresh(failed_job)
            assert failed_job.status == "failed"

        fallback = client.get(f"/api/versions/{version_id}/analysis", headers=headers)
        assert fallback.status_code == 200, fallback.text
        assert fallback.json()["instant_insight"]["summary"]
    finally:
        with SessionLocal() as db:
            user = db.query(User).filter(User.email == email).first()
            if user:
                db.delete(user)
                db.commit()
        if created_path:
            created_path.unlink(missing_ok=True)
        settings.ai_prefetch_enabled = previous_prefetch
