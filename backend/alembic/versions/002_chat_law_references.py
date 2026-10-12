"""Add explicit links from chat answers and changes to legal norms."""
from alembic import op
import sqlalchemy as sa

revision = "002"
down_revision = "001"
branch_labels = None
depends_on = None


def norm_columns():
    return [sa.Column("document_key", sa.String(200), nullable=False),
            sa.Column("article", sa.String(50), nullable=False, server_default=""),
            sa.Column("part", sa.String(50), nullable=False, server_default=""),
            sa.Column("point", sa.String(50), nullable=False, server_default="")]


def upgrade():
    op.create_table("chat_law_references",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("chat_id", sa.Integer(), sa.ForeignKey("chat_sessions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("user_message_id", sa.Integer(), sa.ForeignKey("messages.id", ondelete="CASCADE"), nullable=False),
        sa.Column("assistant_message_id", sa.Integer(), sa.ForeignKey("messages.id", ondelete="CASCADE"), nullable=False),
        *norm_columns(),
        sa.Column("source_url", sa.String(1000), nullable=False),
        sa.Column("source_revision", sa.String(100), nullable=False),
        sa.Column("source_sha256", sa.String(64), nullable=False),
        sa.Column("source_text", sa.Text(), nullable=False),
        sa.Column("situation_excerpt", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("assistant_message_id", "document_key", "article", "part", "point", name="uq_chat_law_reference"))
    op.create_index("ix_chat_law_references_chat_id", "chat_law_references", ["chat_id"])
    op.create_index("ix_chat_law_references_document_key", "chat_law_references", ["document_key"])
    op.create_table("law_change_norms",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("change_id", sa.Integer(), sa.ForeignKey("law_changes.id", ondelete="CASCADE"), nullable=False),
        *norm_columns(),
        sa.UniqueConstraint("change_id", "document_key", "article", "part", "point", name="uq_law_change_norm"))
    op.create_index("ix_law_change_norms_change_id", "law_change_norms", ["change_id"])
    op.create_index("ix_law_change_norms_document_key", "law_change_norms", ["document_key"])


def downgrade():
    op.drop_table("law_change_norms")
    op.drop_table("chat_law_references")
