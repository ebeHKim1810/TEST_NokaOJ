"""Add optional Markdown/LaTeX explanation column to problems table.

Revision ID: 0003_problem_explanation
Revises: 0002_visibility_retention
Create Date: 2026-11-25
"""
from alembic import op

revision = "0003_problem_explanation"
down_revision = "0002_visibility_retention"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE problems
        ADD COLUMN IF NOT EXISTS explanation TEXT NULL;
        """
    )


def downgrade() -> None:
    op.execute("ALTER TABLE problems DROP COLUMN IF EXISTS explanation;")
