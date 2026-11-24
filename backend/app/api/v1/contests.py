"""Contests & Scoreboard API (/api/v1/contests)."""
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Request, status

from backend.app.core.audit import record_audit_log
from backend.app.core.cache import app_cache, invalidate_contest_caches
from backend.app.core.contest_access import (
    can_access_contest,
    ensure_contest_access,
    is_contest_restricted,
    is_user_allowed,
)
from backend.app.core.database import Database, get_db
from backend.app.core.security import (
    get_client_ip,
    get_current_user,
    get_optional_user,
    is_staff,
    require_roles,
)
from backend.app.schemas.schemas import (
    ContestAddClassroomRequest,
    ContestAddUsersRequest,
    ContestCreateRequest,
    ContestUpdateRequest,
)

router = APIRouter(prefix="/contests", tags=["Contests"])


def _parse_dt(val: Any) -> datetime:
    if isinstance(val, datetime):
        return val if val.tzinfo else val.replace(tzinfo=timezone.utc)
    dt = datetime.fromisoformat(str(val).replace("Z", "+00:00"))
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def _contest_status(c: dict) -> str:
    now = datetime.now(timezone.utc)
    st = _parse_dt(c["start_time"])
    en = _parse_dt(c["end_time"])
    if now < st:
        return "UPCOMING"
    if now > en:
        return "ENDED"
    return "RUNNING"


@router.get("")
def list_contests(
    current_user: Optional[dict] = Depends(get_optional_user),
    db: Database = Depends(get_db),
):
    uid_scope = f"u:{current_user['id']}" if current_user else "anon"
    staff = is_staff(current_user)
    cache_key = f"contests:list:{'staff' if staff else 'user'}:{uid_scope}"
    cached = app_cache.get(cache_key)
    if cached is not None:
        return cached

    rows = db.fetchall(
        "SELECT * FROM contests WHERE deleted_at IS NULL ORDER BY start_time DESC"
    )
    if not rows:
        res = {"items": []}
        app_cache.set(cache_key, res, ttl_seconds=20.0)
        return res

    cids = [int(r["id"]) for r in rows]
    ph = ", ".join(["%s"] * len(cids))

    # Bulk-load participant counts & restricted flags in O(1) queries
    p_cnt_rows = db.fetchall(
        f"SELECT contest_id, COUNT(*) AS cnt FROM contest_participants WHERE contest_id IN ({ph}) GROUP BY contest_id",
        tuple(cids),
    )
    p_cnt_map = {int(r["contest_id"]): int(r["cnt"]) for r in p_cnt_rows}

    restricted_rows = db.fetchall(
        f"""
        SELECT DISTINCT contest_id FROM contest_allowed_users WHERE contest_id IN ({ph})
        UNION
        SELECT DISTINCT contest_id FROM contest_classrooms WHERE contest_id IN ({ph})
        """,
        tuple(cids + cids),
    )
    restricted_set = {int(r["contest_id"]) for r in restricted_rows}

    registered_set: set[int] = set()
    allowed_set: set[int] = set()
    user_classrooms: set[int] = set()
    if current_user:
        uid = int(current_user["id"])
        reg_rows = db.fetchall(
            f"SELECT contest_id FROM contest_participants WHERE user_id = %s AND contest_id IN ({ph})",
            (uid, *cids),
        )
        registered_set = {int(r["contest_id"]) for r in reg_rows}

        if not staff:
            cls_rows = db.fetchall(
                "SELECT classroom_id FROM classroom_students WHERE student_id = %s", (uid,)
            )
            user_classrooms = {int(r["classroom_id"]) for r in cls_rows}
            allow_rows = db.fetchall(
                f"""
                SELECT contest_id FROM contest_allowed_users WHERE user_id = %s AND contest_id IN ({ph})
                UNION
                SELECT cc.contest_id FROM contest_classrooms cc
                JOIN classroom_students cs ON cs.classroom_id = cc.classroom_id
                WHERE cs.student_id = %s AND cc.contest_id IN ({ph})
                """,
                (uid, *cids, uid, *cids),
            )
            allowed_set = {int(r["contest_id"]) for r in allow_rows}

    items = []
    for r in rows:
        cid = int(r["id"])
        is_hidden = bool(r.get("is_hidden"))
        is_restricted = cid in restricted_set

        if not staff:
            if is_hidden:
                continue
            if is_restricted:
                if not current_user or cid not in allowed_set:
                    continue
            else:
                vis = r.get("visibility") or "public"
                if vis == "private":
                    continue
                if vis == "classroom" and r.get("classroom_id"):
                    if not current_user or int(r["classroom_id"]) not in user_classrooms:
                        continue

        r["status"] = _contest_status(r)
        r["participant_count"] = p_cnt_map.get(cid, 0)
        r["is_hidden"] = is_hidden
        r["block_old_code"] = bool(r.get("block_old_code"))
        r["is_restricted"] = is_restricted
        r["is_registered"] = cid in registered_set
        items.append(r)

    res = {"items": items}
    app_cache.set(cache_key, res, ttl_seconds=20.0)
    return res


