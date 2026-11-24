"""Submission judging orchestration service & smart retention cleanup (Neon PostgreSQL + Cloudflare R2)."""
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List

from backend.app.core.cache import app_cache, invalidate_submission_caches
from backend.app.core.database import Database
from backend.app.core.storage import BaseStorage
from judge.worker.worker import JudgeEngine, TestcaseInput

logger = logging.getLogger("noka.submissions")


def hard_delete_submission_rows(
    db: Database,
    storage: BaseStorage,
    rows: List[Dict[str, Any]],
) -> int:
    """
    Permanently deletes submission source code objects from Cloudflare R2 / storage FIRST,
    then hard-deletes rows from PostgreSQL `submissions` (cascading `submission_results`).
    """
    if not rows:
        return 0

    ids: List[int] = []
    for r in rows:
        sid = int(r["id"])
        ids.append(sid)
        key = (r.get("source_storage_key") or "").strip()
        if key and key != "pending":
            try:
                storage.delete(key)
            except Exception as exc:
                logger.warning("Failed deleting R2/storage key '%s' for sub #%s: %s", key, sid, exc)

    ph = ", ".join(["%s"] * len(ids))
    db.execute(f"DELETE FROM submissions WHERE id IN ({ph})", tuple(ids))
    return len(ids)


def _apply_submission_retention_policy(
    db: Database,
    storage: BaseStorage,
    sub: Dict[str, Any],
    problem: Dict[str, Any],
    result: Any,
    source_code: str,
    tc_rows: List[Dict[str, Any]],
    judged_at_iso: str,
) -> None:
    """
    Enforces per-problem storage retention so at most 1 submission per (user_id, problem_id)
    remains in Neon PostgreSQL and Cloudflare R2:
    - 'latest': keep the newest submission, delete all older ones from R2 + DB.
    - 'best': keep the highest-scoring submission (tie -> keep newest). If the new attempt
      scored strictly lower, cache an ephemeral 120s snapshot for UI feedback, then immediately
      delete the new attempt from R2 + DB while preserving the existing best submission.
    """
    mode = (problem.get("submission_retention_mode") or "latest").lower()
    sub_id = int(sub["id"])
    user_id = int(sub["user_id"])
    problem_id = int(sub["problem_id"])

    others = db.fetchall(
        """
        SELECT id, status, verdict, score, max_score, source_storage_key
        FROM submissions
        WHERE user_id = %s AND problem_id = %s AND id != %s
        ORDER BY id DESC
        """,
        (user_id, problem_id, sub_id),
    )
    if not others:
        return

    if mode == "best":
        other_completed = [o for o in others if (o.get("status") or "").upper() == "COMPLETED"]
        if not other_completed:
            return
        best_old = max(other_completed, key=lambda o: (int(o.get("score") or 0), int(o["id"])))
        best_old_score = int(best_old.get("score") or 0)
        new_score = int(result.score or 0)

        if new_score >= best_old_score:
            # New submission wins (or ties -> keep latest): delete all older completed ones
            hard_delete_submission_rows(db, storage, other_completed)
        else:
            # Old submission has a strictly higher score:
            # 1. Cache an ephemeral snapshot for 120s so the student's UI polling displays full feedback
            u_row = db.fetchone("SELECT username FROM users WHERE id = %s", (user_id,))
            tc_meta = {int(t["id"]): t for t in tc_rows}
            ephemeral_results = []
            for idx, item in enumerate(result.results, start=1):
                tm = tc_meta.get(int(item.testcase_id), {})
                ephemeral_results.append(
                    {
                        "id": idx,
                        "testcase_id": item.testcase_id,
                        "testcase_name": tm.get("name") or f"Test #{idx}",
                        "verdict": item.verdict,
                        "execution_time_ms": item.execution_time_ms,
                        "memory_kb": item.memory_kb,
                        "score": item.score,
                        "checker_message": item.checker_message,
                        "is_sample": bool(tm.get("is_sample")),
                        "is_hidden": bool(tm.get("is_hidden", True)),
                    }
                )
            snapshot = {
                "id": sub_id,
                "user_id": user_id,
                "username": u_row["username"] if u_row else "",
                "problem_id": problem_id,
                "problem_code": problem["code"],
                "problem_title": problem["title"],
                "contest_id": sub.get("contest_id"),
                "language": sub["language"],
                "status": "COMPLETED",
                "verdict": result.verdict,
                "score": result.score,
                "max_score": result.max_score,
                "execution_time_ms": result.execution_time_ms,
                "memory_kb": result.memory_kb,
                "compile_output": result.compile_output,
                "created_at": str(sub.get("created_at") or judged_at_iso),
                "judged_at": judged_at_iso,
                "source_code": source_code,
                "results": ephemeral_results,
                "discarded_by_retention": True,
                "retention_mode": "best",
                "kept_submission_id": int(best_old["id"]),
                "kept_score": best_old_score,
                "kept_verdict": best_old.get("verdict") or "",
            }
            app_cache.set(f"ephemeral_sub:{sub_id}", snapshot, ttl_seconds=120.0)

            # 2. Immediately delete the lower-scoring new submission (and any older duplicates) from R2 + DB
            to_delete = [sub] + [o for o in other_completed if int(o["id"]) != int(best_old["id"])]
            hard_delete_submission_rows(db, storage, to_delete)
    else:
        # Default 'latest' mode: delete all older/completed submissions for (user_id, problem_id)
        to_delete = [
            o for o in others
            if (o.get("status") or "").upper() == "COMPLETED" or int(o["id"]) < sub_id
        ]
        hard_delete_submission_rows(db, storage, to_delete)


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
        invalidate_submission_caches()
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

    judged_at_iso = datetime.now(timezone.utc).isoformat()
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
            judged_at_iso,
            submission_id,
        ),
    )

    _apply_submission_retention_policy(
        db=db,
        storage=storage,
        sub=sub,
        problem=problem,
        result=result,
        source_code=source_code,
        tc_rows=tc_rows,
        judged_at_iso=judged_at_iso,
    )
    invalidate_submission_caches()
