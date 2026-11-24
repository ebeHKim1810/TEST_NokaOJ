"""Submissions & Run Sample API (/api/v1/submissions)."""
from datetime import datetime, timezone
from typing import Any, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Request, status

from backend.app.core.audit import record_audit_log
from backend.app.core.cache import app_cache, invalidate_submission_caches
from backend.app.core.contest_access import ensure_contest_access, get_active_code_blocking_contests
from backend.app.core.database import Database, get_db
from backend.app.core.problem_access import ensure_problem_access
from backend.app.core.queue import enqueue_submission_job, judge_execution_slot
from backend.app.core.security import (
    get_client_ip,
    get_current_user,
    get_optional_user,
    is_staff,
    require_roles,
)
from backend.app.core.storage import BaseStorage, get_storage
from backend.app.schemas.schemas import RunSampleRequest, SubmissionCreateRequest
from backend.app.services.submission_service import hard_delete_submission_rows
from judge.languages.registry import list_languages
from judge.worker.worker import JudgeEngine

router = APIRouter(prefix="/submissions", tags=["Submissions"])


def _parse_iso(dt_str: Any) -> datetime:
    if isinstance(dt_str, datetime):
        return dt_str if dt_str.tzinfo else dt_str.replace(tzinfo=timezone.utc)
    s = str(dt_str).replace("Z", "+00:00")
    dt = datetime.fromisoformat(s)
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


@router.get("/languages")
def get_supported_languages():
    return {"items": list_languages()}


@router.post("/run-sample")
def run_sample(
    payload: RunSampleRequest,
    current_user: dict = Depends(get_current_user),
    db: Database = Depends(get_db),
    storage: BaseStorage = Depends(get_storage),
):
    prob = db.fetchone(
        "SELECT * FROM problems WHERE id = %s AND deleted_at IS NULL", (payload.problem_id,)
    )
    if not prob:
        raise HTTPException(status_code=404, detail="Problem not found.")
    ensure_problem_access(db, prob, current_user)

    sample_in = payload.custom_input if payload.custom_input is not None else prob["sample_input"]
    expected = None if payload.custom_input is not None else prob["sample_output"]
    checker_source = (
        storage.get_text(prob["checker_storage_key"])
        if prob.get("checker_storage_key")
        else None
    )

    engine = JudgeEngine()
    with judge_execution_slot():
        return engine.run_sample(
            source_code=payload.source_code,
            language_id=payload.language,
            sample_input=sample_in,
            expected_output=expected,
            time_limit_ms=int(prob["time_limit_ms"]),
            memory_limit_mb=int(prob["memory_limit_mb"]),
            checker_type=prob.get("checker_type", "standard"),
            checker_source=checker_source,
            checker_language=prob.get("checker_language") or "python3",
        )


