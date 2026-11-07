"""Persist structured document interviews across chat turns."""
from alembic import op
import sqlalchemy as sa

revision = "005"
down_revision = "004"
branch_labels = None
depends_on = None


def upgrade():
    from app.db.document_workflow_schema import ensure_document_workflow_column
    ensure_document_workflow_column(op.get_bind())


def downgrade():
    op.drop_column("chat_sessions", "document_workflow")
