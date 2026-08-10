"""Add report foreign keys to AI explanations.

Revision ID: 0003_ai_source_foreign_keys
Revises: 0002_evidence_lifecycle
"""
from alembic import op
import sqlalchemy as sa

revision = "0003_ai_source_foreign_keys"
down_revision = "0002_evidence_lifecycle"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("ai_generated_explanations", sa.Column("semantic_diff_report_id", sa.Integer(), nullable=True))
    op.add_column("ai_generated_explanations", sa.Column("profile_report_id", sa.Integer(), nullable=True))
    op.add_column("ai_generated_explanations", sa.Column("diagnosis_report_id", sa.Integer(), nullable=True))
    op.create_foreign_key("fk_ai_semantic_diff", "ai_generated_explanations", "semantic_diff_reports", ["semantic_diff_report_id"], ["id"], ondelete="CASCADE")
    op.create_foreign_key("fk_ai_profile", "ai_generated_explanations", "dataset_profile_reports", ["profile_report_id"], ["id"], ondelete="CASCADE")
    op.create_foreign_key("fk_ai_diagnosis", "ai_generated_explanations", "diagnosis_reports", ["diagnosis_report_id"], ["id"], ondelete="CASCADE")


def downgrade() -> None:
    for constraint in ("fk_ai_diagnosis", "fk_ai_profile", "fk_ai_semantic_diff"):
        op.drop_constraint(constraint, "ai_generated_explanations", type_="foreignkey")
    for column in ("diagnosis_report_id", "profile_report_id", "semantic_diff_report_id"):
        op.drop_column("ai_generated_explanations", column)
