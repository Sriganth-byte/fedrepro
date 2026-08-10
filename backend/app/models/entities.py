from datetime import datetime
from enum import Enum

from sqlalchemy import CheckConstraint, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class TaskType(str, Enum):
    classification = "classification"
    regression = "regression"
    clustering = "clustering"


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class User(TimestampMixin, Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))


class Study(TimestampMixin, Base):
    __tablename__ = "studies"
    id: Mapped[int] = mapped_column(primary_key=True)
    owner_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(180), index=True)
    ml_task: Mapped[str] = mapped_column(String(32), index=True)
    description: Mapped[str | None] = mapped_column(Text)
    problem_objective: Mapped[str | None] = mapped_column(Text)
    intended_use_case: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(32), default="active")
    datasets: Mapped[list["Dataset"]] = relationship(back_populates="study", cascade="all, delete-orphan")
    configurations: Mapped[list["StudyConfiguration"]] = relationship(back_populates="study", cascade="all, delete-orphan")


class StudyConfiguration(TimestampMixin, Base):
    __tablename__ = "study_configurations"
    __table_args__ = (
        UniqueConstraint("study_id", "version_number", name="uq_study_configuration_version"),
        CheckConstraint("ml_task IN ('classification','regression','clustering')", name="ck_study_configuration_task"),
        CheckConstraint("completeness_score >= 0 AND completeness_score <= 100", name="ck_study_configuration_completeness"),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    study_id: Mapped[int] = mapped_column(ForeignKey("studies.id", ondelete="CASCADE"), index=True)
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), index=True)

    # Self-referencing FK: which configuration was this version derived from?
    source_configuration_id: Mapped[int | None] = mapped_column(
        ForeignKey("study_configurations.id", ondelete="SET NULL"),
        index=True,
        nullable=True,
    )

    version_number: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(32), default="current", index=True)
    ml_task: Mapped[str] = mapped_column(String(32))
    domain: Mapped[str | None] = mapped_column(String(180))
    data_quality_focus: Mapped[str | None] = mapped_column(Text)
    research_objective: Mapped[str | None] = mapped_column(Text)
    research_question: Mapped[str | None] = mapped_column(Text)
    hypothesis: Mapped[str | None] = mapped_column(Text)
    target_column: Mapped[str | None] = mapped_column(String(180))
    primary_metric: Mapped[str | None] = mapped_column(String(80))
    baseline_model: Mapped[str | None] = mapped_column(String(120))
    validation_strategy: Mapped[str | None] = mapped_column(String(120))
    random_seed: Mapped[int | None] = mapped_column(Integer)
    feature_scope: Mapped[str | None] = mapped_column(Text)
    intended_use_case: Mapped[str | None] = mapped_column(Text)
    protocol_json: Mapped[dict] = mapped_column(JSONB, default=dict)
    protocol_hash: Mapped[str] = mapped_column(String(64), index=True)

    # Audit columns
    change_reason: Mapped[str | None] = mapped_column(String(500), nullable=True)
    superseded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)

    # Completeness tracking
    completeness_score: Mapped[int] = mapped_column(Integer, default=0)
    missing_fields: Mapped[list] = mapped_column(JSONB, default=list)

    # Relationships
    study: Mapped[Study] = relationship(back_populates="configurations")
    source_configuration: Mapped["StudyConfiguration | None"] = relationship(
        "StudyConfiguration",
        remote_side="StudyConfiguration.id",
        foreign_keys="StudyConfiguration.source_configuration_id",
    )


