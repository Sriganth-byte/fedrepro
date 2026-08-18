"""Add AI insight job table.

Revision ID: 0007_ai_insight_jobs
Revises: 0006_variant_generator
"""
from alembic import op
import sqlalchemy as sa

revision = "0007_ai_insight_jobs"
down_revision = "0006_variant_generator"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "ai_insight_jobs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("version_id", sa.Integer(), sa.ForeignKey("dataset_versions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("study_id", sa.Integer(), sa.ForeignKey("studies.id", ondelete="CASCADE"), nullable=False),
        sa.Column("task_type", sa.String(80), nullable=False),
        sa.Column("priority", sa.Integer(), nullable=False, server_default="5"),
        sa.Column("evidence_hash", sa.String(64), nullable=False),
        sa.Column("context_hash", sa.String(64), nullable=False),
        sa.Column("prompt_version", sa.String(32), nullable=False),
        sa.Column("model_name", sa.String(100), nullable=True),
        sa.Column("status", sa.String(32), nullable=False, server_default="queued"),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("queued_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("execution_time_seconds", sa.Float(), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.CheckConstraint("status IN ('queued','running','completed','failed')", name="ck_ai_insight_jobs_status"),
        sa.CheckConstraint("task_type IN ('version_analysis')", name="ck_ai_insight_jobs_task_type"),
    )
    op.create_index("ix_ai_insight_jobs_version_id", "ai_insight_jobs", ["version_id"])
    op.create_index("ix_ai_insight_jobs_study_id", "ai_insight_jobs", ["study_id"])
    op.create_index("ix_ai_insight_jobs_task_type", "ai_insight_jobs", ["task_type"])
    op.create_index("ix_ai_insight_jobs_priority", "ai_insight_jobs", ["priority"])
    op.create_index("ix_ai_insight_jobs_evidence_hash", "ai_insight_jobs", ["evidence_hash"])
    op.create_index("ix_ai_insight_jobs_context_hash", "ai_insight_jobs", ["context_hash"])
    op.create_index("ix_ai_insight_jobs_prompt_version", "ai_insight_jobs", ["prompt_version"])
    op.create_index("ix_ai_insight_jobs_status", "ai_insight_jobs", ["status"])
    op.create_index(
        "ix_ai_insight_jobs_dedupe",
        "ai_insight_jobs",
        ["version_id", "task_type", "evidence_hash", "context_hash", "prompt_version", "status"],
    )


def downgrade() -> None:
    op.drop_index("ix_ai_insight_jobs_dedupe", table_name="ai_insight_jobs")
    op.drop_index("ix_ai_insight_jobs_status", table_name="ai_insight_jobs")
    op.drop_index("ix_ai_insight_jobs_prompt_version", table_name="ai_insight_jobs")
    op.drop_index("ix_ai_insight_jobs_context_hash", table_name="ai_insight_jobs")
    op.drop_index("ix_ai_insight_jobs_evidence_hash", table_name="ai_insight_jobs")
    op.drop_index("ix_ai_insight_jobs_priority", table_name="ai_insight_jobs")
    op.drop_index("ix_ai_insight_jobs_task_type", table_name="ai_insight_jobs")
    op.drop_index("ix_ai_insight_jobs_study_id", table_name="ai_insight_jobs")
    op.drop_index("ix_ai_insight_jobs_version_id", table_name="ai_insight_jobs")
    op.drop_table("ai_insight_jobs")
