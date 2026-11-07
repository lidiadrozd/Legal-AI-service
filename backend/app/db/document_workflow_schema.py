"""Compatibility upgrade for installations using create_all rather than Alembic."""
from sqlalchemy import inspect, text


def ensure_document_workflow_column(connection):
    columns = {item["name"] for item in inspect(connection).get_columns("chat_sessions")}
    if "document_workflow" not in columns:
        if connection.dialect.name == "postgresql":
            connection.execute(text("ALTER TABLE chat_sessions ADD COLUMN IF NOT EXISTS document_workflow JSON"))
        else:
            connection.execute(text("ALTER TABLE chat_sessions ADD COLUMN document_workflow JSON"))
