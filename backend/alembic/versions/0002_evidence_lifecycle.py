"""Make evidence lifecycle cascades deletion-safe.

Revision ID: 0002_evidence_lifecycle
Revises: 0001_phase1_schema
"""
from alembic import op

revision = "0002_evidence_lifecycle"
down_revision = "0001_phase1_schema"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_constraint("dataset_versions_configuration_id_fkey", "dataset_versions", type_="foreignkey")
    op.create_foreign_key("dataset_versions_configuration_id_fkey", "dataset_versions", "dataset_configurations", ["configuration_id"], ["id"], ondelete="CASCADE")
    op.drop_constraint("dataset_profile_reports_configuration_id_fkey", "dataset_profile_reports", type_="foreignkey")
    op.create_foreign_key("dataset_profile_reports_configuration_id_fkey", "dataset_profile_reports", "dataset_configurations", ["configuration_id"], ["id"], ondelete="CASCADE")
    op.drop_constraint("dataset_fingerprints_combined_fingerprint_key", "dataset_fingerprints", type_="unique")
    op.create_index("ix_dataset_fingerprints_combined_fingerprint", "dataset_fingerprints", ["combined_fingerprint"])


def downgrade() -> None:
    op.drop_index("ix_dataset_fingerprints_combined_fingerprint", table_name="dataset_fingerprints")
    op.create_unique_constraint("dataset_fingerprints_combined_fingerprint_key", "dataset_fingerprints", ["combined_fingerprint"])
    op.drop_constraint("dataset_profile_reports_configuration_id_fkey", "dataset_profile_reports", type_="foreignkey")
    op.create_foreign_key("dataset_profile_reports_configuration_id_fkey", "dataset_profile_reports", "dataset_configurations", ["configuration_id"], ["id"], ondelete="RESTRICT")
    op.drop_constraint("dataset_versions_configuration_id_fkey", "dataset_versions", type_="foreignkey")
    op.create_foreign_key("dataset_versions_configuration_id_fkey", "dataset_versions", "dataset_configurations", ["configuration_id"], ["id"], ondelete="RESTRICT")
