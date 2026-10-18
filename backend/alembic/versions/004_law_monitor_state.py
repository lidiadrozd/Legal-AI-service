"""Durable checkpoints for law-source recovery."""
from alembic import op
import sqlalchemy as sa
revision = "004"
down_revision = "003"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table("law_monitor_states",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("source_url", sa.String(1000), unique=True, nullable=False),
        sa.Column("last_attempt_at", sa.DateTime(timezone=True)),
        sa.Column("last_success_at", sa.DateTime(timezone=True)),
        sa.Column("last_error", sa.String(100)),
        sa.Column("coverage_gap", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("progress", sa.JSON(), nullable=False))


def downgrade():
    op.drop_table("law_monitor_states")