@router.post("", status_code=status.HTTP_201_CREATED)
def create_submission(
    payload: SubmissionCreateRequest,
    request: Request,
    current_user: dict = Depends(get_current_user),
    db: Database = Depends(get_db),
    storage: BaseStorage = Depends(get_storage),
):
    prob = db.fetchone(
        "SELECT * FROM problems WHERE id = %s AND deleted_at IS NULL", (payload.problem_id,)
    )
    if not prob:
        raise HTTPException(status_code=404, detail="Problem not found.")
    ensure_problem_access(db, prob, current_user, contest_id=payload.contest_id)

    # Validate contest window & participation when submitting to a contest
    if payload.contest_id is not None:
        contest = db.fetchone(
            "SELECT * FROM contests WHERE id = %s AND deleted_at IS NULL", (payload.contest_id,)
        )
        if not contest:
            raise HTTPException(status_code=404, detail="Contest not found.")
        ensure_contest_access(db, contest, current_user)
        in_contest = db.fetchone(
            "SELECT 1 FROM contest_problems WHERE contest_id = %s AND problem_id = %s",
            (payload.contest_id, payload.problem_id),
        )
        if not in_contest:
            raise HTTPException(status_code=400, detail="Bài tập không thuộc kỳ thi này.")
        now = datetime.now(timezone.utc)
        if not is_staff(current_user):
            if now < _parse_iso(contest["start_time"]):
                raise HTTPException(status_code=403, detail="Kỳ thi chưa bắt đầu.")
            if now > _parse_iso(contest["end_time"]):
                raise HTTPException(status_code=403, detail="Kỳ thi đã kết thúc.")
            reg = db.fetchone(
                "SELECT 1 FROM contest_participants WHERE contest_id = %s AND user_id = %s",
                (payload.contest_id, current_user["id"]),
            )
            if not reg:
                # Auto-register allowed student so submitting directly from a contest problem records on scoreboard
                db.execute(
                    "INSERT INTO contest_participants (contest_id, user_id) VALUES (%s, %s)",
                    (payload.contest_id, current_user["id"]),
                )

    src_bytes = payload.source_code.encode("utf-8")
    sub_id = db.insert_returning_id(
        """
        INSERT INTO submissions (
            user_id, problem_id, contest_id, language,
            source_storage_key, source_size_bytes, status, verdict, max_score
        ) VALUES (%s, %s, %s, %s, %s, %s, 'PENDING', 'PENDING', %s)
        """,
        (
            current_user["id"],
            payload.problem_id,
            payload.contest_id,
            payload.language,
            "pending",
            len(src_bytes),
            prob["points"],
        ),
    )
    src_key = f"submissions/sub_{sub_id}.src"
    storage.put_bytes(src_key, src_bytes)
    db.execute("UPDATE submissions SET source_storage_key = %s WHERE id = %s", (src_key, sub_id))

    enqueue_submission_job(sub_id, db, storage)
    record_audit_log(
        db, current_user["id"], "submission.create", "submission", str(sub_id), get_client_ip(request)
    )
    sub = db.fetchone("SELECT * FROM submissions WHERE id = %s", (sub_id,))
    if not sub:
        ephemeral = app_cache.get(f"ephemeral_sub:{sub_id}")
        if ephemeral:
            return dict(ephemeral)
        return {
            "id": sub_id,
            "user_id": current_user["id"],
            "problem_id": payload.problem_id,
            "contest_id": payload.contest_id,
            "language": payload.language,
            "status": "COMPLETED",
            "verdict": "PENDING",
            "score": 0,
            "max_score": prob["points"],
        }
    return sub


@router.get("")
def list_submissions(
    username: str = "",
    problem_code: str = "",
    problem_id: Optional[int] = None,
    language: str = "",
    verdict: str = "",
    date_from: str = "",
    contest_id: Optional[int] = None,
    page: int = 1,
    page_size: int = 25,
    current_user: Optional[dict] = Depends(get_optional_user),
    db: Database = Depends(get_db),
):
    page = max(1, page)
    page_size = max(1, min(100, page_size))

    where = ["1=1"]
    params: List[Any] = []

    blocking = get_active_code_blocking_contests(db, current_user)
    active_ids = [c["id"] for c in blocking]
    if blocking and current_user:
        # While in an active contest with block_old_code enabled, students can ONLY
        # view submissions made inside their active contest(s), hiding all past history.
        placeholders = ", ".join(["%s"] * len(active_ids))
        where.append(f"s.contest_id IN ({placeholders})")
        params.extend(active_ids)
        where.append("s.user_id = %s")
        params.append(current_user["id"])

    if username:
        where.append("u.username ILIKE %s")
        params.append(f"%{username}%")
    if problem_code:
        where.append("p.code ILIKE %s")
        params.append(f"%{problem_code}%")
    if problem_id is not None:
        where.append("s.problem_id = %s")
        params.append(problem_id)
    if language:
        where.append("s.language = %s")
        params.append(language)
    if verdict:
        where.append("s.verdict = %s")
        params.append(verdict.upper())
    if date_from:
        where.append("s.created_at >= %s")
        params.append(date_from)
    if contest_id is not None:
        where.append("s.contest_id = %s")
        params.append(contest_id)

    total_row = db.fetchone(
        f"""
        SELECT COUNT(*) AS cnt
        FROM submissions s
        JOIN users u ON u.id = s.user_id
        JOIN problems p ON p.id = s.problem_id
        WHERE {' AND '.join(where)}
        """,
        tuple(params),
    )
    rows = db.fetchall(
        f"""
        SELECT s.id, s.user_id, u.username, s.problem_id, p.code AS problem_code, p.title AS problem_title,
               s.contest_id, s.language, s.status, s.verdict, s.score, s.max_score,
               s.execution_time_ms, s.memory_kb, s.created_at, s.judged_at
        FROM submissions s
        JOIN users u ON u.id = s.user_id
        JOIN problems p ON p.id = s.problem_id
        WHERE {' AND '.join(where)}
        ORDER BY s.id DESC
        LIMIT %s OFFSET %s
        """,
        tuple(params + [page_size, (page - 1) * page_size]),
    )
    active_id_set = set(active_ids)
    for r in rows:
        r["code_blocked"] = bool(blocking) and (
            r.get("contest_id") is None or int(r["contest_id"]) not in active_id_set
        )
    return {
        "items": rows,
        "total": int(total_row["cnt"]) if total_row else 0,
        "page": page,
        "page_size": page_size,
        "old_code_blocked": bool(blocking),
        "blocking_contests": [c["title"] for c in blocking],
    }


