"""Add Variant Generator tables and generation_method column.

Revision ID: 0006_variant_generator
Revises: 0005_study_configuration_completeness
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0006_variant_generator"
down_revision = "0005_study_configuration_completeness"
branch_labels = None
depends_on = None

JSONB = postgresql.JSONB(astext_type=sa.Text())


def upgrade() -> None:
    # ── 1. variant_generation_jobs ────────────────────────────────────────────
    op.create_table(
        "variant_generation_jobs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("source_version_id", sa.Integer(), sa.ForeignKey("dataset_versions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("diagnosis_report_id", sa.Integer(), sa.ForeignKey("diagnosis_reports.id", ondelete="SET NULL"), nullable=True),
        sa.Column("optimization_goal", sa.String(64), nullable=False, server_default="maximize_accuracy"),
        sa.Column("constraints_json", JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("job_constraints_hash", sa.String(64), nullable=False, server_default=""),
        sa.Column("status", sa.String(32), nullable=False, server_default="pending"),
        sa.Column("total_variants_planned", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("total_variants_completed", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_vjobs_source_version_id", "variant_generation_jobs", ["source_version_id"])
    op.create_index("ix_vjobs_status", "variant_generation_jobs", ["status"])
    op.create_index("ix_vjobs_constraints_hash", "variant_generation_jobs", ["job_constraints_hash"])

    # ── 2. variant_generation_records ─────────────────────────────────────────
    op.create_table(
        "variant_generation_records",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("job_id", sa.Integer(), sa.ForeignKey("variant_generation_jobs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("variant_version_id", sa.Integer(), sa.ForeignKey("dataset_versions.id", ondelete="SET NULL"), nullable=True),
        sa.Column("pipeline_id", sa.String(32), nullable=False),
        sa.Column("pipeline_hash", sa.String(64), nullable=False, server_default=""),
        sa.Column("pipeline_steps_json", JSONB, nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("random_seed", sa.Integer(), nullable=True),
        sa.Column("execution_time_seconds", sa.Float(), nullable=True),
        sa.Column("estimated_cost", sa.String(16), nullable=True),
        sa.Column("library_versions_json", JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("mlrs_before", sa.Float(), nullable=True),
        sa.Column("mlrs_after", sa.Float(), nullable=True),
        sa.Column("lrs_after", sa.Float(), nullable=True),
        sa.Column("lrs_caveat", sa.String(64), nullable=True),
        sa.Column("missing_values_pct_before", sa.Float(), nullable=True),
        sa.Column("missing_values_pct_after", sa.Float(), nullable=True),
        sa.Column("class_balance_score_before", sa.Float(), nullable=True),
        sa.Column("class_balance_score_after", sa.Float(), nullable=True),
        sa.Column("feature_count_before", sa.Integer(), nullable=True),
        sa.Column("feature_count_after", sa.Integer(), nullable=True),
        sa.Column("row_count_before", sa.Integer(), nullable=True),
        sa.Column("row_count_after", sa.Integer(), nullable=True),
        sa.Column("vrs_score", sa.Float(), nullable=True),
        sa.Column("vrs_rank", sa.Integer(), nullable=True),
        sa.Column("goal_satisfaction", sa.String(16), nullable=True),
        sa.Column("explanation_json", JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("status", sa.String(32), nullable=False, server_default="pending"),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_vrecords_job_id", "variant_generation_records", ["job_id"])
    op.create_index("ix_vrecords_variant_version_id", "variant_generation_records", ["variant_version_id"])
    op.create_index("ix_vrecords_vrs_rank", "variant_generation_records", ["vrs_rank"])

    # ── 3. generation_method on dataset_versions ──────────────────────────────
    op.add_column(
        "dataset_versions",
        sa.Column("generation_method", sa.String(32), nullable=True),
    )
    op.create_index("ix_dataset_versions_generation_method", "dataset_versions", ["generation_method"])


def downgrade() -> None:
    op.drop_index("ix_dataset_versions_generation_method", table_name="dataset_versions")
    op.drop_column("dataset_versions", "generation_method")

    op.drop_index("ix_vrecords_vrs_rank", table_name="variant_generation_records")
    op.drop_index("ix_vrecords_variant_version_id", table_name="variant_generation_records")
    op.drop_index("ix_vrecords_job_id", table_name="variant_generation_records")
    op.drop_table("variant_generation_records")

    op.drop_index("ix_vjobs_constraints_hash", table_name="variant_generation_jobs")
    op.drop_index("ix_vjobs_status", table_name="variant_generation_jobs")
    op.drop_index("ix_vjobs_source_version_id", table_name="variant_generation_jobs")
    op.drop_table("variant_generation_jobs")
