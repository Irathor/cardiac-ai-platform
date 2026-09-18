"""EPIC-18 follow-up: track which language a cached LLM explanation was written in

Adds llm_explanation_language (nullable, "en"/"es") so switching the UI's
language toggle can tell a stale-language cached explanation apart from a
fresh one in the requested language, instead of serving whichever text
happens to be cached regardless of language — see
app.services.llm_explanation_service.SUPPORTED_LANGUAGES.

Revision ID: 0012
Revises: 0011
Create Date: 2026-09-18
"""
import sqlalchemy as sa
from alembic import op

revision = "0012"
down_revision = "0011"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("ai_analyses", sa.Column("llm_explanation_language", sa.String(10), nullable=True))


def downgrade() -> None:
    op.drop_column("ai_analyses", "llm_explanation_language")