@router.post("", status_code=status.HTTP_201_CREATED)
def create_contest(
    payload: ContestCreateRequest,
    request: Request,
    current_user: dict = Depends(require_roles("admin", "teacher")),
    db: Database = Depends(get_db),
):
    if _parse_dt(payload.end_time) <= _parse_dt(payload.start_time):
        raise HTTPException(status_code=400, detail="End time must be after start time.")

    seen_problem_ids = set()
    for cp in payload.problems:
        if cp.problem_id in seen_problem_ids:
            raise HTTPException(status_code=400, detail=f"Problem ID {cp.problem_id} is duplicated.")
        seen_problem_ids.add(cp.problem_id)
        if not db.fetchone(
            "SELECT 1 FROM problems WHERE id = %s AND deleted_at IS NULL", (cp.problem_id,)
        ):
            raise HTTPException(status_code=400, detail=f"Problem ID {cp.problem_id} not found.")

    allowed_user_ids = list(dict.fromkeys(int(u) for u in payload.allowed_user_ids))
    allowed_classroom_ids = list(dict.fromkeys(int(c_id) for c_id in payload.allowed_classroom_ids))
    for uid in allowed_user_ids:
        if not db.fetchone("SELECT 1 FROM users WHERE id = %s AND deleted_at IS NULL", (uid,)):
            raise HTTPException(status_code=400, detail=f"User ID {uid} not found.")
    for cl_id in allowed_classroom_ids:
        if not db.fetchone("SELECT 1 FROM classrooms WHERE id = %s AND deleted_at IS NULL", (cl_id,)):
            raise HTTPException(status_code=400, detail=f"Classroom ID {cl_id} not found.")

    cid = db.insert_returning_id(
        """
        INSERT INTO contests (
            title, description, start_time, end_time, visibility, classroom_id,
            penalty_minutes, freeze_before_end_minutes, is_scoreboard_enabled,
            block_old_code, created_by
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """,
        (
            payload.title,
            payload.description,
            payload.start_time,
            payload.end_time,
            payload.visibility,
            payload.classroom_id,
            payload.penalty_minutes,
            payload.freeze_before_end_minutes,
            payload.is_scoreboard_enabled,
            bool(payload.block_old_code),
            current_user["id"],
        ),
    )
    for idx, cp in enumerate(payload.problems):
        db.execute(
            """
            INSERT INTO contest_problems (contest_id, problem_id, label, points, order_index)
            VALUES (%s, %s, %s, %s, %s)
            """,
            (cid, cp.problem_id, cp.label, cp.points, idx),
        )
    for uid in allowed_user_ids:
        db.execute(
            "INSERT INTO contest_allowed_users (contest_id, user_id) VALUES (%s, %s)",
            (cid, uid),
        )
        _register_user(db, cid, uid)
    for cl_id in allowed_classroom_ids:
        db.execute(
            "INSERT INTO contest_classrooms (contest_id, classroom_id) VALUES (%s, %s)",
            (cid, cl_id),
        )
        students = db.fetchall(
            "SELECT student_id FROM classroom_students WHERE classroom_id = %s", (cl_id,)
        )
        for s in students:
            _register_user(db, cid, int(s["student_id"]))
    record_audit_log(
        db, current_user["id"], "contest.create", "contest", str(cid), get_client_ip(request)
    )
    invalidate_contest_caches()
    return db.fetchone("SELECT * FROM contests WHERE id = %s", (cid,))


