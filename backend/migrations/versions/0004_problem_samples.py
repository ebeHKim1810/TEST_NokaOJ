"""Add JSONB samples column to problems table and backfill existing single-sample problems.

Revision ID: 0004_problem_samples
Revises: 0003_problem_explanation
Create Date: 2026-11-25
"""
from alembic import op

revision = "0004_problem_samples"
down_revision = "0003_problem_explanation"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE problems
        ADD COLUMN IF NOT EXISTS samples JSONB NOT NULL DEFAULT '[]'::jsonb;
        """
    )
    # Backfill existing problems that had legacy sample_input/sample_output into samples[0]
    op.execute(
        """
        UPDATE problems
        SET samples = jsonb_build_array(
            jsonb_build_object(
                'input', COALESCE(sample_input, ''),
                'output', COALESCE(sample_output, ''),
                'explanation', COALESCE(explanation, '')
            )
        )
        WHERE (samples IS NULL OR samples = '[]'::jsonb)
          AND (
              COALESCE(BTRIM(sample_input), '') <> ''
              OR COALESCE(BTRIM(sample_output), '') <> ''
          );
        """
    )


def downgrade() -> None:
    op.execute("ALTER TABLE problems DROP COLUMN IF EXISTS samples;")
