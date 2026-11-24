"""Submission judging orchestration service called by the Judge Worker."""
from datetime import datetime, timezone
from typing import List

from backend.app.core.database import Database
from backend.app.core.storage import BaseStorage
from judge.worker.worker import JudgeEngine, TestcaseInput


def process_submission_job(
    submission_id: int, db: Database, storage: BaseStorage
) -> None:
    sub = db.fetchone("SELECT * FROM submissions WHERE id = %s", (submission_id,))
    if not sub:
        return

    db.execute(
        "UPDATE submissions SET status = 'JUDGING' WHERE id = %s",
        (submission_id,),
    )

    problem = db.fetchone(
        "SELECT * FROM problems WHERE id = %s",
        (sub["problem_id"],),
    )
    if not problem:
        db.execute(
            """
            UPDATE submissions
            SET status = 'COMPLETED', verdict = 'IE', compile_output = 'Problem not found',
                judged_at = %s
            WHERE id = %s
            """,
            (datetime.now(timezone.utc).isoformat(), submission_id),
        )
        return

    tc_rows = db.fetchall(
        """
        SELECT t.*, COALESCE(g.points, 0) AS group_points
        FROM testcases t
        LEFT JOIN testcase_groups g ON g.id = t.group_id
        WHERE t.problem_id = %s
        ORDER BY t.order_index ASC, t.id ASC
        """,
        (problem["id"],),
    )

    source_code = storage.get_text(sub["source_storage_key"])
    checker_source = (
        storage.get_text(problem["checker_storage_key"])
        if problem.get("checker_storage_key")
        else None
    )

    tc_inputs: List[TestcaseInput] = []
    for row in tc_rows:
        tc_inputs.append(
            TestcaseInput(
                testcase_id=int(row["id"]),
                name=row["name"],
                input_data=storage.get_text(row["input_storage_key"]),
                expected_output=storage.get_text(row["output_storage_key"]),
                group_id=row["group_id"],
                group_points=int(row["group_points"] or 0),
            )
        )

    engine = JudgeEngine()
    result = engine.judge_submission(
        source_code=source_code,
        language_id=sub["language"],
        testcases=tc_inputs,
        time_limit_ms=int(problem["time_limit_ms"]),
        memory_limit_mb=int(problem["memory_limit_mb"]),
        max_points=int(problem["points"]),
        checker_type=problem.get("checker_type", "standard"),
        checker_source=checker_source,
        checker_language=problem.get("checker_language") or "python3",
    )

    # Clear prior results on rejudge and persist testcase-level results
    db.execute("DELETE FROM submission_results WHERE submission_id = %s", (submission_id,))
    for item in result.results:
        db.execute(
            """
            INSERT INTO submission_results
                (submission_id, testcase_id, verdict, execution_time_ms, memory_kb, score, checker_message)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            """,
            (
                submission_id,
                item.testcase_id,
                item.verdict,
                item.execution_time_ms,
                item.memory_kb,
                item.score,
                item.checker_message,
            ),
        )

    db.execute(
        """
        UPDATE submissions
        SET status = 'COMPLETED',
            verdict = %s,
            score = %s,
            max_score = %s,
            execution_time_ms = %s,
            memory_kb = %s,
            compile_output = %s,
            judged_at = %s
        WHERE id = %s
        """,
        (
            result.verdict,
            result.score,
            result.max_score,
            result.execution_time_ms,
            result.memory_kb,
            result.compile_output,
            datetime.now(timezone.utc).isoformat(),
            submission_id,
        ),
    )
