"""Add versioned study research protocols.

Revision ID: 0004_study_configurations
Revises: 0003_ai_source_foreign_keys
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0004_study_configurations"
down_revision = "0003_ai_source_foreign_keys"
branch_labels = None
depends_on = None

JSONB = postgresql.JSONB(astext_type=sa.Text())


def upgrade() -> None:
    op.create_table(
        "study_configurations",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("study_id", sa.Integer(), sa.ForeignKey("studies.id", ondelete="CASCADE"), nullable=False),
        sa.Column("created_by", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("version_number", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(32), nullable=False, server_default="current"),
        sa.Column("ml_task", sa.String(32), nullable=False),
        sa.Column("domain", sa.String(180), nullable=True),
        sa.Column("data_quality_focus", sa.Text(), nullable=True),
        sa.Column("research_objective", sa.Text(), nullable=True),
        sa.Column("research_question", sa.Text(), nullable=True),
        sa.Column("hypothesis", sa.Text(), nullable=True),
        sa.Column("target_column", sa.String(180), nullable=True),
        sa.Column("primary_metric", sa.String(80), nullable=True),
        sa.Column("baseline_model", sa.String(120), nullable=True),
        sa.Column("validation_strategy", sa.String(120), nullable=True),
        sa.Column("random_seed", sa.Integer(), nullable=True),
        sa.Column("feature_scope", sa.Text(), nullable=True),
        sa.Column("intended_use_case", sa.Text(), nullable=True),
        sa.Column("protocol_json", JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("protocol_hash", sa.String(64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("ml_task IN ('classification','regression','clustering')", name="ck_study_configuration_task"),
        sa.UniqueConstraint("study_id", "version_number", name="uq_study_configuration_version"),
    )
    op.create_index("ix_study_configurations_study_id", "study_configurations", ["study_id"])
    op.create_index("ix_study_configurations_created_by", "study_configurations", ["created_by"])
    op.create_index("ix_study_configurations_status", "study_configurations", ["status"])
    op.create_index("ix_study_configurations_protocol_hash", "study_configurations", ["protocol_hash"])
    op.create_index(
        "ix_study_configurations_one_current",
        "study_configurations",
        ["study_id"],
        unique=True,
        postgresql_where=sa.text("status = 'current'"),
    )
    op.execute(
        """
        INSERT INTO study_configurations (
            study_id,
            created_by,
            version_number,
            status,
            ml_task,
            research_objective,
            intended_use_case,
            protocol_json,
            protocol_hash,
            created_at,
            updated_at
        )
        SELECT
            id,
            owner_id,
            1,
            'current',
            ml_task,
            problem_objective,
            intended_use_case,
            jsonb_build_object(
                'legacy_description', description,
                'research_objective', problem_objective,
                'intended_use_case', intended_use_case
            ),
            md5(
                coalesce(ml_task, '') || '|' ||
                coalesce(description, '') || '|' ||
                coalesce(problem_objective, '') || '|' ||
                coalesce(intended_use_case, '')
            ) ||
            md5(
                'study-protocol-1.0|' ||
                coalesce(ml_task, '') || '|' ||
                coalesce(description, '') || '|' ||
                coalesce(problem_objective, '') || '|' ||
                coalesce(intended_use_case, '')
            ),
            created_at,
            updated_at
        FROM studies
        """
    )


def downgrade() -> None:
    op.drop_index("ix_study_configurations_one_current", table_name="study_configurations")
    op.drop_index("ix_study_configurations_protocol_hash", table_name="study_configurations")
    op.drop_index("ix_study_configurations_status", table_name="study_configurations")
    op.drop_index("ix_study_configurations_created_by", table_name="study_configurations")
    op.drop_index("ix_study_configurations_study_id", table_name="study_configurations")
    op.drop_table("study_configurations")
