from pathlib import Path

import pandas as pd
from fastapi import UploadFile
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.entities import ActivityLog, Dataset, DatasetConfiguration, DatasetFingerprint, DatasetProfileReport, DatasetRegistration, DatasetVersion, DiagnosisReport, LineageEvent, SemanticDiffReport, Study
from app.schemas.contracts import ConfigurationCreate
from app.services.dataset_explanation_report_service import DatasetExplanationReportService
from app.services.diagnosis_service import DiagnosisService
from app.services.fingerprint_service import FingerprintService
from app.services.profiling_service import ProfilingService
from app.services.semantic_diff_service import SemanticDiffService
from app.storage.local_storage import LocalFileStorage
from app.utilities.hashing import canonical_hash


class DatasetWorkflowService:
    SUPERVISED_METRICS = {"classification": {"accuracy", "f1_weighted", "f1_macro", "precision", "recall", "roc_auc"}, "regression": {"rmse", "mae", "r2", "mape"}}
    VALIDATION_STRATEGIES = {"holdout", "stratified_holdout", "k_fold", "stratified_k_fold"}
    SCALING_STRATEGIES = {"none", "standard", "robust", "minmax"}

    def __init__(self, db: Session, storage: LocalFileStorage | None = None):
        self.db = db
        self.storage = storage or LocalFileStorage()

    @staticmethod
    def metadata(frame: pd.DataFrame) -> dict:
        return {"row_count": int(len(frame)), "column_count": int(len(frame.columns)), "column_names": list(frame.columns), "data_types": {column: str(frame[column].dtype) for column in frame.columns}, "missing_values": {column: int(value) for column, value in frame.isna().sum().items()}, "missing_total": int(frame.isna().sum().sum()), "duplicate_count": int(frame.duplicated().sum()), "memory_usage_bytes": int(frame.memory_usage(deep=True).sum())}

    async def register(self, study: Study, user_id: int, upload: UploadFile, dataset_name: str | None, version_notes: str | None) -> DatasetRegistration:
        staged, frame = await self.storage.stage_csv(upload)
        name = (dataset_name or Path(upload.filename or "dataset").stem).strip()[:180] or "Dataset"
        dataset = self.db.query(Dataset).filter(Dataset.study_id == study.id, func.lower(Dataset.name) == name.lower()).first()
        if not dataset:
            dataset = Dataset(study_id=study.id, name=name)
            self.db.add(dataset)
            self.db.flush()
        metadata = self.metadata(frame)
        registration = DatasetRegistration(dataset_id=dataset.id, original_filename=Path(upload.filename or "dataset.csv").name, staged_file_path=str(staged), file_size=staged.stat().st_size, version_notes=(version_notes or "").strip() or None, metadata_json=metadata, validation_json={"valid_csv": True, "schema_valid": True, "warnings": []}, status="registered")
        self.db.add(registration)
        self.db.flush()
        self.db.add(ActivityLog(study_id=study.id, actor_id=user_id, action="dataset.registered", entity_type="registration", entity_id=registration.id, details_json={"dataset_id": dataset.id, "rows": metadata["row_count"], "columns": metadata["column_count"]}))
        self.db.add(ActivityLog(study_id=study.id, actor_id=user_id, action="dataset.registration_report", entity_type="registration", entity_id=registration.id, details_json=DatasetExplanationReportService.registration_report(study, dataset, registration)))
        self.db.commit()
        self.db.refresh(registration)
        return registration

    def configure_and_analyze(self, study: Study, user_id: int, registration_id: int, payload: ConfigurationCreate) -> DatasetVersion:
        registration = self.db.query(DatasetRegistration).join(Dataset).filter(DatasetRegistration.id == registration_id, Dataset.study_id == study.id).first()
        if not registration:
            raise ValueError("Dataset registration not found")
        if registration.status != "registered":
            existing = self.db.query(DatasetVersion).filter(DatasetVersion.registration_id == registration.id).first()
            if existing:
                return existing
            raise ValueError("Registration is not available for configuration")
        columns = registration.metadata_json["column_names"]
        config = payload.model_dump()
        self._validate_configuration(study.ml_task, columns, config)
        config_hash = canonical_hash({"task_type": study.ml_task, **config})
        configuration = DatasetConfiguration(dataset_id=registration.dataset_id, registration_id=registration.id, task_type=study.ml_task, target_column=config["target_column"], primary_metric=config["primary_metric"], validation_strategy=config["validation_strategy"], feature_selection_mode=config["feature_selection_mode"], selected_features_json=config["selected_features"], scaling_strategy=config["scaling_strategy"], configuration_hash=config_hash)
        self.db.add(configuration)
        self.db.flush()
        previous = self.db.query(DatasetVersion).filter(DatasetVersion.dataset_id == registration.dataset_id).order_by(DatasetVersion.version_number.desc()).first()
        version_number = (previous.version_number + 1) if previous else 1
        destination = self.storage.promote(registration.staged_file_path, study.id, registration.dataset_id, version_number)
        try:
            frame = pd.read_csv(destination)
            fingerprint_data = FingerprintService().generate(str(destination), frame, registration.metadata_json, config_hash)
            version = DatasetVersion(dataset_id=registration.dataset_id, registration_id=registration.id, configuration_id=configuration.id, parent_version_id=previous.id if previous else None, version_number=version_number, immutable_file_path=str(destination), version_notes=registration.version_notes, file_hash=fingerprint_data["file_hash"], row_count=len(frame), column_count=len(frame.columns))
            self.db.add(version)
            self.db.flush()
            self.db.add(DatasetFingerprint(version_id=version.id, **fingerprint_data))
            self.db.add(LineageEvent(dataset_id=version.dataset_id, source_version_id=previous.id if previous else None, destination_version_id=version.id, event_type="version.created", evidence_json={"file_hash": version.file_hash, "configuration_hash": config_hash, "version_number": version_number}))
            semantic_record, semantic_payload = None, None
            if previous:
                semantic_payload = SemanticDiffService().compare(pd.read_csv(previous.immutable_file_path), frame, config.get("target_column"))
                semantic_record = SemanticDiffReport(previous_version_id=previous.id, current_version_id=version.id, report_json=semantic_payload["report"], scm_score=semantic_payload["scm_score"], dsi_score=semantic_payload["dsi_score"], ruleset_version=semantic_payload["ruleset_version"])
                self.db.add(semantic_record)
            profile_payload = ProfilingService().profile(frame, study.ml_task, config)
            profile = DatasetProfileReport(version_id=version.id, configuration_id=configuration.id, report_json=profile_payload, profiler_version=ProfilingService.profiler_version)
            self.db.add(profile)
            self.db.flush()
            diagnosis = DiagnosisService().diagnose(profile_payload, semantic_payload, {"source_version_id": previous.id if previous else None, "version_number": version_number, "version_notes": registration.version_notes}, config)
            diagnosis_record = DiagnosisReport(version_id=version.id, profile_report_id=profile.id, findings_json=diagnosis["findings"], mlrs_score=diagnosis["mlrs_score"], lrs_score=diagnosis["lrs_score"], ruleset_version=diagnosis["ruleset_version"])
            self.db.add(diagnosis_record)
            self.db.flush()
            registration.status = "completed"
            self.db.add(ActivityLog(study_id=study.id, actor_id=user_id, action="dataset.analyzed", entity_type="dataset_version", entity_id=version.id, details_json={"version_number": version_number, "mlrs": diagnosis["mlrs_score"], "lrs": diagnosis["lrs_score"]}))
            self.db.add(ActivityLog(study_id=study.id, actor_id=user_id, action="diagnosis.score_breakdown", entity_type="diagnosis_report", entity_id=diagnosis_record.id, details_json=diagnosis["score_breakdown"]))
            fingerprint = self.db.query(DatasetFingerprint).filter(DatasetFingerprint.version_id == version.id).first()
            self.db.add(ActivityLog(study_id=study.id, actor_id=user_id, action="dataset.version_report", entity_type="dataset_version", entity_id=version.id, details_json=DatasetExplanationReportService.version_report(study, self.db.get(Dataset, version.dataset_id), registration, version, configuration, fingerprint, profile, diagnosis_record, semantic_record)))
            self.db.commit()
            self.db.refresh(version)
            return version
        except Exception:
            self.db.rollback()
            staged = Path(registration.staged_file_path)
            staged.parent.mkdir(parents=True, exist_ok=True)
            if destination.exists() and not staged.exists():
                destination.replace(staged)
            raise

    def _validate_configuration(self, task_type: str, columns: list[str], config: dict) -> None:
        if task_type in {"classification", "regression"}:
            if config.get("target_column") not in columns:
                raise ValueError("Select a valid target column")
            if config.get("primary_metric") not in self.SUPERVISED_METRICS[task_type]:
                raise ValueError("Select a metric valid for the study task")
            if config.get("validation_strategy") not in self.VALIDATION_STRATEGIES:
                raise ValueError("Select a valid validation strategy")
        else:
            if config.get("scaling_strategy") not in self.SCALING_STRATEGIES:
                raise ValueError("Select a valid clustering scaling strategy")
            selected = config.get("selected_features") or []
            if any(column not in columns for column in selected):
                raise ValueError("Selected clustering features must exist in the dataset")

    def delete_version(self, study: Study, user_id: int, version_id: int) -> None:
        version = self.db.query(DatasetVersion).join(Dataset).filter(
            DatasetVersion.id == version_id,
            Dataset.study_id == study.id,
        ).first()
        if not version:
            raise ValueError("Dataset version not found")

        registration = self.db.get(DatasetRegistration, version.registration_id)
        file_path = version.immutable_file_path
        details = {
            "dataset_id": version.dataset_id,
            "version_number": version.version_number,
            "file_hash": version.file_hash,
        }

        self.db.delete(version)
        self.db.flush()
        if registration:
            self.db.delete(registration)
        self.db.add(ActivityLog(
            study_id=study.id,
            actor_id=user_id,
            action="dataset.version_deleted",
            entity_type="dataset_version",
            entity_id=version_id,
            details_json=details,
        ))
        self.db.commit()
        self.storage.delete_version_file(file_path)

    def refresh_semantic_report(self, report: SemanticDiffReport) -> bool:
        # Metric reports are historical evidence; new algorithms apply to new comparisons only.
        return False
