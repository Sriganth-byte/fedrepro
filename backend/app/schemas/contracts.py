from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, EmailStr, Field, field_validator

Task = Literal["classification", "regression", "clustering"]


class RegisterRequest(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class StudyCreate(BaseModel):
    name: str = Field(min_length=2, max_length=180)
    ml_task: Task
    description: str | None = None
    problem_objective: str | None = None
    intended_use_case: str | None = None


class StudyUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=180)
    ml_task: Task | None = None
    description: str | None = None
    problem_objective: str | None = None
    intended_use_case: str | None = None


# ── Study Configuration schemas ──────────────────────────────────────────────
# These must be defined BEFORE StudyRead so that StudyRead can reference
# StudyConfigurationRead without a forward-reference string.

class StudyConfigurationBase(BaseModel):
    ml_task: Task | None = None
    domain: str | None = Field(default=None, max_length=180)
    data_quality_focus: str | None = None
    research_objective: str | None = None
    research_question: str | None = None
    hypothesis: str | None = None
    target_column: str | None = Field(default=None, max_length=180)
    primary_metric: str | None = Field(default=None, max_length=80)
    baseline_model: str | None = Field(default=None, max_length=120)
    validation_strategy: str | None = Field(default=None, max_length=120)
    random_seed: int | None = Field(default=None, ge=0)
    feature_scope: str | None = None
    intended_use_case: str | None = None

    @field_validator(
        "domain",
        "data_quality_focus",
        "research_objective",
        "research_question",
        "hypothesis",
        "target_column",
        "primary_metric",
        "baseline_model",
        "validation_strategy",
        "feature_scope",
        "intended_use_case",
        mode="before",
    )
    @classmethod
    def blank_to_none(cls, value):
        if value is None:
            return None
        value = str(value).strip()
        return value or None


class StudyConfigurationCreate(StudyConfigurationBase):
    change_reason: str | None = Field(default=None, max_length=500)


class StudyConfigurationRead(StudyConfigurationBase):
    id: int
    study_id: int
    created_by: int | None
    version_number: int
    status: str
    protocol_json: dict[str, Any]
    protocol_hash: str

    # Audit fields
    change_reason: str | None
    superseded_at: datetime | None
    source_configuration_id: int | None

    # Completeness fields
    completeness_score: int
    missing_fields: list[str]

    created_at: datetime
    updated_at: datetime
    model_config = {"from_attributes": True}


class ProtocolFieldDiff(BaseModel):
    """A single field comparison between two protocol versions."""
    field: str
    from_value: Any
    to_value: Any
    changed: bool


class StudyConfigurationDiff(BaseModel):
    """Full field-level diff between two study configuration versions."""
    study_id: int
    from_version: int
    to_version: int
    from_hash: str
    to_hash: str
    hash_changed: bool
    completeness_delta: int
    from_completeness_score: int
    to_completeness_score: int
    fields_changed: list[str]
    fields_added: list[str]
    fields_removed: list[str]
    field_diffs: list[ProtocolFieldDiff]


# ── Study Read (references StudyConfigurationRead defined above) ──────────────

class StudyRead(StudyCreate):
    id: int
    status: str
    created_at: datetime
    updated_at: datetime
    # Populated only when ?include_configuration=true is requested; None by default.
    current_configuration: StudyConfigurationRead | None = None
    model_config = {"from_attributes": True}


# ── Dataset configuration ─────────────────────────────────────────────────────

class ConfigurationCreate(BaseModel):
    target_column: str | None = None
    primary_metric: str | None = None
    validation_strategy: str | None = None
    feature_selection_mode: str | None = None
    selected_features: list[str] = Field(default_factory=list)
    scaling_strategy: str | None = None


class ExplanationRequest(BaseModel):
    explanation_type: Literal[
        "study_description", "semantic_diff", "profile", "diagnosis",
        "version_analysis", "semantic_metrics", "semantic_diff_interpretation",
        "dataset_executive_summary", "dataset_explanation_report",
        "diagnosis_report_interpretation",
    ]
    source_entity_id: int


class DashboardRead(BaseModel):
    total_studies: int
    total_datasets: int
    total_versions: int
    high_risk_studies: int
    recent_activity: list[dict[str, Any]]
    recent_diagnoses: list[dict[str, Any]]


