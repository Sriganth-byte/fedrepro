"""Add completeness tracking and audit columns to study_configurations.

Revision ID: 0005_study_configuration_completeness
Revises: 0004_study_configurations
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0005_study_configuration_completeness"
down_revision = "0004_study_configurations"
branch_labels = None
depends_on = None

JSONB = postgresql.JSONB(astext_type=sa.Text())


def upgrade() -> None:
    # 1. change_reason as a proper DB column (was only inside protocol_json)
    op.add_column(
        "study_configurations",
        sa.Column("change_reason", sa.String(500), nullable=True),
    )

    # 2. superseded_at — records when a configuration was archived
    op.add_column(
        "study_configurations",
        sa.Column("superseded_at", sa.DateTime(timezone=True), nullable=True),
    )

    # 3. source_configuration_id — self-referencing FK for lineage
    op.add_column(
        "study_configurations",
        sa.Column("source_configuration_id", sa.Integer(), nullable=True),
    )
    op.create_foreign_key(
        "fk_study_configuration_source",
        "study_configurations",
        "study_configurations",
        ["source_configuration_id"],
        ["id"],
        ondelete="SET NULL",
    )

    # 4. completeness_score — integer 0–100
    op.add_column(
        "study_configurations",
        sa.Column(
            "completeness_score",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
    )
    op.create_check_constraint(
        "ck_study_configuration_completeness",
        "study_configurations",
        "completeness_score >= 0 AND completeness_score <= 100",
    )

    # 5. missing_fields — JSONB list of empty field names
    op.add_column(
        "study_configurations",
        sa.Column(
            "missing_fields",
            JSONB,
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
    )

    # 6. Indexes
    op.create_index(
        "ix_study_configurations_superseded_at",
        "study_configurations",
        ["superseded_at"],
    )
    op.create_index(
        "ix_study_configurations_source_id",
        "study_configurations",
        ["source_configuration_id"],
    )

    # 7. Back-fill: extract change_reason from existing protocol_json
    op.execute(
        """
        UPDATE study_configurations
        SET change_reason = protocol_json->>'change_reason'
        WHERE protocol_json->>'change_reason' IS NOT NULL
        """
    )

    # 8. Back-fill completeness_score
    op.execute(
        """
        UPDATE study_configurations
        SET completeness_score = (
            (CASE WHEN ml_task IS NOT NULL AND ml_task <> '' THEN 10 ELSE 0 END) +
            (CASE WHEN domain IS NOT NULL AND domain <> '' THEN 10 ELSE 0 END) +
            (CASE WHEN research_objective IS NOT NULL AND research_objective <> '' THEN 10 ELSE 0 END) +
            (CASE WHEN research_question IS NOT NULL AND research_question <> '' THEN 10 ELSE 0 END) +
            (CASE WHEN hypothesis IS NOT NULL AND hypothesis <> '' THEN 10 ELSE 0 END) +
            (CASE WHEN target_column IS NOT NULL AND target_column <> '' THEN 10 ELSE 0 END) +
            (CASE WHEN primary_metric IS NOT NULL AND primary_metric <> '' THEN 10 ELSE 0 END) +
            (CASE WHEN baseline_model IS NOT NULL AND baseline_model <> '' THEN 10 ELSE 0 END) +
            (CASE WHEN validation_strategy IS NOT NULL AND validation_strategy <> '' THEN 10 ELSE 0 END) +
            (CASE WHEN random_seed IS NOT NULL THEN 10 ELSE 0 END)
        )
        """
    )

    # 9. Back-fill missing_fields
    op.execute(
        """
        UPDATE study_configurations
        SET missing_fields = (
            CASE WHEN ml_task IS NULL OR ml_task = '' THEN '["ml_task"]'::jsonb ELSE '[]'::jsonb END ||
            CASE WHEN domain IS NULL OR domain = '' THEN '["domain"]'::jsonb ELSE '[]'::jsonb END ||
            CASE WHEN research_objective IS NULL OR research_objective = '' THEN '["research_objective"]'::jsonb ELSE '[]'::jsonb END ||
            CASE WHEN research_question IS NULL OR research_question = '' THEN '["research_question"]'::jsonb ELSE '[]'::jsonb END ||
            CASE WHEN hypothesis IS NULL OR hypothesis = '' THEN '["hypothesis"]'::jsonb ELSE '[]'::jsonb END ||
            CASE WHEN target_column IS NULL OR target_column = '' THEN '["target_column"]'::jsonb ELSE '[]'::jsonb END ||
            CASE WHEN primary_metric IS NULL OR primary_metric = '' THEN '["primary_metric"]'::jsonb ELSE '[]'::jsonb END ||
            CASE WHEN baseline_model IS NULL OR baseline_model = '' THEN '["baseline_model"]'::jsonb ELSE '[]'::jsonb END ||
            CASE WHEN validation_strategy IS NULL OR validation_strategy = '' THEN '["validation_strategy"]'::jsonb ELSE '[]'::jsonb END ||
            CASE WHEN random_seed IS NULL THEN '["random_seed"]'::jsonb ELSE '[]'::jsonb END
        )
        """
    )


def downgrade() -> None:
    op.drop_index("ix_study_configurations_source_id", table_name="study_configurations")
    op.drop_index("ix_study_configurations_superseded_at", table_name="study_configurations")
    op.drop_constraint(
        "ck_study_configuration_completeness", "study_configurations", type_="check"
    )
    op.drop_constraint(
        "fk_study_configuration_source", "study_configurations", type_="foreignkey"
    )
    op.drop_column("study_configurations", "missing_fields")
    op.drop_column("study_configurations", "completeness_score")
    op.drop_column("study_configurations", "source_configuration_id")
    op.drop_column("study_configurations", "superseded_at")
    op.drop_column("study_configurations", "change_reason")