def _get_contest_or_404(db: Database, contest_id: int) -> dict:
    c = db.fetchone("SELECT * FROM contests WHERE id = %s AND deleted_at IS NULL", (contest_id,))
    if not c:
        raise HTTPException(status_code=404, detail="Contest not found.")
    return c


def _register_user(db: Database, contest_id: int, user_id: int) -> None:
    if not db.fetchone(
        "SELECT 1 FROM contest_participants WHERE contest_id = %s AND user_id = %s",
        (contest_id, user_id),
    ):
        db.execute(
            "INSERT INTO contest_participants (contest_id, user_id) VALUES (%s, %s)",
            (contest_id, user_id),
        )


@router.get("/{contest_id}")
def get_contest(
    contest_id: int,
    current_user: Optional[dict] = Depends(get_optional_user),
    db: Database = Depends(get_db),
):
    c = _get_contest_or_404(db, contest_id)
    ensure_contest_access(db, c, current_user)

    c["status"] = _contest_status(c)
    c["server_time"] = datetime.now(timezone.utc).isoformat()
    c["is_hidden"] = bool(c.get("is_hidden"))
    c["block_old_code"] = bool(c.get("block_old_code"))
    c["is_restricted"] = is_contest_restricted(db, contest_id)
    c["is_registered"] = bool(
        current_user
        and db.fetchone(
            "SELECT 1 FROM contest_participants WHERE contest_id = %s AND user_id = %s",
            (contest_id, current_user["id"]),
        )
    )
    problems = db.fetchall(
        """
        SELECT cp.label, cp.points, p.id, p.code, p.title, p.difficulty, p.time_limit_ms, p.memory_limit_mb
        FROM contest_problems cp
        JOIN problems p ON p.id = cp.problem_id
        WHERE cp.contest_id = %s
        ORDER BY cp.order_index ASC, cp.label ASC
        """,
        (contest_id,),
    )
    # Hide problem list before contest starts for non-staff
    c["problems"] = problems if (is_staff(current_user) or c["status"] != "UPCOMING") else []
    return c


@router.post("/{contest_id}/register")
def register_contest(
    contest_id: int,
    current_user: dict = Depends(get_current_user),
    db: Database = Depends(get_db),
):
    c = _get_contest_or_404(db, contest_id)
    if not can_access_contest(db, c, current_user):
        raise HTTPException(status_code=403, detail="You are not allowed to join this contest.")
    _register_user(db, contest_id, int(current_user["id"]))
    invalidate_contest_caches()
    return {"registered": True, "contest_id": contest_id}