@router.get("/{submission_id}")
def get_submission_detail(
    submission_id: int,
    current_user: dict = Depends(get_current_user),
    db: Database = Depends(get_db),
    storage: BaseStorage = Depends(get_storage),
):
    sub = db.fetchone(
        """
        SELECT s.*, u.username, p.code AS problem_code, p.title AS problem_title
        FROM submissions s
        JOIN users u ON u.id = s.user_id
        JOIN problems p ON p.id = s.problem_id
        WHERE s.id = %s
        """,
        (submission_id,),
    )
    staff = is_staff(current_user)
    if not sub:
        # Check ephemeral cache for a lower-scoring submission discarded by 'best' retention mode
        ephemeral = app_cache.get(f"ephemeral_sub:{submission_id}")
        if not ephemeral:
            raise HTTPException(status_code=404, detail="Submission not found.")
        if not staff and int(ephemeral["user_id"]) != int(current_user["id"]):
            raise HTTPException(status_code=403, detail="You can only view your own submissions.")
        sanitized_eph = []
        for idx, r in enumerate(ephemeral.get("results", []), start=1):
            if staff or (r.get("is_sample") and not r.get("is_hidden")):
                sanitized_eph.append(r)
            else:
                sanitized_eph.append(
                    {
                        "id": r.get("id", idx),
                        "testcase_index": idx,
                        "testcase_name": f"Test #{idx}",
                        "verdict": r["verdict"],
                        "execution_time_ms": r["execution_time_ms"],
                        "memory_kb": r["memory_kb"],
                        "score": r["score"],
                        "is_hidden": True,
                        "checker_message": "Hidden testcase details are protected.",
                    }
                )
        payload = dict(ephemeral)
        payload["results"] = sanitized_eph
        return payload

    if not staff and int(sub["user_id"]) != int(current_user["id"]):
        raise HTTPException(status_code=403, detail="You can only view your own submissions.")

    if not staff:
        blocking = get_active_code_blocking_contests(db, current_user)
        if blocking:
            active_ids = {c["id"] for c in blocking}
            if sub.get("contest_id") is None or int(sub["contest_id"]) not in active_ids:
                raise HTTPException(
                    status_code=403,
                    detail="Không được phép xem lại code cũ trong lúc đang tham gia kỳ thi.",
                )

    sub["source_code"] = storage.get_text(sub["source_storage_key"])

    raw_results = db.fetchall(
        """
        SELECT sr.id, sr.testcase_id, sr.verdict, sr.execution_time_ms, sr.memory_kb,
               sr.score, sr.checker_message, t.name AS testcase_name,
               t.is_sample, t.is_hidden
        FROM submission_results sr
        JOIN testcases t ON t.id = sr.testcase_id
        WHERE sr.submission_id = %s
        ORDER BY t.order_index ASC, sr.id ASC
        """,
        (submission_id,),
    )

    # Strictly redact hidden testcase details/messages for students
    sanitized_results = []
    for idx, r in enumerate(raw_results, start=1):
        if staff or (r["is_sample"] and not r["is_hidden"]):
            sanitized_results.append(r)
        else:
            sanitized_results.append(
                {
                    "id": r["id"],
                    "testcase_index": idx,
                    "testcase_name": f"Test #{idx}",
                    "verdict": r["verdict"],
                    "execution_time_ms": r["execution_time_ms"],
                    "memory_kb": r["memory_kb"],
                    "score": r["score"],
                    "is_hidden": True,
                    "checker_message": "Hidden testcase details are protected.",
                }
            )
    sub["results"] = sanitized_results
    return sub