class Dataset(TimestampMixin, Base):
    __tablename__ = "datasets"
    __table_args__ = (UniqueConstraint("study_id", "name", name="uq_dataset_study_name"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    study_id: Mapped[int] = mapped_column(ForeignKey("studies.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(180))
    study: Mapped[Study] = relationship(back_populates="datasets")
    registrations: Mapped[list["DatasetRegistration"]] = relationship(cascade="all, delete-orphan")
    versions: Mapped[list["DatasetVersion"]] = relationship(back_populates="dataset", cascade="all, delete-orphan")


class DatasetRegistration(TimestampMixin, Base):
    __tablename__ = "dataset_registrations"
    id: Mapped[int] = mapped_column(primary_key=True)
    dataset_id: Mapped[int] = mapped_column(ForeignKey("datasets.id", ondelete="CASCADE"), index=True)
    original_filename: Mapped[str] = mapped_column(String(500))
    staged_file_path: Mapped[str] = mapped_column(String(700))
    file_size: Mapped[int] = mapped_column(Integer)
    version_notes: Mapped[str | None] = mapped_column(Text)
    metadata_json: Mapped[dict] = mapped_column(JSONB)
    validation_json: Mapped[dict] = mapped_column(JSONB)
    status: Mapped[str] = mapped_column(String(32), default="registered")
    configuration: Mapped["DatasetConfiguration | None"] = relationship(back_populates="registration", uselist=False, cascade="all, delete-orphan")


class DatasetConfiguration(TimestampMixin, Base):
    __tablename__ = "dataset_configurations"
    __table_args__ = (CheckConstraint("task_type IN ('classification','regression','clustering')", name="ck_configuration_task"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    dataset_id: Mapped[int] = mapped_column(ForeignKey("datasets.id", ondelete="CASCADE"), index=True)
    registration_id: Mapped[int] = mapped_column(ForeignKey("dataset_registrations.id", ondelete="CASCADE"), unique=True)
    task_type: Mapped[str] = mapped_column(String(32))
    target_column: Mapped[str | None] = mapped_column(String(180))
    primary_metric: Mapped[str | None] = mapped_column(String(80))
    validation_strategy: Mapped[str | None] = mapped_column(String(80))
    feature_selection_mode: Mapped[str | None] = mapped_column(String(80))
    selected_features_json: Mapped[list] = mapped_column(JSONB, default=list)
    scaling_strategy: Mapped[str | None] = mapped_column(String(80))
    configuration_hash: Mapped[str] = mapped_column(String(64), index=True)
    registration: Mapped[DatasetRegistration] = relationship(back_populates="configuration")


class DatasetVersion(TimestampMixin, Base):
    __tablename__ = "dataset_versions"
    __table_args__ = (UniqueConstraint("dataset_id", "version_number", name="uq_dataset_version_number"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    dataset_id: Mapped[int] = mapped_column(ForeignKey("datasets.id", ondelete="CASCADE"), index=True)
    registration_id: Mapped[int] = mapped_column(ForeignKey("dataset_registrations.id", ondelete="RESTRICT"), unique=True)
    configuration_id: Mapped[int] = mapped_column(ForeignKey("dataset_configurations.id", ondelete="CASCADE"))
    parent_version_id: Mapped[int | None] = mapped_column(ForeignKey("dataset_versions.id", ondelete="SET NULL"))
    version_number: Mapped[int] = mapped_column(Integer)
    immutable_file_path: Mapped[str] = mapped_column(String(700))
    version_notes: Mapped[str | None] = mapped_column(Text)
    file_hash: Mapped[str] = mapped_column(String(64), index=True)
    row_count: Mapped[int] = mapped_column(Integer)
    column_count: Mapped[int] = mapped_column(Integer)
    generation_method: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)
    dataset: Mapped[Dataset] = relationship(back_populates="versions")
    fingerprint: Mapped["DatasetFingerprint"] = relationship(back_populates="version", uselist=False, cascade="all, delete-orphan")
    variant_jobs_as_source: Mapped[list["VariantGenerationJob"]] = relationship(
        "VariantGenerationJob",
        foreign_keys="VariantGenerationJob.source_version_id",
        back_populates="source_version",
        lazy="select",
    )
    variant_records: Mapped[list["VariantGenerationRecord"]] = relationship(
        "VariantGenerationRecord",
        foreign_keys="VariantGenerationRecord.variant_version_id",
        back_populates="variant_version",
        lazy="select",
    )


class DatasetFingerprint(TimestampMixin, Base):
    __tablename__ = "dataset_fingerprints"
    id: Mapped[int] = mapped_column(primary_key=True)
    version_id: Mapped[int] = mapped_column(ForeignKey("dataset_versions.id", ondelete="CASCADE"), unique=True, index=True)
    file_hash: Mapped[str] = mapped_column(String(64))
    schema_hash: Mapped[str] = mapped_column(String(64))
    metadata_hash: Mapped[str] = mapped_column(String(64))
    combined_fingerprint: Mapped[str] = mapped_column(String(64), index=True)
    fingerprint_json: Mapped[dict] = mapped_column(JSONB)
    algorithm_version: Mapped[str] = mapped_column(String(32), default="fingerprint-1.0")
    version: Mapped[DatasetVersion] = relationship(back_populates="fingerprint")


class LineageEvent(TimestampMixin, Base):
    __tablename__ = "lineage_events"
    id: Mapped[int] = mapped_column(primary_key=True)
    dataset_id: Mapped[int] = mapped_column(ForeignKey("datasets.id", ondelete="CASCADE"), index=True)
    source_version_id: Mapped[int | None] = mapped_column(ForeignKey("dataset_versions.id", ondelete="SET NULL"))
    destination_version_id: Mapped[int] = mapped_column(ForeignKey("dataset_versions.id", ondelete="CASCADE"), index=True)
    event_type: Mapped[str] = mapped_column(String(80))
    evidence_json: Mapped[dict] = mapped_column(JSONB)


class SemanticDiffReport(TimestampMixin, Base):
    __tablename__ = "semantic_diff_reports"
    id: Mapped[int] = mapped_column(primary_key=True)
    previous_version_id: Mapped[int] = mapped_column(ForeignKey("dataset_versions.id", ondelete="CASCADE"))
    current_version_id: Mapped[int] = mapped_column(ForeignKey("dataset_versions.id", ondelete="CASCADE"), unique=True, index=True)
    report_json: Mapped[dict] = mapped_column(JSONB)
    scm_score: Mapped[float] = mapped_column(Float)
    dsi_score: Mapped[float] = mapped_column(Float)
    ruleset_version: Mapped[str] = mapped_column(String(32), default="semantic-1.0")


class DatasetProfileReport(TimestampMixin, Base):
    __tablename__ = "dataset_profile_reports"
    id: Mapped[int] = mapped_column(primary_key=True)
    version_id: Mapped[int] = mapped_column(ForeignKey("dataset_versions.id", ondelete="CASCADE"), unique=True, index=True)
    configuration_id: Mapped[int] = mapped_column(ForeignKey("dataset_configurations.id", ondelete="CASCADE"))
    report_json: Mapped[dict] = mapped_column(JSONB)
    profiler_version: Mapped[str] = mapped_column(String(32), default="profile-1.0")


class DiagnosisReport(TimestampMixin, Base):
    __tablename__ = "diagnosis_reports"
    id: Mapped[int] = mapped_column(primary_key=True)
    version_id: Mapped[int] = mapped_column(ForeignKey("dataset_versions.id", ondelete="CASCADE"), unique=True, index=True)
    profile_report_id: Mapped[int] = mapped_column(ForeignKey("dataset_profile_reports.id", ondelete="CASCADE"), unique=True)
    findings_json: Mapped[list] = mapped_column(JSONB)
    mlrs_score: Mapped[float] = mapped_column(Float)
    lrs_score: Mapped[float] = mapped_column(Float)
    ruleset_version: Mapped[str] = mapped_column(String(32), default="diagnosis-1.0")


class AIGeneratedExplanation(TimestampMixin, Base):
    __tablename__ = "ai_generated_explanations"
    id: Mapped[int] = mapped_column(primary_key=True)
    study_id: Mapped[int] = mapped_column(ForeignKey("studies.id", ondelete="CASCADE"), index=True)
    semantic_diff_report_id: Mapped[int | None] = mapped_column(ForeignKey("semantic_diff_reports.id", ondelete="CASCADE"))
    profile_report_id: Mapped[int | None] = mapped_column(ForeignKey("dataset_profile_reports.id", ondelete="CASCADE"))
    diagnosis_report_id: Mapped[int | None] = mapped_column(ForeignKey("diagnosis_reports.id", ondelete="CASCADE"))
    explanation_type: Mapped[str] = mapped_column(String(50))
    source_entity_type: Mapped[str] = mapped_column(String(50))
    source_entity_id: Mapped[int] = mapped_column(Integer)
    model: Mapped[str] = mapped_column(String(100))
    prompt_version: Mapped[str] = mapped_column(String(32))
    source_evidence_hash: Mapped[str] = mapped_column(String(64))
    content: Mapped[str] = mapped_column(Text)


class ActivityLog(Base):
    __tablename__ = "activity_logs"
    id: Mapped[int] = mapped_column(primary_key=True)
    study_id: Mapped[int | None] = mapped_column(ForeignKey("studies.id", ondelete="CASCADE"), index=True)
    actor_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    action: Mapped[str] = mapped_column(String(100), index=True)
    entity_type: Mapped[str] = mapped_column(String(50))
    entity_id: Mapped[int | None] = mapped_column(Integer)
    details_json: Mapped[dict] = mapped_column(JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class VariantGenerationJob(Base):
    __tablename__ = "variant_generation_jobs"
    id: Mapped[int] = mapped_column(primary_key=True)
    source_version_id: Mapped[int] = mapped_column(ForeignKey("dataset_versions.id", ondelete="CASCADE"), nullable=False, index=True)
    diagnosis_report_id: Mapped[int | None] = mapped_column(ForeignKey("diagnosis_reports.id", ondelete="SET NULL"), nullable=True)
    optimization_goal: Mapped[str] = mapped_column(String(64), nullable=False, default="maximize_accuracy")
    constraints_json: Mapped[dict] = mapped_column(JSONB, default=dict)
    job_constraints_hash: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="pending", index=True)
    total_variants_planned: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    total_variants_completed: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    source_version: Mapped["DatasetVersion"] = relationship(
        "DatasetVersion",
        foreign_keys=[source_version_id],
        back_populates="variant_jobs_as_source",
    )
    records: Mapped[list["VariantGenerationRecord"]] = relationship(
        "VariantGenerationRecord",
        back_populates="job",
        cascade="all, delete-orphan",
        order_by="VariantGenerationRecord.id",
    )


class VariantGenerationRecord(Base):
    __tablename__ = "variant_generation_records"
    id: Mapped[int] = mapped_column(primary_key=True)
    job_id: Mapped[int] = mapped_column(ForeignKey("variant_generation_jobs.id", ondelete="CASCADE"), nullable=False, index=True)
    variant_version_id: Mapped[int | None] = mapped_column(ForeignKey("dataset_versions.id", ondelete="SET NULL"), nullable=True, index=True)
    pipeline_id: Mapped[str] = mapped_column(String(32), nullable=False)
    pipeline_hash: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    pipeline_steps_json: Mapped[list] = mapped_column(JSONB, default=list)
    random_seed: Mapped[int | None] = mapped_column(Integer, nullable=True)
    execution_time_seconds: Mapped[float | None] = mapped_column(Float, nullable=True)
    estimated_cost: Mapped[str | None] = mapped_column(String(16), nullable=True)
    library_versions_json: Mapped[dict] = mapped_column(JSONB, default=dict)
    mlrs_before: Mapped[float | None] = mapped_column(Float, nullable=True)
    mlrs_after: Mapped[float | None] = mapped_column(Float, nullable=True)
    lrs_after: Mapped[float | None] = mapped_column(Float, nullable=True)
    lrs_caveat: Mapped[str | None] = mapped_column(String(64), nullable=True)
    missing_values_pct_before: Mapped[float | None] = mapped_column(Float, nullable=True)
    missing_values_pct_after: Mapped[float | None] = mapped_column(Float, nullable=True)
    class_balance_score_before: Mapped[float | None] = mapped_column(Float, nullable=True)
    class_balance_score_after: Mapped[float | None] = mapped_column(Float, nullable=True)
    feature_count_before: Mapped[int | None] = mapped_column(Integer, nullable=True)
    feature_count_after: Mapped[int | None] = mapped_column(Integer, nullable=True)
    row_count_before: Mapped[int | None] = mapped_column(Integer, nullable=True)
    row_count_after: Mapped[int | None] = mapped_column(Integer, nullable=True)
    vrs_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    vrs_rank: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    goal_satisfaction: Mapped[str | None] = mapped_column(String(16), nullable=True)
    explanation_json: Mapped[dict] = mapped_column(JSONB, default=dict)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="pending")
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    job: Mapped["VariantGenerationJob"] = relationship("VariantGenerationJob", back_populates="records")
    variant_version: Mapped["DatasetVersion | None"] = relationship(
        "DatasetVersion",
        foreign_keys=[variant_version_id],
        back_populates="variant_records",
    )