# ── Variant Generator schemas ─────────────────────────────────────────────────

class VariantConstraints(BaseModel):
    max_preprocessing_seconds: int | None = None
    max_features: int | None = None
    avoid_synthetic_data: bool = False
    preserve_distribution: bool = False
    max_memory_mb: int | None = None


class VariantJobCreate(BaseModel):
    source_version_id: int
    optimization_goal: str = "maximize_accuracy"
    constraints: VariantConstraints = Field(default_factory=VariantConstraints)
    n_pipelines: int = Field(default=4, ge=2, le=8)
    force_regenerate: bool = False


class VariantPipelineStepRead(BaseModel):
    category: str
    transformation_id: str
    label: str
    params: dict[str, Any]
    explanation: str
    model_config = {"from_attributes": True}


class VariantRecordRead(BaseModel):
    id: int
    pipeline_id: str
    pipeline_hash: str
    steps: list[VariantPipelineStepRead] = Field(default_factory=list)
    estimated_cost: str | None
    execution_time_seconds: float | None
    mlrs_before: float | None
    mlrs_after: float | None
    mlrs_improvement: float | None = None   # computed: mlrs_before - mlrs_after
    lrs_after: float | None
    lrs_caveat: str | None
    missing_values_pct_before: float | None
    missing_values_pct_after: float | None
    class_balance_score_before: float | None
    class_balance_score_after: float | None
    feature_count_before: int | None
    feature_count_after: int | None
    row_count_before: int | None
    row_count_after: int | None
    vrs_score: float | None
    vrs_rank: int | None
    goal_satisfaction: str | None
    explanation_json: dict[str, Any]
    status: str
    error_message: str | None
    variant_version_id: int | None
    library_versions: dict[str, Any] = Field(default_factory=dict)
    random_seed: int | None
    created_at: datetime

    @classmethod
    def from_orm_record(cls, record) -> "VariantRecordRead":
        """Build from ORM VariantGenerationRecord, computing derived fields."""
        improvement = None
        if record.mlrs_before is not None and record.mlrs_after is not None:
            improvement = round(record.mlrs_before - record.mlrs_after, 2)
        steps = []
        for s in (record.pipeline_steps_json or []):
            steps.append(VariantPipelineStepRead(
                category=s.get("category", ""),
                transformation_id=s.get("transformation_id", ""),
                label=s.get("label", ""),
                params=s.get("params", {}),
                explanation=s.get("explanation", ""),
            ))
        return cls(
            id=record.id,
            pipeline_id=record.pipeline_id,
            pipeline_hash=record.pipeline_hash or "",
            steps=steps,
            estimated_cost=record.estimated_cost,
            execution_time_seconds=record.execution_time_seconds,
            mlrs_before=record.mlrs_before,
            mlrs_after=record.mlrs_after,
            mlrs_improvement=improvement,
            lrs_after=record.lrs_after,
            lrs_caveat=record.lrs_caveat,
            missing_values_pct_before=record.missing_values_pct_before,
            missing_values_pct_after=record.missing_values_pct_after,
            class_balance_score_before=record.class_balance_score_before,
            class_balance_score_after=record.class_balance_score_after,
            feature_count_before=record.feature_count_before,
            feature_count_after=record.feature_count_after,
            row_count_before=record.row_count_before,
            row_count_after=record.row_count_after,
            vrs_score=record.vrs_score,
            vrs_rank=record.vrs_rank,
            goal_satisfaction=record.goal_satisfaction,
            explanation_json=record.explanation_json or {},
            status=record.status,
            error_message=record.error_message,
            variant_version_id=record.variant_version_id,
            library_versions=record.library_versions_json or {},
            random_seed=record.random_seed,
            created_at=record.created_at,
        )

    model_config = {"from_attributes": True}


class VariantJobRead(BaseModel):
    id: int
    source_version_id: int
    optimization_goal: str
    constraints_json: dict[str, Any]
    status: str
    total_variants_planned: int
    total_variants_completed: int
    error_message: str | None
    created_at: datetime
    completed_at: datetime | None
    records: list[VariantRecordRead] = Field(default_factory=list)
    model_config = {"from_attributes": True}

