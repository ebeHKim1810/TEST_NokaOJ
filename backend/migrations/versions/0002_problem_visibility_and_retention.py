"""Add problem_allowed_users table, hidden visibility support, and submission_retention_mode on problems.

Revision ID: 0002_visibility_retention
Revises: 0001_initial_schema
Create Date: 2026-11-25
"""
from alembic import op

revision = "0002_visibility_retention"
down_revision = "0001_initial_schema"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE problems
        ADD COLUMN IF NOT EXISTS submission_retention_mode VARCHAR(16) NOT NULL DEFAULT 'latest';
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS problem_allowed_users (
            problem_id INTEGER NOT NULL REFERENCES problems(id) ON DELETE CASCADE,
            user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            added_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (problem_id, user_id)
        );
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_problem_allowed_users_user
        ON problem_allowed_users(user_id, problem_id);
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_problem_allowed_users_user;")
    op.execute("DROP TABLE IF EXISTS problem_allowed_users;")
    op.execute("ALTER TABLE problems DROP COLUMN IF EXISTS submission_retention_mode;")
