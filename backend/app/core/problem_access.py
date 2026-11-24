"""Shared problem visibility & access helpers (public, private + allowed users, hidden)."""
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import HTTPException

from backend.app.core.contest_access import can_access_contest
from backend.app.core.database import Database
from backend.app.core.security import is_staff


def get_problem_allowed_users(db: Database, problem_id: int) -> List[Dict[str, Any]]:
    return db.fetchall(
        """
        SELECT u.id, u.username, u.full_name, u.email
        FROM problem_allowed_users pau
        JOIN users u ON u.id = pau.user_id
        WHERE pau.problem_id = %s AND u.deleted_at IS NULL
        ORDER BY u.full_name ASC, u.username ASC
        """,
        (problem_id,),
    )


def sync_problem_allowed_users(
    db: Database, problem_id: int, user_ids: List[int]
) -> List[int]:
    unique_ids = list(dict.fromkeys(int(uid) for uid in user_ids if int(uid) > 0))
    db.execute("DELETE FROM problem_allowed_users WHERE problem_id = %s", (problem_id,))
    if not unique_ids:
        return []

    ph = ", ".join(["%s"] * len(unique_ids))
    valid_rows = db.fetchall(
        f"SELECT id FROM users WHERE id IN ({ph}) AND deleted_at IS NULL",
        tuple(unique_ids),
    )
    valid_ids = [int(r["id"]) for r in valid_rows]
    for uid in valid_ids:
        db.execute(
            "INSERT INTO problem_allowed_users (problem_id, user_id) VALUES (%s, %s)",
            (problem_id, uid),
        )
    return valid_ids


def can_access_problem(
    db: Database,
    prob: Dict[str, Any],
    user: Optional[Dict[str, Any]],
    contest_id: Optional[int] = None,
) -> bool:
    """
    Checks whether `user` can view/submit `prob`:
    - Admin/Teacher: always allowed.
    - hidden: completely hidden from students (never allowed).
    - public: allowed for everyone.
    - private: allowed if user is in problem_allowed_users (or via an active accessible contest).
    - classroom (legacy): allowed if assigned to student's classroom (or active accessible contest).
    """
    if is_staff(user):
        return True

    vis = (prob.get("visibility") or "public").lower()
    if vis == "hidden":
        return False
    if vis == "public":
        return True

    pid = int(prob["id"])

    if user:
        uid = int(user["id"])
        if vis == "private":
            direct = db.fetchone(
                "SELECT 1 FROM problem_allowed_users WHERE problem_id = %s AND user_id = %s LIMIT 1",
                (pid, uid),
            )
            if direct is not None:
                return True
        if vis == "classroom":
            assigned = db.fetchone(
                """
                SELECT 1 FROM assignment_problems ap
                JOIN assignments a ON a.id = ap.assignment_id
                JOIN classroom_students cs ON cs.classroom_id = a.classroom_id
                WHERE ap.problem_id = %s AND cs.student_id = %s AND a.deleted_at IS NULL
                LIMIT 1
                """,
                (pid, uid),
            )
            if assigned is not None:
                return True

    # Allow access inside a started accessible contest containing this non-hidden problem
    now = datetime.now(timezone.utc)
    if contest_id is not None:
        c_rows = db.fetchall(
            """
            SELECT c.* FROM contests c
            JOIN contest_problems cp ON cp.contest_id = c.id
            WHERE c.id = %s AND cp.problem_id = %s AND c.deleted_at IS NULL
            """,
            (contest_id, pid),
        )
    else:
        c_rows = db.fetchall(
            """
            SELECT c.* FROM contests c
            JOIN contest_problems cp ON cp.contest_id = c.id
            WHERE cp.problem_id = %s AND c.deleted_at IS NULL
            """,
            (pid,),
        )
    for c in c_rows:
        if not can_access_contest(db, c, user):
            continue
        st_val = c["start_time"]
        st_dt = (
            st_val
            if isinstance(st_val, datetime)
            else datetime.fromisoformat(str(st_val).replace("Z", "+00:00"))
        )
        if not st_dt.tzinfo:
            st_dt = st_dt.replace(tzinfo=timezone.utc)
        if now >= st_dt:
            return True

    return False


def ensure_problem_access(
    db: Database,
    prob: Dict[str, Any],
    user: Optional[Dict[str, Any]],
    contest_id: Optional[int] = None,
) -> None:
    if can_access_problem(db, prob, user, contest_id=contest_id):
        return
    vis = (prob.get("visibility") or "public").lower()
    if vis == "hidden":
        raise HTTPException(status_code=404, detail="Problem not found.")
    raise HTTPException(
        status_code=403,
        detail="Bạn không có quyền truy cập bài tập riêng tư này.",
    )
