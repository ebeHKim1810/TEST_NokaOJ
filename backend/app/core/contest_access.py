"""Shared contest access helpers (hidden contests, restricted lists & old-code blocking)."""
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import HTTPException

from backend.app.core.database import Database
from backend.app.core.security import is_staff


def _parse_dt_utc(val: Any) -> datetime:
    if isinstance(val, datetime):
        return val if val.tzinfo else val.replace(tzinfo=timezone.utc)
    dt = datetime.fromisoformat(str(val).replace("Z", "+00:00"))
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def get_active_code_blocking_contests(
    db: Database, user: Optional[dict]
) -> List[Dict[str, Any]]:
    """
    Return currently RUNNING contests with block_old_code enabled that `user`
    is participating in. Staff are never blocked.
    """
    if not user or is_staff(user):
        return []
    uid = int(user["id"])
    rows = db.fetchall(
        """
        SELECT DISTINCT c.id, c.title, c.start_time, c.end_time
        FROM contests c
        WHERE c.deleted_at IS NULL
          AND c.is_hidden = %s
          AND c.block_old_code = %s
          AND (
              EXISTS (SELECT 1 FROM contest_participants cp WHERE cp.contest_id = c.id AND cp.user_id = %s)
              OR EXISTS (SELECT 1 FROM contest_allowed_users au WHERE au.contest_id = c.id AND au.user_id = %s)
              OR EXISTS (
                  SELECT 1 FROM contest_classrooms cc
                  JOIN classroom_students cs ON cs.classroom_id = cc.classroom_id
                  WHERE cc.contest_id = c.id AND cs.student_id = %s
              )
          )
        """,
        (False, True, uid, uid, uid),
    )
    now = datetime.now(timezone.utc)
    active: List[Dict[str, Any]] = []
    for r in rows:
        try:
            st = _parse_dt_utc(r["start_time"])
            en = _parse_dt_utc(r["end_time"])
        except (TypeError, ValueError):
            continue
        if st <= now <= en:
            active.append({"id": int(r["id"]), "title": r["title"]})
    return active


def is_contest_restricted(db: Database, contest_id: int) -> bool:
    """A contest is restricted when staff assigned specific accounts or classrooms to it."""
    if db.fetchone("SELECT 1 FROM contest_allowed_users WHERE contest_id = %s LIMIT 1", (contest_id,)):
        return True
    if db.fetchone("SELECT 1 FROM contest_classrooms WHERE contest_id = %s LIMIT 1", (contest_id,)):
        return True
    return False


def is_user_allowed(db: Database, contest_id: int, user_id: int) -> bool:
    """True if the user was assigned directly or belongs to an assigned classroom."""
    if db.fetchone(
        "SELECT 1 FROM contest_allowed_users WHERE contest_id = %s AND user_id = %s",
        (contest_id, user_id),
    ):
        return True
    return (
        db.fetchone(
            """
            SELECT 1 FROM contest_classrooms cc
            JOIN classroom_students cs ON cs.classroom_id = cc.classroom_id
            WHERE cc.contest_id = %s AND cs.student_id = %s
            LIMIT 1
            """,
            (contest_id, user_id),
        )
        is not None
    )


def can_access_contest(db: Database, contest: Dict[str, Any], user: Optional[dict]) -> bool:
    """Check whether `user` can view/participate in `contest`. Staff always have access."""
    if is_staff(user):
        return True
    if contest.get("is_hidden"):
        return False
    cid = int(contest["id"])
    if is_contest_restricted(db, cid):
        return bool(user) and is_user_allowed(db, cid, int(user["id"]))

    vis = contest.get("visibility") or "public"
    if vis == "classroom" and contest.get("classroom_id"):
        if not user:
            return False
        in_cls = db.fetchone(
            "SELECT 1 FROM classroom_students WHERE classroom_id = %s AND student_id = %s",
            (contest["classroom_id"], user["id"]),
        )
        return in_cls is not None
    if vis == "private":
        if not user:
            return False
        enrolled = db.fetchone(
            "SELECT 1 FROM contest_participants WHERE contest_id = %s AND user_id = %s LIMIT 1",
            (cid, int(user["id"])),
        )
        return enrolled is not None
    return True


def ensure_contest_access(db: Database, contest: Dict[str, Any], user: Optional[dict]) -> None:
    """Raise a clear HTTP error if `user` cannot access `contest`."""
    if is_staff(user):
        return
    if contest.get("is_hidden"):
        raise HTTPException(status_code=404, detail="Kỳ thi không tồn tại hoặc đang bị ẩn.")
    if can_access_contest(db, contest, user):
        return
    if not user:
        raise HTTPException(
            status_code=401,
            detail="Kỳ thi này chỉ dành cho thí sinh được chỉ định. Vui lòng đăng nhập.",
        )
    raise HTTPException(status_code=403, detail="Bạn không có quyền tham gia kỳ thi này.")