# --- Staff management: edit / delete / hide / show / access lists ---
@router.patch("/{contest_id}")
def update_contest(
    contest_id: int,
    payload: ContestUpdateRequest,
    request: Request,
    current_user: dict = Depends(require_roles("admin", "teacher")),
    db: Database = Depends(get_db),
):
    existing = _get_contest_or_404(db, contest_id)

    eff_start = payload.start_time if payload.start_time is not None else existing["start_time"]
    eff_end = payload.end_time if payload.end_time is not None else existing["end_time"]
    if _parse_dt(eff_end) <= _parse_dt(eff_start):
        raise HTTPException(status_code=400, detail="End time must be after start time.")

    if payload.problems is not None:
        seen_pids = set()
        for cp in payload.problems:
            if cp.problem_id in seen_pids:
                raise HTTPException(status_code=400, detail=f"Problem ID {cp.problem_id} is duplicated.")
            seen_pids.add(cp.problem_id)
            if not db.fetchone(
                "SELECT 1 FROM problems WHERE id = %s AND deleted_at IS NULL", (cp.problem_id,)
            ):
                raise HTTPException(status_code=400, detail=f"Problem ID {cp.problem_id} not found.")

    sets = []
    params: List[Any] = []
    for field in (
        "title",
        "description",
        "start_time",
        "end_time",
        "penalty_minutes",
        "freeze_before_end_minutes",
        "is_hidden",
        "block_old_code",
    ):
        val = getattr(payload, field)
        if val is not None:
            sets.append(f"{field} = %s")
            params.append(bool(val) if field in ("is_hidden", "block_old_code") else val)

    if sets:
        sets.append("updated_at = CURRENT_TIMESTAMP")
        params.append(contest_id)
        db.execute(f"UPDATE contests SET {', '.join(sets)} WHERE id = %s", tuple(params))

    if payload.problems is not None:
        db.execute("DELETE FROM contest_problems WHERE contest_id = %s", (contest_id,))
        for idx, cp in enumerate(payload.problems):
            db.execute(
                """
                INSERT INTO contest_problems (contest_id, problem_id, label, points, order_index)
                VALUES (%s, %s, %s, %s, %s)
                """,
                (contest_id, cp.problem_id, cp.label, cp.points, idx),
            )

    action = "contest.update"
    if payload.is_hidden is not None and len(sets) == 2 and payload.problems is None:
        action = "contest.hide" if payload.is_hidden else "contest.show"
    record_audit_log(db, current_user["id"], action, "contest", str(contest_id), get_client_ip(request))
    invalidate_contest_caches()

    c = db.fetchone("SELECT * FROM contests WHERE id = %s", (contest_id,))
    c["status"] = _contest_status(c)
    c["server_time"] = datetime.now(timezone.utc).isoformat()
    c["is_hidden"] = bool(c.get("is_hidden"))
    c["block_old_code"] = bool(c.get("block_old_code"))
    c["is_restricted"] = is_contest_restricted(db, contest_id)
    return c


@router.delete("/{contest_id}")
def delete_contest(
    contest_id: int,
    request: Request,
    current_user: dict = Depends(require_roles("admin", "teacher")),
    db: Database = Depends(get_db),
):
    _get_contest_or_404(db, contest_id)
    db.execute("UPDATE contests SET deleted_at = CURRENT_TIMESTAMP WHERE id = %s", (contest_id,))
    record_audit_log(
        db, current_user["id"], "contest.delete", "contest", str(contest_id), get_client_ip(request)
    )
    invalidate_contest_caches()
    return {"deleted": True, "contest_id": contest_id}


def _access_payload(db: Database, contest_id: int) -> dict:
    users = db.fetchall(
        """
        SELECT u.id, u.username, u.full_name, u.email
        FROM contest_allowed_users au
        JOIN users u ON u.id = au.user_id
        WHERE au.contest_id = %s
        ORDER BY u.username ASC
        """,
        (contest_id,),
    )
    classrooms = db.fetchall(
        """
        SELECT c.id, c.name,
               (SELECT COUNT(*) FROM classroom_students cs WHERE cs.classroom_id = c.id) AS student_count
        FROM contest_classrooms cc
        JOIN classrooms c ON c.id = cc.classroom_id
        WHERE cc.contest_id = %s
        ORDER BY c.name ASC
        """,
        (contest_id,),
    )
    for cl in classrooms:
        cl["student_count"] = int(cl.get("student_count") or 0)
    return {
        "contest_id": contest_id,
        "is_restricted": bool(users or classrooms),
        "users": users,
        "classrooms": classrooms,
    }