@router.post("/{submission_id}/rejudge")
def rejudge_submission(
    submission_id: int,
    current_user: dict = Depends(require_roles("admin", "teacher")),
    db: Database = Depends(get_db),
    storage: BaseStorage = Depends(get_storage),
):
    sub = db.fetchone("SELECT id FROM submissions WHERE id = %s", (submission_id,))
    if not sub:
        raise HTTPException(status_code=404, detail="Submission not found.")
    db.execute("UPDATE submissions SET status = 'PENDING', verdict = 'PENDING' WHERE id = %s", (submission_id,))
    enqueue_submission_job(submission_id, db, storage)
    return db.fetchone("SELECT * FROM submissions WHERE id = %s", (submission_id,))


@router.delete("/{submission_id}")
def delete_submission(
    submission_id: int,
    request: Request,
    current_user: dict = Depends(get_current_user),
    db: Database = Depends(get_db),
    storage: BaseStorage = Depends(get_storage),
):
    """Permanently delete a single submission from Cloudflare R2 and PostgreSQL."""
    sub = db.fetchone(
        "SELECT id, user_id, problem_id, source_storage_key FROM submissions WHERE id = %s",
        (submission_id,),
    )
    if not sub:
        raise HTTPException(status_code=404, detail="Submission not found.")

    if not is_staff(current_user) and int(sub["user_id"]) != int(current_user["id"]):
        raise HTTPException(status_code=403, detail="Bạn chỉ có thể xóa bài nộp của chính mình.")

    hard_delete_submission_rows(db, storage, [sub])
    record_audit_log(
        db,
        current_user["id"],
        "submission.delete",
        "submission",
        str(submission_id),
        get_client_ip(request),
        {"problem_id": sub["problem_id"], "owner_user_id": sub["user_id"]},
    )
    invalidate_submission_caches()
    return {"deleted": True, "id": submission_id}


@router.delete("")
def bulk_delete_submissions(
    request: Request,
    problem_id: Optional[int] = None,
    problem_code: str = "",
    user_id: Optional[int] = None,
    username: str = "",
    delete_all: bool = False,
    current_user: dict = Depends(require_roles("admin", "teacher")),
    db: Database = Depends(get_db),
    storage: BaseStorage = Depends(get_storage),
):
    """
    Bulk hard-delete submission history from Cloudflare R2 + PostgreSQL (Admin/Teacher only).
    Requires at least one filter (problem_id, problem_code, user_id, username) or delete_all=true.
    """
    where: List[str] = []
    params: List[Any] = []

    if problem_id is not None:
        where.append("s.problem_id = %s")
        params.append(problem_id)
    if problem_code.strip():
        where.append("p.code ILIKE %s")
        params.append(problem_code.strip())
    if user_id is not None:
        where.append("s.user_id = %s")
        params.append(user_id)
    if username.strip():
        where.append("u.username ILIKE %s")
        params.append(username.strip())

    if not where and not delete_all:
        raise HTTPException(
            status_code=400,
            detail="Vui lòng chọn điều kiện lọc (bài tập / học sinh) hoặc xác nhận delete_all=true.",
        )

    where_sql = f"WHERE {' AND '.join(where)}" if where else ""
    rows = db.fetchall(
        f"""
        SELECT s.id, s.source_storage_key
        FROM submissions s
        JOIN problems p ON p.id = s.problem_id
        JOIN users u ON u.id = s.user_id
        {where_sql}
        """,
        tuple(params),
    )
    deleted_count = hard_delete_submission_rows(db, storage, rows)
    record_audit_log(
        db,
        current_user["id"],
        "submission.bulk_delete",
        "submission",
        "bulk",
        get_client_ip(request),
        {
            "deleted_count": deleted_count,
            "problem_id": problem_id,
            "problem_code": problem_code,
            "user_id": user_id,
            "username": username,
            "delete_all": delete_all,
        },
    )
    invalidate_submission_caches()
    return {"deleted_count": deleted_count}
