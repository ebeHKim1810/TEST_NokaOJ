"""Initial Noka JUDGE schema (20 normalized tables, constraints, indexes, default roles).

Revision ID: 0001_initial_schema
Revises:
Create Date: 2026-11-23
"""
import os
from alembic import op

revision = "0001_initial_schema"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    schema_path = os.path.abspath(
        os.path.join(os.path.dirname(__file__), "..", "..", "..", "database", "init", "01_schema.sql")
    )
    with open(schema_path, "r", encoding="utf-8") as f:
        sql = f.read()
    op.execute(sql)


def downgrade() -> None:
    tables = [
        "system_settings",
        "audit_logs",
        "announcements",
        "submission_results",
        "submissions",
        "contest_participants",
        "contest_problems",
        "contests",
        "assignment_problems",
        "assignments",
        "classroom_students",
        "classrooms",
        "testcases",
        "testcase_groups",
        "problem_tags",
        "problems",
        "tags",
        "user_roles",
        "users",
        "roles",
    ]
    for t in tables:
        op.execute(f"DROP TABLE IF EXISTS {t} CASCADE;")
