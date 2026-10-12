"""Persist reference decisions and unique per-user law notifications."""
from alembic import op
import sqlalchemy as sa

revision = "003"
down_revision = "002"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table("law_reference_assessments",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("change_id", sa.Integer(), sa.ForeignKey("law_changes.id", ondelete="CASCADE"), nullable=False),
        sa.Column("reference_id", sa.Integer(), sa.ForeignKey("chat_law_references.id", ondelete="CASCADE"), nullable=False),
        sa.Column("status", sa.String(30), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("conditions", sa.JSON(), nullable=False),
        sa.Column("law_analysis", sa.JSON(), nullable=True),
        sa.Column("failure_stage", sa.String(50), nullable=True),
        sa.Column("error_code", sa.String(100), nullable=True),
        sa.Column("model", sa.String(100), nullable=False),
        sa.Column("input_fingerprint", sa.String(64), nullable=False),
        sa.Column("checked_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("notification_id", sa.Integer(), sa.ForeignKey("notifications.id", ondelete="SET NULL"), nullable=True),
        sa.UniqueConstraint("change_id", "reference_id", name="uq_law_reference_assessment"))
    op.create_index("ix_law_reference_assessments_change_id", "law_reference_assessments", ["change_id"])
    op.create_index("ix_law_reference_assessments_reference_id", "law_reference_assessments", ["reference_id"])
    op.create_table("law_change_deliveries",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("change_id", sa.Integer(), sa.ForeignKey("law_changes.id", ondelete="CASCADE"), nullable=False),
        sa.Column("notification_id", sa.Integer(), sa.ForeignKey("notifications.id", ondelete="CASCADE"), nullable=False, unique=True),
        sa.Column("payload_meta", sa.JSON(), nullable=False),
        sa.UniqueConstraint("user_id", "change_id", name="uq_law_change_delivery"))
    op.create_index("ix_law_change_deliveries_user_id", "law_change_deliveries", ["user_id"])
    op.create_index("ix_law_change_deliveries_change_id", "law_change_deliveries", ["change_id"])


def downgrade():
    op.drop_table("law_change_deliveries")
    op.drop_table("law_reference_assessments")
