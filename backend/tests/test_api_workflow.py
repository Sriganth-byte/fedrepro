import json
import tempfile
from pathlib import Path
from uuid import uuid4

from fastapi.testclient import TestClient

from app.api.routes.ai import resolve_evidence
from app.core.database import SessionLocal
from app.main import app
from app.models.entities import DatasetFingerprint, DatasetVersion, DiagnosisReport, SemanticDiffReport, Study, User
from app.services.diagnosis_service import DiagnosisService
from app.services.evidence_warmup_service import EvidenceWarmupService
from app.services.semantic_diff_service import SemanticDiffService


def test_ollama_model_probe_routes_do_not_404():
    client = TestClient(app)
    for path in ("/models", "/v1/models"):
        response = client.get(path)
        assert response.status_code == 200
        payload = response.json()
        assert payload["object"] == "list"
        assert payload["data"][0]["id"]


def test_version_route_reports_api_metadata():
    client = TestClient(app)
    response = client.get("/api/version")
    assert response.status_code == 200
    assert response.json() == {"service": "FedRepro", "version": "1.0.0", "api_prefix": "/api"}


def test_complete_phase_one_api_workflow(tmp_path):
    client = TestClient(app)
    email = f"integration-{uuid4().hex}@example.com"
    token = client.post("/api/auth/register", json={"name": "Integration Researcher", "email": email, "password": "strong-password"}).json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    created_paths = []
    try:
        study_response = client.post("/api/studies", headers=headers, json={"name": "Placement Evidence Study", "ml_task": "classification", "description": "Assess placement dataset evidence.", "problem_objective": "Understand dataset risks.", "intended_use_case": "Future placement classification research."})
        assert study_response.status_code == 201, study_response.text
        study = study_response.json()
        protocol_response = client.get(f"/api/studies/{study['id']}/configuration", headers=headers)
        assert protocol_response.status_code == 200, protocol_response.text
        protocol = protocol_response.json()
        assert protocol["version_number"] == 1
        assert protocol["status"] == "current"
        assert protocol["ml_task"] == "classification"
        assert len(protocol["protocol_hash"]) == 64
        protocol_v2_response = client.post(
            f"/api/studies/{study['id']}/configurations",
            headers=headers,
            json={
                "ml_task": "classification",
                "domain": "student placement",
                "data_quality_focus": "missing scores and leakage",
                "research_objective": "Protocol versioned objective.",
                "research_question": "Does evidence repair improve readiness?",
                "hypothesis": "Repairing score missingness lowers readiness risk.",
                "target_column": "placed",
                "primary_metric": "f1_weighted",
                "baseline_model": "random_forest",
                "validation_strategy": "stratified_holdout",
                "random_seed": 42,
                "feature_scope": "all pre-outcome columns",
                "intended_use_case": "Controlled data-centric ML research.",
                "change_reason": "Integration test protocol refinement",
            },
        )
        assert protocol_v2_response.status_code == 201, protocol_v2_response.text
        protocol_v2 = protocol_v2_response.json()
        assert protocol_v2["version_number"] == 2
        assert protocol_v2["target_column"] == "placed"
        assert protocol_v2["protocol_json"]["schema_version"] == "study-protocol-1.0"
        protocol_history_response = client.get(f"/api/studies/{study['id']}/configurations", headers=headers)
        assert protocol_history_response.status_code == 200, protocol_history_response.text
        history = protocol_history_response.json()
        assert [item["version_number"] for item in history] == [2, 1]
        assert [item["status"] for item in history] == ["current", "archived"]
        update_response = client.patch(f"/api/studies/{study['id']}", headers=headers, json={"problem_objective": "Updated protocol objective.", "intended_use_case": "Updated research use."})
        assert update_response.status_code == 200, update_response.text
        assert update_response.json()["problem_objective"] == "Updated protocol objective."
        updated_protocol_response = client.get(f"/api/studies/{study['id']}/configuration", headers=headers)
        assert updated_protocol_response.status_code == 200, updated_protocol_response.text
        assert updated_protocol_response.json()["version_number"] == 3
        assert updated_protocol_response.json()["research_objective"] == "Updated protocol objective."
        csv = b"age,score,placed\n20,40,no\n21,50,no\n22,,no\n23,70,yes\n24,80,yes\n"
        registration_response = client.post(f"/api/studies/{study['id']}/datasets/register", headers=headers, files={"file": ("placement.csv", csv, "text/csv")}, data={"dataset_name": "Placement Evidence", "version_notes": "Baseline collection"})
        assert registration_response.status_code == 201, registration_response.text
        registration = registration_response.json()
        registration_report_response = client.get(f"/api/registrations/{registration['id']}/explanation-report", headers=headers)
        assert registration_report_response.status_code == 200, registration_report_response.text
        assert registration_report_response.json()["report_type"] == "dataset_registration_explanation"
        version_response = client.post(f"/api/registrations/{registration['id']}/configure", headers=headers, json={"target_column": "placed", "primary_metric": "f1_weighted", "validation_strategy": "stratified_holdout", "selected_features": []})
        assert version_response.status_code == 201, version_response.text
        version = version_response.json()
        assert version["version_number"] == 1
        assert len(version["fingerprint"]["combined_fingerprint"]) == 64
        assert version["semantic_diff"] is None
        repeat_configure_response = client.post(f"/api/registrations/{registration['id']}/configure", headers=headers, json={"target_column": "placed", "primary_metric": "f1_weighted", "validation_strategy": "stratified_holdout", "selected_features": []})
        assert repeat_configure_response.status_code == 201, repeat_configure_response.text
        assert repeat_configure_response.json()["id"] == version["id"]
        dataset_list_response = client.get(f"/api/studies/{study['id']}/datasets", headers=headers)
        assert dataset_list_response.status_code == 200, dataset_list_response.text
        listed_registration = dataset_list_response.json()[0]["registrations"][0]
        assert listed_registration["status"] == "completed"
        profile = client.get(f"/api/versions/{version['id']}/profile", headers=headers)
        diagnosis = client.get(f"/api/versions/{version['id']}/diagnosis", headers=headers)
        assert profile.status_code == 200
        assert diagnosis.status_code == 200
        assert diagnosis.json()["ruleset_version"] == "diagnosis-2.0"
        assert "score_breakdown" in diagnosis.json()
        rerun = client.post(f"/api/versions/{version['id']}/diagnosis/run", headers=headers, params={"recompute": True})
        assert rerun.status_code == 201, rerun.text
        assert rerun.json()["diagnosis"]["version_id"] == version["id"]
        assert rerun.json()["version"]["diagnosis_status"] == "Diagnosed"
        analysis = client.get(f"/api/versions/{version['id']}/analysis", headers=headers)
        assert analysis.status_code == 200, analysis.text
        assert analysis.json()["version"]["id"] == version["id"]
        assert analysis.json()["profile"]["version_id"] == version["id"]
        assert len(analysis.json()["timeline"]) == 1
        assert analysis.json()["timeline"][0]["semantic_diff"] is None
        with SessionLocal() as db:
            row = db.get(DatasetVersion, version["id"])
            version_path = Path(row.immutable_file_path)
            created_paths.append(version_path)

        csv_v2 = b"age,score,placed\n20,40,no\n21,50,no\n22,60,no\n23,70,yes\n24,80,yes\n25,90,yes\n"
        registration_v2_response = client.post(
            f"/api/studies/{study['id']}/datasets/register",
            headers=headers,
            files={"file": ("placement-v2.csv", csv_v2, "text/csv")},
            data={"dataset_name": "Placement Evidence", "version_notes": "Added one row and repaired score"},
        )
        assert registration_v2_response.status_code == 201, registration_v2_response.text
        registration_v2 = registration_v2_response.json()
        version_v2_response = client.post(
            f"/api/registrations/{registration_v2['id']}/configure",
            headers=headers,
            json={"target_column": "placed", "primary_metric": "f1_weighted", "validation_strategy": "stratified_holdout", "selected_features": []},
        )
        assert version_v2_response.status_code == 201, version_v2_response.text
        version_v2 = version_v2_response.json()
        assert version_v2["version_number"] == 2
        with SessionLocal() as db:
            semantic_row = db.query(SemanticDiffReport).filter(SemanticDiffReport.current_version_id == version_v2["id"]).first()
            diagnosis_row = db.query(DiagnosisReport).filter(DiagnosisReport.version_id == version_v2["id"]).first()
            assert semantic_row
            assert diagnosis_row
            semantic_row.ruleset_version = "semantic-legacy"
            semantic_row.scm_score = 0
            semantic_row.dsi_score = 0
            diagnosis_row.ruleset_version = "diagnosis-legacy"
            db.commit()
            warmup = EvidenceWarmupService(db)
            warmup.settings.ai_enabled = False
            summary = warmup.warm_all()
            assert summary["diagnosis_generated"] >= 1
            db.refresh(semantic_row)
            db.refresh(diagnosis_row)
            assert semantic_row.ruleset_version == SemanticDiffService.ruleset_version
            assert diagnosis_row.ruleset_version == DiagnosisService.ruleset_version
            assert semantic_row.scm_score is not None
            assert semantic_row.dsi_score is not None
        analysis_v2 = client.get(f"/api/versions/{version_v2['id']}/analysis", headers=headers)
        assert analysis_v2.status_code == 200, analysis_v2.text
        assert [item["version_number"] for item in analysis_v2.json()["timeline"]] == [1, 2]
        assert analysis_v2.json()["timeline"][0]["semantic_diff"] is None
        assert analysis_v2.json()["timeline"][1]["semantic_diff"]["current_version_id"] == version_v2["id"]
        version_report_response = client.get(f"/api/versions/{version_v2['id']}/explanation-report", headers=headers)
        assert version_report_response.status_code == 200, version_report_response.text
        assert version_report_response.json()["report_type"] == "dataset_version_explanation"
        assert version_report_response.json()["version"]["id"] == version_v2["id"]
        compare_response = client.get(f"/api/versions/{version_v2['id']}/compare", headers=headers, params={"against_version_id": version["id"]})
        assert compare_response.status_code == 200, compare_response.text
        assert compare_response.json()["previous_version_id"] == version["id"]
        assert compare_response.json()["current_version_id"] == version_v2["id"]
        bundle_response = client.get(f"/api/versions/{version_v2['id']}/recreation-bundle", headers=headers)
        assert bundle_response.status_code == 200, bundle_response.text
        bundle = bundle_response.json()
        assert bundle["expected_hashes"]["combined_fingerprint"] == version_v2["fingerprint"]["combined_fingerprint"]
        verify_response = client.post(
            "/api/versions/recreate/verify",
            headers=headers,
            files={"file": ("placement-v2.csv", csv_v2, "text/csv")},
            data={"bundle_json": json.dumps(bundle)},
        )
        assert verify_response.status_code == 200, verify_response.text
        assert verify_response.json()["matched"] is True
        assert verify_response.json()["similarity_rate"] == 100
        assert verify_response.json()["metrics"]["shape_match"] is True
        diagnosis_contract_response = client.get(f"/api/versions/{version_v2['id']}/diagnosis-contract", headers=headers)
        assert diagnosis_contract_response.status_code == 200, diagnosis_contract_response.text
        diagnosis_contract = diagnosis_contract_response.json()
        assert diagnosis_contract["header"]["version_id"] == version_v2["id"]
        assert "readiness" in diagnosis_contract
        assert "experiment_handoff" in diagnosis_contract
        diagnosis_report_response = client.get(f"/api/versions/{version_v2['id']}/diagnosis-report", headers=headers)
        assert diagnosis_report_response.status_code == 200, diagnosis_report_response.text
        assert diagnosis_report_response.headers["content-type"] == "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        assert diagnosis_report_response.content[:2] == b"PK"
        Path(tempfile.gettempdir(), f"fedrepro-diagnosis-v{version_v2['id']}-report.docx").unlink(missing_ok=True)
        report_response = client.get(f"/api/studies/{study['id']}/executive-report", headers=headers)
        assert report_response.status_code == 200, report_response.text
        assert report_response.headers["content-type"] == "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        assert report_response.content[:2] == b"PK"
        Path(tempfile.gettempdir(), f"fedrepro-study-{study['id']}-executive-report.docx").unlink(missing_ok=True)
        with SessionLocal() as db:
            row_v2 = db.get(DatasetVersion, version_v2["id"])
            version_v2_path = Path(row_v2.immutable_file_path)
            created_paths.append(version_v2_path)
            llm_evidence = resolve_evidence(db, db.get(Study, study["id"]), "version_analysis", version_v2["id"])
            assert llm_evidence["ml_study"]["id"] == study["id"]
            assert llm_evidence["selected_version"]["id"] == version_v2["id"]
            assert len(llm_evidence["version_history"]) == 2
            assert llm_evidence["version_history"][1]["semantic_diff_from_previous"] is not None
            fingerprint = db.query(DatasetFingerprint).filter(DatasetFingerprint.version_id == version_v2["id"]).first()
            assert fingerprint
            db.delete(fingerprint)
            db.commit()
        incomplete_analysis = client.get(f"/api/versions/{version_v2['id']}/analysis", headers=headers)
        assert incomplete_analysis.status_code == 400, incomplete_analysis.text
        assert incomplete_analysis.json()["detail"] == "Dataset version is incomplete: fingerprint missing"

        delete_v2_response = client.delete(f"/api/versions/{version_v2['id']}", headers=headers)
        assert delete_v2_response.status_code == 204, delete_v2_response.text
        assert not version_v2_path.exists()
        datasets = client.get(f"/api/studies/{study['id']}/datasets", headers=headers).json()
        assert [item["version_number"] for item in datasets[0]["versions"]] == [1]

        delete_response = client.delete(f"/api/versions/{version['id']}", headers=headers)
        assert delete_response.status_code == 204, delete_response.text
        assert not version_path.exists()
        assert client.get(f"/api/versions/{version['id']}", headers=headers).status_code == 400
        datasets = client.get(f"/api/studies/{study['id']}/datasets", headers=headers).json()
        assert datasets[0]["versions"] == []
    finally:
        with SessionLocal() as db:
            user = db.query(User).filter(User.email == email).first()
            if user:
                db.delete(user)
                db.commit()
        for path in created_paths:
            path.unlink(missing_ok=True)


