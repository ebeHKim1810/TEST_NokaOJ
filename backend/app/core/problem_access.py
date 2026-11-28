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


def _parse_dt_utc(val: Any) -> datetime:
    if isinstance(val, datetime):
        return val if val.tzinfo else val.replace(tzinfo=timezone.utc)
    dt = datetime.fromisoformat(str(val).replace("Z", "+00:00"))
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def _has_direct_problem_access(
    db: Database,
    prob: Dict[str, Any],
    user: Optional[Dict[str, Any]],
) -> bool:
    """Checks non-contest access rules (staff, public, direct private list, classroom assignment)."""
    if is_staff(user):
        return True

    vis = (prob.get("visibility") or "public").lower()
    if vis == "public":
        return True
    if vis == "hidden":
        return False

    if not user:
        return False

    pid = int(prob["id"])
    uid = int(user["id"])

    if vis == "private":
        direct = db.fetchone(
            "SELECT 1 FROM problem_allowed_users WHERE problem_id = %s AND user_id = %s LIMIT 1",
            (pid, uid),
        )
        return direct is not None

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
        return assigned is not None

    return False


def _can_access_problem_via_contest(
    db: Database,
    problem_id: int,
    user: Optional[Dict[str, Any]],
    contest_id: Optional[int] = None,
    require_running_contest: bool = False,
) -> bool:
    """
    Contest Override: allows valid contest participants to access hidden/private problems
    attached to an accessible contest once the contest has started (`now >= start_time`).
    When `require_running_contest=True`, also requires `now <= end_time`.
    """
    now = datetime.now(timezone.utc)
    if contest_id is not None:
        c_rows = db.fetchall(
            """
            SELECT c.* FROM contests c
            JOIN contest_problems cp ON cp.contest_id = c.id
            WHERE c.id = %s AND cp.problem_id = %s AND c.deleted_at IS NULL
            """,
            (contest_id, problem_id),
        )
    else:
        c_rows = db.fetchall(
            """
            SELECT c.* FROM contests c
            JOIN contest_problems cp ON cp.contest_id = c.id
            WHERE cp.problem_id = %s AND c.deleted_at IS NULL
            """,
            (problem_id,),
        )

    for c in c_rows:
        if not can_access_contest(db, c, user):
            continue
        try:
            st_dt = _parse_dt_utc(c["start_time"])
            en_dt = _parse_dt_utc(c["end_time"])
        except (TypeError, ValueError):
            continue
        if now < st_dt:
            continue
        if require_running_contest and now > en_dt:
            continue
        return True

    return False


def can_access_problem(
    db: Database,
    prob: Dict[str, Any],
    user: Optional[Dict[str, Any]],
    contest_id: Optional[int] = None,
    require_running_contest: bool = False,
) -> bool:
    """
    Checks whether `user` can view/submit `prob`:
    - Admin/Teacher: always allowed.
    - public: allowed for everyone.
    - private: allowed if user is in problem_allowed_users, or via contest override.
    - hidden: hidden from general problemset, allowed ONLY via contest override once contest starts.
    - classroom (legacy): allowed if assigned to student's classroom, or via contest override.
    """
    if _has_direct_problem_access(db, prob, user):
        return True

    return _can_access_problem_via_contest(
        db=db,
        problem_id=int(prob["id"]),
        user=user,
        contest_id=contest_id,
        require_running_contest=require_running_contest,
    )


can_user_access_problem = can_access_problem


def ensure_problem_access(
    db: Database,
    prob: Dict[str, Any],
    user: Optional[Dict[str, Any]],
    contest_id: Optional[int] = None,
    require_running_contest: bool = False,
) -> None:
    if can_access_problem(
        db,
        prob,
        user,
        contest_id=contest_id,
        require_running_contest=require_running_contest,
    ):
        return
    vis = (prob.get("visibility") or "public").lower()
    if vis == "hidden":
        raise HTTPException(status_code=404, detail="Problem not found.")
    raise HTTPException(
        status_code=403,
        detail="Bạn không có quyền truy cập bài tập riêng tư này.",
    )
