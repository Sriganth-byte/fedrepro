"""FedRepro Phase 1 schema.

Revision ID: 0001_phase1_schema
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0001_phase1_schema"
down_revision = None
branch_labels = None
depends_on = None

JSONB = postgresql.JSONB(astext_type=sa.Text())


def timestamps():
    return [
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    ]


def upgrade() -> None:
    op.create_table("users", sa.Column("id", sa.Integer(), primary_key=True), sa.Column("name", sa.String(120), nullable=False), sa.Column("email", sa.String(255), nullable=False, unique=True), sa.Column("password_hash", sa.String(255), nullable=False), *timestamps())
    op.create_index("ix_users_email", "users", ["email"], unique=True)
    op.create_table("studies", sa.Column("id", sa.Integer(), primary_key=True), sa.Column("owner_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False), sa.Column("name", sa.String(180), nullable=False), sa.Column("ml_task", sa.String(32), nullable=False), sa.Column("description", sa.Text()), sa.Column("problem_objective", sa.Text()), sa.Column("intended_use_case", sa.Text()), sa.Column("status", sa.String(32), nullable=False, server_default="active"), *timestamps(), sa.CheckConstraint("ml_task IN ('classification','regression','clustering')", name="ck_study_task"))
    op.create_index("ix_studies_owner_id", "studies", ["owner_id"])
    op.create_table("datasets", sa.Column("id", sa.Integer(), primary_key=True), sa.Column("study_id", sa.Integer(), sa.ForeignKey("studies.id", ondelete="CASCADE"), nullable=False), sa.Column("name", sa.String(180), nullable=False), *timestamps(), sa.UniqueConstraint("study_id", "name", name="uq_dataset_study_name"))
    op.create_index("ix_datasets_study_id", "datasets", ["study_id"])
    op.create_table("dataset_registrations", sa.Column("id", sa.Integer(), primary_key=True), sa.Column("dataset_id", sa.Integer(), sa.ForeignKey("datasets.id", ondelete="CASCADE"), nullable=False), sa.Column("original_filename", sa.String(500), nullable=False), sa.Column("staged_file_path", sa.String(700), nullable=False), sa.Column("file_size", sa.Integer(), nullable=False), sa.Column("version_notes", sa.Text()), sa.Column("metadata_json", JSONB, nullable=False), sa.Column("validation_json", JSONB, nullable=False), sa.Column("status", sa.String(32), nullable=False, server_default="registered"), *timestamps())
    op.create_index("ix_dataset_registrations_dataset_id", "dataset_registrations", ["dataset_id"])
    op.create_table("dataset_configurations", sa.Column("id", sa.Integer(), primary_key=True), sa.Column("dataset_id", sa.Integer(), sa.ForeignKey("datasets.id", ondelete="CASCADE"), nullable=False), sa.Column("registration_id", sa.Integer(), sa.ForeignKey("dataset_registrations.id", ondelete="CASCADE"), nullable=False, unique=True), sa.Column("task_type", sa.String(32), nullable=False), sa.Column("target_column", sa.String(180)), sa.Column("primary_metric", sa.String(80)), sa.Column("validation_strategy", sa.String(80)), sa.Column("feature_selection_mode", sa.String(80)), sa.Column("selected_features_json", JSONB, nullable=False, server_default=sa.text("'[]'::jsonb")), sa.Column("scaling_strategy", sa.String(80)), sa.Column("configuration_hash", sa.String(64), nullable=False), *timestamps(), sa.CheckConstraint("task_type IN ('classification','regression','clustering')", name="ck_configuration_task"))
    op.create_index("ix_dataset_configurations_dataset_id", "dataset_configurations", ["dataset_id"])
    op.create_index("ix_dataset_configurations_configuration_hash", "dataset_configurations", ["configuration_hash"])
    op.create_table("dataset_versions", sa.Column("id", sa.Integer(), primary_key=True), sa.Column("dataset_id", sa.Integer(), sa.ForeignKey("datasets.id", ondelete="CASCADE"), nullable=False), sa.Column("registration_id", sa.Integer(), sa.ForeignKey("dataset_registrations.id", ondelete="RESTRICT"), nullable=False, unique=True), sa.Column("configuration_id", sa.Integer(), sa.ForeignKey("dataset_configurations.id", ondelete="RESTRICT"), nullable=False), sa.Column("parent_version_id", sa.Integer(), sa.ForeignKey("dataset_versions.id", ondelete="SET NULL")), sa.Column("version_number", sa.Integer(), nullable=False), sa.Column("immutable_file_path", sa.String(700), nullable=False), sa.Column("version_notes", sa.Text()), sa.Column("file_hash", sa.String(64), nullable=False), sa.Column("row_count", sa.Integer(), nullable=False), sa.Column("column_count", sa.Integer(), nullable=False), *timestamps(), sa.UniqueConstraint("dataset_id", "version_number", name="uq_dataset_version_number"))
    op.create_index("ix_dataset_versions_dataset_id", "dataset_versions", ["dataset_id"])
    op.create_index("ix_dataset_versions_file_hash", "dataset_versions", ["file_hash"])
    op.create_table("dataset_fingerprints", sa.Column("id", sa.Integer(), primary_key=True), sa.Column("version_id", sa.Integer(), sa.ForeignKey("dataset_versions.id", ondelete="CASCADE"), nullable=False, unique=True), sa.Column("file_hash", sa.String(64), nullable=False), sa.Column("schema_hash", sa.String(64), nullable=False), sa.Column("metadata_hash", sa.String(64), nullable=False), sa.Column("combined_fingerprint", sa.String(64), nullable=False, unique=True), sa.Column("fingerprint_json", JSONB, nullable=False), sa.Column("algorithm_version", sa.String(32), nullable=False), *timestamps())
    op.create_table("lineage_events", sa.Column("id", sa.Integer(), primary_key=True), sa.Column("dataset_id", sa.Integer(), sa.ForeignKey("datasets.id", ondelete="CASCADE"), nullable=False), sa.Column("source_version_id", sa.Integer(), sa.ForeignKey("dataset_versions.id", ondelete="SET NULL")), sa.Column("destination_version_id", sa.Integer(), sa.ForeignKey("dataset_versions.id", ondelete="CASCADE"), nullable=False), sa.Column("event_type", sa.String(80), nullable=False), sa.Column("evidence_json", JSONB, nullable=False), *timestamps())
    op.create_table("semantic_diff_reports", sa.Column("id", sa.Integer(), primary_key=True), sa.Column("previous_version_id", sa.Integer(), sa.ForeignKey("dataset_versions.id", ondelete="CASCADE"), nullable=False), sa.Column("current_version_id", sa.Integer(), sa.ForeignKey("dataset_versions.id", ondelete="CASCADE"), nullable=False, unique=True), sa.Column("report_json", JSONB, nullable=False), sa.Column("scm_score", sa.Float(), nullable=False), sa.Column("dsi_score", sa.Float(), nullable=False), sa.Column("ruleset_version", sa.String(32), nullable=False), *timestamps())
    op.create_table("dataset_profile_reports", sa.Column("id", sa.Integer(), primary_key=True), sa.Column("version_id", sa.Integer(), sa.ForeignKey("dataset_versions.id", ondelete="CASCADE"), nullable=False, unique=True), sa.Column("configuration_id", sa.Integer(), sa.ForeignKey("dataset_configurations.id", ondelete="RESTRICT"), nullable=False), sa.Column("report_json", JSONB, nullable=False), sa.Column("profiler_version", sa.String(32), nullable=False), *timestamps())
    op.create_table("diagnosis_reports", sa.Column("id", sa.Integer(), primary_key=True), sa.Column("version_id", sa.Integer(), sa.ForeignKey("dataset_versions.id", ondelete="CASCADE"), nullable=False, unique=True), sa.Column("profile_report_id", sa.Integer(), sa.ForeignKey("dataset_profile_reports.id", ondelete="CASCADE"), nullable=False, unique=True), sa.Column("findings_json", JSONB, nullable=False), sa.Column("mlrs_score", sa.Float(), nullable=False), sa.Column("lrs_score", sa.Float(), nullable=False), sa.Column("ruleset_version", sa.String(32), nullable=False), *timestamps())
    op.create_table("ai_generated_explanations", sa.Column("id", sa.Integer(), primary_key=True), sa.Column("study_id", sa.Integer(), sa.ForeignKey("studies.id", ondelete="CASCADE"), nullable=False), sa.Column("explanation_type", sa.String(50), nullable=False), sa.Column("source_entity_type", sa.String(50), nullable=False), sa.Column("source_entity_id", sa.Integer(), nullable=False), sa.Column("model", sa.String(100), nullable=False), sa.Column("prompt_version", sa.String(32), nullable=False), sa.Column("source_evidence_hash", sa.String(64), nullable=False), sa.Column("content", sa.Text(), nullable=False), *timestamps())
    op.create_table("activity_logs", sa.Column("id", sa.Integer(), primary_key=True), sa.Column("study_id", sa.Integer(), sa.ForeignKey("studies.id", ondelete="CASCADE")), sa.Column("actor_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL")), sa.Column("action", sa.String(100), nullable=False), sa.Column("entity_type", sa.String(50), nullable=False), sa.Column("entity_id", sa.Integer()), sa.Column("details_json", JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")), sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False))


def downgrade() -> None:
    for table in ["activity_logs", "ai_generated_explanations", "diagnosis_reports", "dataset_profile_reports", "semantic_diff_reports", "lineage_events", "dataset_fingerprints", "dataset_versions", "dataset_configurations", "dataset_registrations", "datasets", "studies", "users"]:
        op.drop_table(table)

