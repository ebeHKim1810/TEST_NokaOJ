"""Problemset & Problem CRUD API routes (/api/v1/problems)."""
import re
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Request, status

from backend.app.core.audit import record_audit_log
from backend.app.core.contest_access import can_access_contest, get_active_code_blocking_contests
from backend.app.core.database import Database, get_db
from backend.app.core.security import (
    get_client_ip,
    get_optional_user,
    is_admin,
    is_staff,
    require_roles,
)
from backend.app.core.storage import BaseStorage, get_storage
from backend.app.schemas.schemas import ProblemCreateRequest, ProblemUpdateRequest

router = APIRouter(prefix="/problems", tags=["Problems"])


def _slugify(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-") or "tag"


def _sync_tags(db: Database, problem_id: int, tags: List[str]) -> None:
    db.execute("DELETE FROM problem_tags WHERE problem_id = %s", (problem_id,))
    for raw in tags:
        name = raw.strip()
        if not name:
            continue
        slug = _slugify(name)
        existing = db.fetchone("SELECT id FROM tags WHERE slug = %s", (slug,))
        if existing:
            tag_id = int(existing["id"])
        else:
            tag_id = db.insert_returning_id(
                "INSERT INTO tags (name, slug) VALUES (%s, %s)", (name, slug)
            )
        db.execute(
            "INSERT INTO problem_tags (problem_id, tag_id) VALUES (%s, %s)",
            (problem_id, tag_id),
        )


def _get_problem_tags(db: Database, problem_id: int) -> List[str]:
    rows = db.fetchall(
        """
        SELECT t.name FROM tags t
        JOIN problem_tags pt ON pt.tag_id = t.id
        WHERE pt.problem_id = %s
        ORDER BY t.name ASC
        """,
        (problem_id,),
    )
    return [r["name"] for r in rows]


def _can_edit_problem(user: Dict[str, Any], problem: Dict[str, Any]) -> bool:
    if is_admin(user):
        return True
    return "teacher" in user.get("roles", []) and problem.get("created_by") == user["id"]


@router.get("/tags/all")
def list_tags(db: Database = Depends(get_db)):
    rows = db.fetchall("SELECT id, name, slug FROM tags ORDER BY name ASC")
    return {"items": rows}


@router.get("")
def list_problems(
    search: str = "",
    tag: str = "",
    difficulty: str = "",
    solved_status: str = "",  # solved, unsolved, attempted
    visibility: str = "",  # public, assigned, all
    sort_by: str = "code",  # code, title, difficulty, ac_rate
    sort_dir: str = "asc",
    page: int = 1,
    page_size: int = 20,
    current_user: Optional[dict] = Depends(get_optional_user),
    db: Database = Depends(get_db),
):
    page = max(1, page)
    page_size = max(1, min(100, page_size))

    where = ["p.deleted_at IS NULL"]
    params: List[Any] = []

    if not is_staff(current_user):
        if current_user:
            where.append(
                """
                (p.visibility = 'public' OR p.id IN (
                    SELECT ap.problem_id FROM assignment_problems ap
                    JOIN assignments a ON a.id = ap.assignment_id
                    JOIN classroom_students cs ON cs.classroom_id = a.classroom_id
                    WHERE cs.student_id = %s AND a.deleted_at IS NULL
                ))
                """
            )
            params.append(current_user["id"])
        else:
            where.append("p.visibility = 'public'")
    else:
        if visibility in ("public", "private", "classroom"):
            where.append("p.visibility = %s")
            params.append(visibility)

    if visibility == "assigned" and current_user:
        where.append(
            """
            p.id IN (
                SELECT ap.problem_id FROM assignment_problems ap
                JOIN assignments a ON a.id = ap.assignment_id
                JOIN classroom_students cs ON cs.classroom_id = a.classroom_id
                WHERE cs.student_id = %s AND a.deleted_at IS NULL
            )
            """
        )
        params.append(current_user["id"])

    if search:
        where.append("(p.title ILIKE %s OR p.code ILIKE %s)")
        like = f"%{search}%"
        params.extend([like, like])

    if difficulty in ("easy", "medium", "hard"):
        where.append("p.difficulty = %s")
        params.append(difficulty)

    if tag:
        where.append(
            """
            p.id IN (
                SELECT pt.problem_id FROM problem_tags pt
                JOIN tags t ON t.id = pt.tag_id
                WHERE t.slug = %s OR t.name ILIKE %s
            )
            """
        )
        params.extend([_slugify(tag), tag])

    rows = db.fetchall(
        f"""
        SELECT p.id, p.code, p.title, p.difficulty, p.points, p.visibility,
               p.time_limit_ms, p.memory_limit_mb, p.created_by, p.created_at
        FROM problems p
        WHERE {' AND '.join(where)}
        """,
        tuple(params),
    )

    enriched = []
    diff_rank = {"easy": 1, "medium": 2, "hard": 3}
    for row in rows:
        pid = int(row["id"])
        ac_row = db.fetchone(
            "SELECT COUNT(DISTINCT user_id) AS cnt FROM submissions WHERE problem_id = %s AND verdict = 'AC'",
            (pid,),
        )
        sub_row = db.fetchone(
            "SELECT COUNT(*) AS cnt FROM submissions WHERE problem_id = %s",
            (pid,),
        )
        ac_users = int(ac_row["cnt"]) if ac_row else 0
        total_subs = int(sub_row["cnt"]) if sub_row else 0
        ac_rate = round((ac_users / total_subs) * 100, 1) if total_subs > 0 else 0.0

        user_status = "unsolved"
        if current_user:
            u_ac = db.fetchone(
                "SELECT id FROM submissions WHERE problem_id = %s AND user_id = %s AND verdict = 'AC' LIMIT 1",
                (pid, current_user["id"]),
            )
            if u_ac:
                user_status = "solved"
            else:
                u_any = db.fetchone(
                    "SELECT id FROM submissions WHERE problem_id = %s AND user_id = %s LIMIT 1",
                    (pid, current_user["id"]),
                )
                if u_any:
                    user_status = "attempted"

        if solved_status == "solved" and user_status != "solved":
            continue
        if solved_status == "unsolved" and user_status == "solved":
            continue

        row["tags"] = _get_problem_tags(db, pid)
        row["ac_count"] = ac_users
        row["submission_count"] = total_subs
        row["ac_rate"] = ac_rate
        row["user_status"] = user_status
        enriched.append(row)

    reverse = sort_dir.lower() == "desc"
    if sort_by == "title":
        enriched.sort(key=lambda x: x["title"].lower(), reverse=reverse)
    elif sort_by == "difficulty":
        enriched.sort(key=lambda x: diff_rank.get(x["difficulty"], 1), reverse=reverse)
    elif sort_by == "ac_rate":
        enriched.sort(key=lambda x: x["ac_rate"], reverse=reverse)
    else:
        enriched.sort(key=lambda x: x["code"].lower(), reverse=reverse)

    total = len(enriched)
    start = (page - 1) * page_size
    return {
        "items": enriched[start : start + page_size],
        "total": total,
        "page": page,
        "page_size": page_size,
    }


@router.get("/{code_or_id}")
def get_problem(
    code_or_id: str,
    contest_id: Optional[int] = None,
    current_user: Optional[dict] = Depends(get_optional_user),
    db: Database = Depends(get_db),
    storage: BaseStorage = Depends(get_storage),
):
    if code_or_id.isdigit():
        prob = db.fetchone(
            "SELECT * FROM problems WHERE id = %s AND deleted_at IS NULL",
            (int(code_or_id),),
        )
    else:
        prob = db.fetchone(
            "SELECT * FROM problems WHERE code = %s AND deleted_at IS NULL",
            (code_or_id,),
        )
    if not prob:
        raise HTTPException(status_code=404, detail="Problem not found.")

    if prob["visibility"] != "public" and not is_staff(current_user):
        # Allow if assigned to student's classroom or part of a started accessible contest
        allowed = False
        if current_user:
            chk = db.fetchone(
                """
                SELECT 1 FROM assignment_problems ap
                JOIN assignments a ON a.id = ap.assignment_id
                JOIN classroom_students cs ON cs.classroom_id = a.classroom_id
                WHERE ap.problem_id = %s AND cs.student_id = %s AND a.deleted_at IS NULL
                LIMIT 1
                """,
                (prob["id"], current_user["id"]),
            )
            allowed = chk is not None
        if not allowed:
            now = datetime.now(timezone.utc)
            if contest_id is not None:
                c_rows = db.fetchall(
                    """
                    SELECT c.* FROM contests c
                    JOIN contest_problems cp ON cp.contest_id = c.id
                    WHERE c.id = %s AND cp.problem_id = %s AND c.deleted_at IS NULL
                    """,
                    (contest_id, prob["id"]),
                )
            else:
                c_rows = db.fetchall(
                    """
                    SELECT c.* FROM contests c
                    JOIN contest_problems cp ON cp.contest_id = c.id
                    WHERE cp.problem_id = %s AND c.deleted_at IS NULL
                    """,
                    (prob["id"],),
                )
            for c in c_rows:
                if not can_access_contest(db, c, current_user):
                    continue
                st_val = c["start_time"]
                st_dt = (
                    st_val if isinstance(st_val, datetime)
                    else datetime.fromisoformat(str(st_val).replace("Z", "+00:00"))
                )
                if not st_dt.tzinfo:
                    st_dt = st_dt.replace(tzinfo=timezone.utc)
                if now >= st_dt:
                    allowed = True
                    break
        if not allowed:
            raise HTTPException(status_code=403, detail="Access denied to this problem.")

    # Only return explicitly marked sample (non-hidden) testcases to students!
    sample_rows = db.fetchall(
        """
        SELECT id, name, input_storage_key, output_storage_key
        FROM testcases
        WHERE problem_id = %s AND is_sample = %s AND is_hidden = %s
        ORDER BY order_index ASC, id ASC
        """,
        (prob["id"], True, False),
    )
    samples = [
        {
            "id": r["id"],
            "name": r["name"],
            "input": storage.get_text(r["input_storage_key"]),
            "output": storage.get_text(r["output_storage_key"]),
        }
        for r in sample_rows
    ]

    tc_count = db.fetchone(
        "SELECT COUNT(*) AS cnt FROM testcases WHERE problem_id = %s", (prob["id"],)
    )
    # If a student opens a problem inside a RUNNING accessible contest, auto-enroll them
    # in contest_participants so contest rules (such as block_old_code) engage immediately.
    if contest_id is not None and current_user and not is_staff(current_user):
        c_row = db.fetchone(
            """
            SELECT c.* FROM contests c
            JOIN contest_problems cp ON cp.contest_id = c.id
            WHERE c.id = %s AND cp.problem_id = %s AND c.deleted_at IS NULL
            """,
            (contest_id, prob["id"]),
        )
        if c_row and can_access_contest(db, c_row, current_user):
            now_dt = datetime.now(timezone.utc)
            st_val, en_val = c_row["start_time"], c_row["end_time"]
            st_dt = (
                st_val if isinstance(st_val, datetime)
                else datetime.fromisoformat(str(st_val).replace("Z", "+00:00"))
            )
            en_dt = (
                en_val if isinstance(en_val, datetime)
                else datetime.fromisoformat(str(en_val).replace("Z", "+00:00"))
            )
            if not st_dt.tzinfo:
                st_dt = st_dt.replace(tzinfo=timezone.utc)
            if not en_dt.tzinfo:
                en_dt = en_dt.replace(tzinfo=timezone.utc)
            if st_dt <= now_dt <= en_dt:
                if not db.fetchone(
                    "SELECT 1 FROM contest_participants WHERE contest_id = %s AND user_id = %s",
                    (contest_id, current_user["id"]),
                ):
                    db.execute(
                        "INSERT INTO contest_participants (contest_id, user_id) VALUES (%s, %s)",
                        (contest_id, current_user["id"]),
                    )

    blocking = get_active_code_blocking_contests(db, current_user)
    recent_subs = []
    if current_user:
        if contest_id is not None:
            recent_subs = db.fetchall(
                """
                SELECT id, language, verdict, score, max_score, execution_time_ms, memory_kb, created_at
                FROM submissions
                WHERE problem_id = %s AND user_id = %s AND contest_id = %s
                ORDER BY id DESC
                LIMIT 10
                """,
                (prob["id"], current_user["id"], contest_id),
            )
        elif not blocking:
            recent_subs = db.fetchall(
                """
                SELECT id, language, verdict, score, max_score, execution_time_ms, memory_kb, created_at
                FROM submissions
                WHERE problem_id = %s AND user_id = %s
                ORDER BY id DESC
                LIMIT 10
                """,
                (prob["id"], current_user["id"]),
            )

    prob["tags"] = _get_problem_tags(db, int(prob["id"]))
    prob["samples"] = samples
    prob["testcase_count"] = int(tc_count["cnt"]) if tc_count else 0
    prob["recent_submissions"] = recent_subs
    prob["block_old_code"] = bool(blocking)
    prob["checker_language"] = prob.get("checker_language") or "python3"
    if is_staff(current_user):
        prob["checker_source"] = (
            storage.get_text(prob["checker_storage_key"])
            if prob.get("checker_storage_key")
            else ""
        )
    return prob


@router.post("", status_code=status.HTTP_201_CREATED)
def create_problem(
    payload: ProblemCreateRequest,
    request: Request,
    current_user: dict = Depends(require_roles("admin", "teacher")),
    db: Database = Depends(get_db),
    storage: BaseStorage = Depends(get_storage),
):
    code = (payload.code or "").strip().upper()
    if not code:
        cnt = db.fetchone("SELECT COUNT(*) AS cnt FROM problems")
        nxt = (int(cnt["cnt"]) if cnt else 0) + 1
        code = f"NK{nxt:04d}"
    if db.fetchone("SELECT id FROM problems WHERE code = %s", (code,)):
        raise HTTPException(status_code=409, detail=f"Problem code '{code}' already exists.")

    checker_key = None
    checker_lang = payload.checker_language or "python3"
    if payload.checker_type == "custom":
        if not payload.checker_source or not payload.checker_source.strip():
            raise HTTPException(
                status_code=400,
                detail="Vui lòng dán mã nguồn trình chấm cho loại trình chấm Chấp nhận mọi đáp án hợp lệ.",
            )
        ext = "py" if checker_lang == "python3" else "cpp"
        checker_key = f"checkers/{code}_checker.{ext}"
        storage.put_text(checker_key, payload.checker_source)

    pid = db.insert_returning_id(
        """
        INSERT INTO problems (
            code, title, statement_md, input_description, output_description,
            constraints_md, sample_input, sample_output, time_limit_ms,
            memory_limit_mb, points, difficulty, visibility, checker_type,
            checker_language, checker_storage_key, created_by
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """,
        (
            code,
            payload.title,
            payload.statement_md,
            payload.input_description,
            payload.output_description,
            payload.constraints_md,
            payload.sample_input,
            payload.sample_output,
            payload.time_limit_ms,
            payload.memory_limit_mb,
            payload.points,
            payload.difficulty,
            payload.visibility,
            payload.checker_type,
            checker_lang,
            checker_key,
            current_user["id"],
        ),
    )
    _sync_tags(db, pid, payload.tags)
    record_audit_log(
        db, current_user["id"], "problem.create", "problem", str(pid), get_client_ip(request), {"code": code}
    )
    prob = db.fetchone("SELECT * FROM problems WHERE id = %s", (pid,))
    prob["tags"] = _get_problem_tags(db, pid)
    return prob


@router.put("/{problem_id}")
def update_problem(
    problem_id: int,
    payload: ProblemUpdateRequest,
    request: Request,
    current_user: dict = Depends(require_roles("admin", "teacher")),
    db: Database = Depends(get_db),
    storage: BaseStorage = Depends(get_storage),
):
    prob = db.fetchone("SELECT * FROM problems WHERE id = %s AND deleted_at IS NULL", (problem_id,))
    if not prob:
        raise HTTPException(status_code=404, detail="Problem not found.")
    if not _can_edit_problem(current_user, prob):
        raise HTTPException(status_code=403, detail="You can only edit problems you manage.")

    data = (payload.model_dump(exclude_none=True) if hasattr(payload, "model_dump") else payload.dict(exclude_none=True))
    tags = data.pop("tags", None)
    checker_src = data.pop("checker_source", None)
    eff_checker_type = data.get("checker_type", prob.get("checker_type") or "standard")
    eff_checker_lang = data.get("checker_language", prob.get("checker_language") or "python3")
    if eff_checker_type == "custom":
        if checker_src is not None:
            if not checker_src.strip():
                raise HTTPException(
                    status_code=400,
                    detail="Vui lòng dán mã nguồn trình chấm cho loại trình chấm Chấp nhận mọi đáp án hợp lệ.",
                )
            ext = "py" if eff_checker_lang == "python3" else "cpp"
            key = f"checkers/{prob['code']}_checker.{ext}"
            storage.put_text(key, checker_src)
            data["checker_storage_key"] = key
        elif not prob.get("checker_storage_key"):
            raise HTTPException(
                status_code=400,
                detail="Vui lòng dán mã nguồn trình chấm cho loại trình chấm Chấp nhận mọi đáp án hợp lệ.",
            )
    elif checker_src is not None and checker_src.strip():
        ext = "py" if eff_checker_lang == "python3" else "cpp"
        key = f"checkers/{prob['code']}_checker.{ext}"
        storage.put_text(key, checker_src)
        data["checker_storage_key"] = key

    if data:
        data["updated_at"] = datetime.now(timezone.utc).isoformat()
        sets = ", ".join(f"{k} = %s" for k in data.keys())
        db.execute(f"UPDATE problems SET {sets} WHERE id = %s", (*data.values(), problem_id))

    if tags is not None:
        _sync_tags(db, problem_id, tags)

    record_audit_log(
        db, current_user["id"], "problem.update", "problem", str(problem_id), get_client_ip(request)
    )
    updated = db.fetchone("SELECT * FROM problems WHERE id = %s", (problem_id,))
    updated["tags"] = _get_problem_tags(db, problem_id)
    return updated


@router.delete("/{problem_id}")
def delete_problem(
    problem_id: int,
    request: Request,
    current_user: dict = Depends(require_roles("admin", "teacher")),
    db: Database = Depends(get_db),
):
    prob = db.fetchone("SELECT * FROM problems WHERE id = %s AND deleted_at IS NULL", (problem_id,))
    if not prob:
        raise HTTPException(status_code=404, detail="Problem not found.")
    if not _can_edit_problem(current_user, prob):
        raise HTTPException(status_code=403, detail="Permission denied.")

    db.execute(
        "UPDATE problems SET deleted_at = %s WHERE id = %s",
        (datetime.now(timezone.utc).isoformat(), problem_id),
    )
    record_audit_log(
        db, current_user["id"], "problem.delete", "problem", str(problem_id), get_client_ip(request)
    )
    return {"deleted": True, "id": problem_id}