@router.get("/{contest_id}/access")
def get_contest_access(
    contest_id: int,
    current_user: dict = Depends(require_roles("admin", "teacher")),
    db: Database = Depends(get_db),
):
    _get_contest_or_404(db, contest_id)
    return _access_payload(db, contest_id)


@router.post("/{contest_id}/access/users")
def add_contest_users(
    contest_id: int,
    payload: ContestAddUsersRequest,
    request: Request,
    current_user: dict = Depends(require_roles("admin", "teacher")),
    db: Database = Depends(get_db),
):
    _get_contest_or_404(db, contest_id)
    user_ids: List[int] = []
    not_found: List[str] = []
    for uid in payload.user_ids:
        row = db.fetchone("SELECT id FROM users WHERE id = %s AND deleted_at IS NULL", (uid,))
        if row:
            user_ids.append(int(row["id"]))
        else:
            not_found.append(str(uid))
    for raw in payload.usernames:
        name = (raw or "").strip()
        if not name:
            continue
        row = db.fetchone(
            "SELECT id FROM users WHERE (username = %s OR email = %s) AND deleted_at IS NULL",
            (name, name),
        )
        if row:
            user_ids.append(int(row["id"]))
        else:
            not_found.append(name)

    added = 0
    for uid in dict.fromkeys(user_ids):
        if not db.fetchone(
            "SELECT 1 FROM contest_allowed_users WHERE contest_id = %s AND user_id = %s",
            (contest_id, uid),
        ):
            db.execute(
                "INSERT INTO contest_allowed_users (contest_id, user_id) VALUES (%s, %s)",
                (contest_id, uid),
            )
            added += 1
        # Assigned accounts are registered automatically so they appear on the scoreboard
        _register_user(db, contest_id, uid)
    record_audit_log(
        db, current_user["id"], "contest.access.add_users", "contest", str(contest_id), get_client_ip(request)
    )
    invalidate_contest_caches()
    result = _access_payload(db, contest_id)
    result["added"] = added
    result["not_found"] = not_found
    return result


@router.delete("/{contest_id}/access/users/{user_id}")
def remove_contest_user(
    contest_id: int,
    user_id: int,
    current_user: dict = Depends(require_roles("admin", "teacher")),
    db: Database = Depends(get_db),
):
    _get_contest_or_404(db, contest_id)
    db.execute(
        "DELETE FROM contest_allowed_users WHERE contest_id = %s AND user_id = %s",
        (contest_id, user_id),
    )
    # Keep participation only if the user is still allowed through a classroom (or contest became open)
    if is_contest_restricted(db, contest_id) and not is_user_allowed(db, contest_id, user_id):
        db.execute(
            "DELETE FROM contest_participants WHERE contest_id = %s AND user_id = %s",
            (contest_id, user_id),
        )
    invalidate_contest_caches()
    return _access_payload(db, contest_id)


@router.post("/{contest_id}/access/classrooms")
def add_contest_classroom(
    contest_id: int,
    payload: ContestAddClassroomRequest,
    request: Request,
    current_user: dict = Depends(require_roles("admin", "teacher")),
    db: Database = Depends(get_db),
):
    _get_contest_or_404(db, contest_id)
    cls = db.fetchone(
        "SELECT id FROM classrooms WHERE id = %s AND deleted_at IS NULL", (payload.classroom_id,)
    )
    if not cls:
        raise HTTPException(status_code=404, detail="Classroom not found.")
    if not db.fetchone(
        "SELECT 1 FROM contest_classrooms WHERE contest_id = %s AND classroom_id = %s",
        (contest_id, payload.classroom_id),
    ):
        db.execute(
            "INSERT INTO contest_classrooms (contest_id, classroom_id) VALUES (%s, %s)",
            (contest_id, payload.classroom_id),
        )
    students = db.fetchall(
        "SELECT student_id FROM classroom_students WHERE classroom_id = %s", (payload.classroom_id,)
    )
    for s in students:
        _register_user(db, contest_id, int(s["student_id"]))
    record_audit_log(
        db, current_user["id"], "contest.access.add_classroom", "contest", str(contest_id), get_client_ip(request)
    )
    invalidate_contest_caches()
    return _access_payload(db, contest_id)