def test_study_configuration_completeness_and_diff():
    """
    Integration test for Refinement #1.
    Validates: completeness_score, missing_fields, change_reason, superseded_at,
    source_configuration_id, version-specific fetch, protocol diff, and the
    include_configuration query parameter on the study detail endpoint.
    """
    from app.models.entities import StudyConfiguration

    client = TestClient(app)
    email = f"refinement1-{uuid4().hex}@example.com"
    token = client.post(
        "/api/auth/register",
        json={"name": "Refinement Tester", "email": email, "password": "strongpass1"},
    ).json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    try:
        # 1. Create a minimal study (only ml_task -> low completeness score)
        study = client.post(
            "/api/studies",
            headers=headers,
            json={"name": "Completeness Test Study", "ml_task": "classification"},
        ).json()
        study_id = study["id"]

        # 2. Verify initial configuration contains all new fields
        config_v1 = client.get(
            f"/api/studies/{study_id}/configuration", headers=headers
        ).json()
        assert "completeness_score" in config_v1, "completeness_score missing from response"
        assert "missing_fields" in config_v1, "missing_fields missing from response"
        assert isinstance(config_v1["completeness_score"], int)
        assert 0 <= config_v1["completeness_score"] <= 100
        assert isinstance(config_v1["missing_fields"], list)
        assert config_v1["version_number"] == 1
        assert config_v1["change_reason"] == "Initial research protocol"
        assert config_v1["superseded_at"] is None
        assert config_v1["source_configuration_id"] is None
        initial_completeness = config_v1["completeness_score"]

        # ml_task is set, so score should be 10 (only ml_task contributes from the
        # minimal study payload); everything else is empty
        assert initial_completeness == 10, f"Expected 10, got {initial_completeness}"
        assert "domain" in config_v1["missing_fields"]
        assert "ml_task" not in config_v1["missing_fields"]

        # 3. Create a fully-specified protocol version
        full_payload = {
            "ml_task": "classification",
            "domain": "student placement",
            "data_quality_focus": "missing scores",
            "research_objective": "Understand dataset risks",
            "research_question": "Does repair lower MLRS?",
            "hypothesis": "Missingness repair reduces MLRS",
            "target_column": "placed",
            "primary_metric": "f1_weighted",
            "baseline_model": "random_forest",
            "validation_strategy": "stratified_holdout",
            "random_seed": 42,
            "feature_scope": "all pre-outcome columns",
            "intended_use_case": "Controlled data-centric research",
            "change_reason": "Full protocol specification",
        }
        config_v2_resp = client.post(
            f"/api/studies/{study_id}/configurations",
            headers=headers,
            json=full_payload,
        )
        assert config_v2_resp.status_code == 201, config_v2_resp.text
        config_v2 = config_v2_resp.json()
        assert config_v2["version_number"] == 2
        assert config_v2["completeness_score"] == 100
        assert config_v2["missing_fields"] == []
        assert config_v2["change_reason"] == "Full protocol specification"
        assert config_v2["source_configuration_id"] == config_v1["id"]
        assert config_v2["superseded_at"] is None  # v2 is the current version

        # 4. Verify v1 is now archived and superseded_at is set in the DB
        with SessionLocal() as db:
            v1_row = db.get(StudyConfiguration, config_v1["id"])
            assert v1_row.status == "archived"
            assert v1_row.superseded_at is not None, "superseded_at must be set when archived"

        # 5. Fetch v1 by version number
        v1_fetch = client.get(
            f"/api/studies/{study_id}/configurations/1", headers=headers
        )
        assert v1_fetch.status_code == 200, v1_fetch.text
        assert v1_fetch.json()["version_number"] == 1
        assert v1_fetch.json()["completeness_score"] == 10

        # 6. Fetch v2 by version number
        v2_fetch = client.get(
            f"/api/studies/{study_id}/configurations/2", headers=headers
        )
        assert v2_fetch.status_code == 200
        assert v2_fetch.json()["completeness_score"] == 100

        # 7. Non-existent version number -> 400
        bad = client.get(
            f"/api/studies/{study_id}/configurations/99", headers=headers
        )
        assert bad.status_code == 400

        # 8. Diff v1 -> v2
        diff_resp = client.get(
            f"/api/studies/{study_id}/configurations/diff",
            headers=headers,
            params={"from_version": 1, "to_version": 2},
        )
        assert diff_resp.status_code == 200, diff_resp.text
        diff = diff_resp.json()
        assert diff["from_version"] == 1
        assert diff["to_version"] == 2
        assert diff["hash_changed"] is True
        assert diff["completeness_delta"] == 100 - initial_completeness  # = 90
        assert "domain" in diff["fields_changed"]
        assert "domain" in diff["fields_added"]
        assert isinstance(diff["field_diffs"], list)
        domain_diff = next(d for d in diff["field_diffs"] if d["field"] == "domain")
        assert domain_diff["from_value"] is None
        assert domain_diff["to_value"] == "student placement"
        assert domain_diff["changed"] is True
        ml_task_diff = next(d for d in diff["field_diffs"] if d["field"] == "ml_task")
        assert ml_task_diff["changed"] is False  # ml_task was already 'classification'

        # 9. Same version number -> 400
        same = client.get(
            f"/api/studies/{study_id}/configurations/diff",
            headers=headers,
            params={"from_version": 1, "to_version": 1},
        )
        assert same.status_code == 400

        # 10. Study detail with include_configuration=true -> current_configuration populated
        detail = client.get(
            f"/api/studies/{study_id}",
            headers=headers,
            params={"include_configuration": True},
        )
        assert detail.status_code == 200
        assert detail.json()["current_configuration"] is not None
        assert detail.json()["current_configuration"]["version_number"] == 2
        assert detail.json()["current_configuration"]["completeness_score"] == 100

        # 11. Study detail without flag -> current_configuration is null (backward compat)
        detail_no_config = client.get(f"/api/studies/{study_id}", headers=headers)
        assert detail_no_config.status_code == 200
        assert detail_no_config.json()["current_configuration"] is None

        # 12. Configuration history includes both versions with new fields
        history = client.get(
            f"/api/studies/{study_id}/configurations", headers=headers
        ).json()
        assert len(history) == 2
        assert all("completeness_score" in c for c in history)
        assert all("missing_fields" in c for c in history)
        assert all("change_reason" in c for c in history)

    finally:
        with SessionLocal() as db:
            user = db.query(User).filter(User.email == email).first()
            if user:
                db.delete(user)
                db.commit()


def test_study_configuration_diff_same_version_rejected():
    """from_version == to_version must be rejected with HTTP 400."""
    client = TestClient(app)
    email = f"diff-reject-{uuid4().hex}@example.com"
    token = client.post(
        "/api/auth/register",
        json={"name": "Diff Reject Tester", "email": email, "password": "strongpass1"},
    ).json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    try:
        study = client.post(
            "/api/studies",
            headers=headers,
            json={"name": "Diff Reject Study", "ml_task": "regression"},
        ).json()
        resp = client.get(
            f"/api/studies/{study['id']}/configurations/diff",
            headers=headers,
            params={"from_version": 1, "to_version": 1},
        )
        assert resp.status_code == 400
        assert "different" in resp.json()["detail"].lower()
    finally:
        with SessionLocal() as db:
            user = db.query(User).filter(User.email == email).first()
            if user:
                db.delete(user)
                db.commit()