@router.delete("/{contest_id}/access/classrooms/{classroom_id}")
def remove_contest_classroom(
    contest_id: int,
    classroom_id: int,
    current_user: dict = Depends(require_roles("admin", "teacher")),
    db: Database = Depends(get_db),
):
    _get_contest_or_404(db, contest_id)
    db.execute(
        "DELETE FROM contest_classrooms WHERE contest_id = %s AND classroom_id = %s",
        (contest_id, classroom_id),
    )
    if is_contest_restricted(db, contest_id):
        students = db.fetchall(
            "SELECT student_id FROM classroom_students WHERE classroom_id = %s", (classroom_id,)
        )
        for s in students:
            sid = int(s["student_id"])
            if not is_user_allowed(db, contest_id, sid):
                db.execute(
                    "DELETE FROM contest_participants WHERE contest_id = %s AND user_id = %s",
                    (contest_id, sid),
                )
    invalidate_contest_caches()
    return _access_payload(db, contest_id)


@router.get("/{contest_id}/scoreboard")
def get_scoreboard(
    contest_id: int,
    current_user: Optional[dict] = Depends(get_optional_user),
    db: Database = Depends(get_db),
):
    c = _get_contest_or_404(db, contest_id)
    ensure_contest_access(db, c, current_user)
    if not c["is_scoreboard_enabled"] and not is_staff(current_user):
        raise HTTPException(status_code=403, detail="Scoreboard is disabled for this contest.")

    start_dt = _parse_dt(c["start_time"])
    end_dt = _parse_dt(c["end_time"])
    freeze_mins = int(c.get("freeze_before_end_minutes") or 0)
    freeze_cutoff = end_dt - timedelta(minutes=freeze_mins) if freeze_mins > 0 else None
    now = datetime.now(timezone.utc)
    apply_freeze = bool(
        freeze_cutoff and not is_staff(current_user) and start_dt <= now <= end_dt and now >= freeze_cutoff
    )

    sb_cache_key = f"scoreboard:{contest_id}:{'frozen' if apply_freeze else 'live'}"
    cached_sb = app_cache.get(sb_cache_key)
    if cached_sb is not None:
        return cached_sb

    c_problems = db.fetchall(
        """
        SELECT cp.problem_id, cp.label, cp.points, p.code, p.title
        FROM contest_problems cp
        JOIN problems p ON p.id = cp.problem_id
        WHERE cp.contest_id = %s
        ORDER BY cp.order_index ASC, cp.label ASC
        """,
        (contest_id,),
    )
    problem_points = {str(cp["problem_id"]): int(cp["points"] or 0) for cp in c_problems}
    # Gather all eligible / active participants in ONE unified UNION query
    participants = db.fetchall(
        """
        SELECT u.id, u.username, u.full_name
        FROM contest_participants cp
        JOIN users u ON u.id = cp.user_id
        WHERE cp.contest_id = %s AND u.deleted_at IS NULL
        UNION
        SELECT u.id, u.username, u.full_name
        FROM contest_allowed_users au
        JOIN users u ON u.id = au.user_id
        WHERE au.contest_id = %s AND u.deleted_at IS NULL
        UNION
        SELECT u.id, u.username, u.full_name
        FROM contest_classrooms cc
        JOIN classroom_students cs ON cs.classroom_id = cc.classroom_id
        JOIN users u ON u.id = cs.student_id
        WHERE cc.contest_id = %s AND u.deleted_at IS NULL
        UNION
        SELECT u.id, u.username, u.full_name
        FROM submissions s
        JOIN users u ON u.id = s.user_id
        WHERE s.contest_id = %s AND u.deleted_at IS NULL
        """,
        (contest_id, contest_id, contest_id, contest_id),
    )

    # Strictly count ONLY submissions made inside THIS contest so prior practice or
    # other-contest results are never carried over when a problem is reused.
    subs = db.fetchall(
        """
        SELECT id, user_id, problem_id, status, verdict, score, max_score, created_at
        FROM submissions
        WHERE contest_id = %s
        """,
        (contest_id,),
    )

    def _sort_key(s: dict):
        try:
            return (_parse_dt(s["created_at"]), int(s["id"]))
        except (TypeError, ValueError):
            return (end_dt, int(s["id"]))

    subs.sort(key=_sort_key)

    board: Dict[int, Dict[str, Any]] = {}
    for p in participants:
        board[int(p["id"])] = {
            "user_id": int(p["id"]),
            "username": p["username"],
            "full_name": p["full_name"],
            "display_name": (p.get("full_name") or "").strip() or p["username"],
            "solved": 0,
            "total_score": 0,
            "penalty": 0,
            "problems": {
                str(cp["problem_id"]): {
                    "label": cp["label"],
                    "solved": False,
                    "is_first_ac": False,
                    "attempts": 0,
                    "score": 0,
                    "max_score": int(cp["points"] or 0),
                    "time_min": 0,
                    "submitted": False,
                    "pending": False,
                }
                for cp in c_problems
            },
        }

    penalty_per_wrong = int(c.get("penalty_minutes") or 20)
    seen_ids = set()
    first_ac_done = set()
    for s in subs:
        sid = int(s["id"])
        if sid in seen_ids:
            continue
        seen_ids.add(sid)
        uid = int(s["user_id"])
        pid = str(s["problem_id"])
        if uid not in board or pid not in board[uid]["problems"]:
            continue
        sub_dt = _parse_dt(s["created_at"])
        if apply_freeze and freeze_cutoff and sub_dt >= freeze_cutoff:
            continue
        cell = board[uid]["problems"][pid]
        verdict = s.get("verdict") or ""
        if verdict in ("PENDING", "JUDGING") or (s.get("status") and s["status"] != "COMPLETED"):
            if not cell["solved"]:
                cell["pending"] = True
            continue
        if cell["solved"]:
            continue
        cell["submitted"] = True
        pts = problem_points.get(pid, 0)
        max_s = int(s.get("max_score") or 0)
        raw = int(s.get("score") or 0)
        if verdict == "AC":
            scaled = pts
        elif max_s > 0:
            scaled = min(pts, max(0, int(round(raw * pts / max_s))))
        else:
            scaled = 0
        if verdict == "AC":
            cell["solved"] = True
            if pid not in first_ac_done:
                first_ac_done.add(pid)
                cell["is_first_ac"] = True
            mins = max(0, int((sub_dt - start_dt).total_seconds() // 60))
            cell["time_min"] = mins
            cell["score"] = max(cell["score"], scaled)
            board[uid]["solved"] += 1
            board[uid]["penalty"] += mins + cell["attempts"] * penalty_per_wrong
        elif verdict not in ("CE", "IE"):
            cell["attempts"] += 1
            cell["score"] = max(cell["score"], scaled)

    rows = []
    for entry in board.values():
        for cell in entry["problems"].values():
            if cell["solved"]:
                cell["pending"] = False
        entry["total_score"] = sum(cell["score"] for cell in entry["problems"].values())
        rows.append(entry)
    rows.sort(key=lambda r: (-r["total_score"], -r["solved"], r["penalty"], r["username"]))
    for rank, row in enumerate(rows, start=1):
        row["rank"] = rank

    sb_res = {
        "contest_id": contest_id,
        "frozen": apply_freeze,
        "problems": c_problems,
        "max_total": sum(problem_points.values()),
        "standings": rows,
    }
    app_cache.set(sb_cache_key, sb_res, ttl_seconds=10.0)
    return sb_res
