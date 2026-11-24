"""Problemset & Problem CRUD API routes (/api/v1/problems)."""
import re
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from fastapi import APIRouter, Depends, File, HTTPException, Request, Response, UploadFile, status

from backend.app.core.audit import record_audit_log
from backend.app.core.cache import app_cache, invalidate_problem_caches
from backend.app.core.contest_access import can_access_contest, get_active_code_blocking_contests
from backend.app.core.database import Database, get_db
from backend.app.core.problem_access import (
    ensure_problem_access,
    get_problem_allowed_users,
    sync_problem_allowed_users,
)
from backend.app.core.security import (
    get_client_ip,
    get_optional_user,
    is_admin,
    is_staff,
    require_roles,
)
from backend.app.core.storage import BaseStorage, get_storage
from backend.app.schemas.schemas import (
    ProblemAccessUpdateRequest,
    ProblemCreateRequest,
    ProblemUpdateRequest,
)

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


MAX_PROBLEM_IMAGE_BYTES = 5 * 1024 * 1024  # 5 MB
ALLOWED_IMAGE_MIMES: Dict[str, Tuple[str, str]] = {
    "image/png": (".png", "image/png"),
    "image/jpeg": (".jpg", "image/jpeg"),
    "image/jpg": (".jpg", "image/jpeg"),
    "image/webp": (".webp", "image/webp"),
    "image/gif": (".gif", "image/gif"),
}
EXT_TO_IMAGE_MIME: Dict[str, str] = {
    "png": "image/png",
    "jpg": "image/jpeg",
    "jpeg": "image/jpeg",
    "webp": "image/webp",
    "gif": "image/gif",
}
SAFE_IMAGE_FILENAME_RE = re.compile(r"^[a-f0-9]{16,64}\.(png|jpg|jpeg|webp|gif)$")


def _detect_image_format(data: bytes) -> Optional[Tuple[str, str]]:
    """Verifies image magic bytes and returns (extension, canonical_mime) for PNG/JPEG/WEBP/GIF."""
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return (".png", "image/png")
    if data.startswith(b"\xff\xd8\xff"):
        return (".jpg", "image/jpeg")
    if len(data) >= 12 and data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return (".webp", "image/webp")
    if data.startswith((b"GIF87a", b"GIF89a")):
        return (".gif", "image/gif")
    return None


@router.get("/tags/all")
def list_tags(db: Database = Depends(get_db)):
    return app_cache.get_or_set(
        "tags:all",
        lambda: {"items": db.fetchall("SELECT id, name, slug FROM tags ORDER BY name ASC")},
        ttl_seconds=60.0,
    )


@router.post("/upload-image", status_code=status.HTTP_201_CREATED)
async def upload_problem_image(
    request: Request,
    file: UploadFile = File(...),
    current_user: dict = Depends(require_roles("admin", "teacher")),
    db: Database = Depends(get_db),
    storage: BaseStorage = Depends(get_storage),
):
    """
    Uploads an image (PNG/JPEG/WEBP/GIF, max 5MB) to Cloudflare R2 (`problem-images/`)
    for embedding inside problem statements and explanations.
    """
    raw_mime = (file.content_type or "").split(";")[0].strip().lower()
    if raw_mime not in ALLOWED_IMAGE_MIMES:
        raise HTTPException(
            status_code=400,
            detail="Chỉ chấp nhận định dạng ảnh PNG, JPEG, WEBP hoặc GIF.",
        )

    data = await file.read(MAX_PROBLEM_IMAGE_BYTES + 1)
    if not data:
        raise HTTPException(status_code=400, detail="File ảnh trống.")
    if len(data) > MAX_PROBLEM_IMAGE_BYTES:
        raise HTTPException(
            status_code=413,
            detail="Ảnh vượt quá dung lượng tối đa 5MB. Vui lòng nén hoặc chọn ảnh nhỏ hơn.",
        )

    detected = _detect_image_format(data)
    if not detected:
        raise HTTPException(
            status_code=400,
            detail="Nội dung file không phải ảnh hợp lệ (PNG, JPEG, WEBP, GIF).",
        )

    ext, canonical_mime = detected
    filename = f"{uuid.uuid4().hex}{ext}"
    storage_key = f"problem-images/{filename}"
    storage.put_bytes(storage_key, data)

    proto = (request.headers.get("x-forwarded-proto") or request.url.scheme or "https").split(",")[0].strip()
    host = (request.headers.get("x-forwarded-host") or request.headers.get("host") or request.url.netloc).strip()
    path = f"/api/v1/problems/images/{filename}"
    image_url = f"{proto}://{host}{path}" if host else path

    record_audit_log(
        db,
        current_user["id"],
        "problem.image.upload",
        "problem_image",
        filename,
        get_client_ip(request),
        {"storage_key": storage_key, "size_bytes": len(data), "content_type": canonical_mime},
    )
    return {
        "url": image_url,
        "path": path,
        "filename": filename,
        "storage_key": storage_key,
        "size_bytes": len(data),
        "content_type": canonical_mime,
    }


@router.get("/images/{filename}")
def get_problem_image(
    filename: str,
    storage: BaseStorage = Depends(get_storage),
):
    """Streams a stored problem image from Cloudflare R2 / local storage with 1-year immutable caching."""
    clean = (filename or "").strip().lower()
    if not SAFE_IMAGE_FILENAME_RE.match(clean):
        raise HTTPException(status_code=400, detail="Invalid image filename.")

    data = storage.get_bytes(f"problem-images/{clean}")
    if not data:
        raise HTTPException(status_code=404, detail="Image not found.")

    ext = clean.rsplit(".", 1)[-1]
    media_type = EXT_TO_IMAGE_MIME.get(ext, "application/octet-stream")
    return Response(
        content=data,
        media_type=media_type,
        headers={
            "Cache-Control": "public, max-age=31536000, immutable",
            "Cross-Origin-Resource-Policy": "cross-origin",
            "X-Content-Type-Options": "nosniff",
        },
    )


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

    uid_scope = f"u:{current_user['id']}" if current_user else "anon"
    staff_flag = "staff" if is_staff(current_user) else "user"
    cache_key = (
        f"problems:{staff_flag}:{uid_scope}:"
        f"{search.strip().lower()}|{tag.strip().lower()}|{difficulty}|{solved_status}|"
        f"{visibility}|{sort_by}|{sort_dir.lower()}|{page}|{page_size}"
    )
    cached = app_cache.get(cache_key)
    if cached is not None:
        return cached

    where = ["p.deleted_at IS NULL"]
    params: List[Any] = []

    if not is_staff(current_user):
        if current_user:
            where.append(
                """
                (
                    p.visibility = 'public'
                    OR (p.visibility = 'private' AND p.id IN (
                        SELECT pau.problem_id FROM problem_allowed_users pau
                        WHERE pau.user_id = %s
                    ))
                    OR (p.visibility = 'classroom' AND p.id IN (
                        SELECT ap.problem_id FROM assignment_problems ap
                        JOIN assignments a ON a.id = ap.assignment_id
                        JOIN classroom_students cs ON cs.classroom_id = a.classroom_id
                        WHERE cs.student_id = %s AND a.deleted_at IS NULL
                    ))
                )
                """
            )
            params.extend([current_user["id"], current_user["id"]])
        else:
            where.append("p.visibility = 'public'")
        if visibility in ("public", "private"):
            where.append("p.visibility = %s")
            params.append(visibility)
    else:
        if visibility in ("public", "private", "hidden", "classroom"):
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
               p.submission_retention_mode,
               p.time_limit_ms, p.memory_limit_mb, p.created_by, p.created_at
        FROM problems p
        WHERE {' AND '.join(where)}
        """,
        tuple(params),
    )

    if not rows:
        empty_res = {"items": [], "total": 0, "page": page, "page_size": page_size}
        app_cache.set(cache_key, empty_res, ttl_seconds=30.0)
        return empty_res

    # Batched O(1) queries to eliminate 5*N N+1 queries across up to 700+ problems
    pids = [int(r["id"]) for r in rows]
    ph = ", ".join(["%s"] * len(pids))

    sub_stats_rows = db.fetchall(
        f"""
        SELECT problem_id,
               COUNT(*) AS total_subs,
               COUNT(DISTINCT CASE WHEN verdict = 'AC' THEN user_id END) AS ac_users
        FROM submissions
        WHERE problem_id IN ({ph})
        GROUP BY problem_id
        """,
        tuple(pids),
    )
    stats_map: Dict[int, tuple] = {
        int(r["problem_id"]): (int(r["ac_users"] or 0), int(r["total_subs"] or 0))
        for r in sub_stats_rows
    }

    tag_rows = db.fetchall(
        f"""
        SELECT pt.problem_id, t.name
        FROM problem_tags pt
        JOIN tags t ON t.id = pt.tag_id
        WHERE pt.problem_id IN ({ph})
        ORDER BY t.name ASC
        """,
        tuple(pids),
    )
    tags_map: Dict[int, List[str]] = {}
    for tr in tag_rows:
        tags_map.setdefault(int(tr["problem_id"]), []).append(tr["name"])

    user_status_map: Dict[int, str] = {}
    if current_user:
        u_rows = db.fetchall(
            f"""
            SELECT problem_id,
                   MAX(CASE WHEN verdict = 'AC' THEN 1 ELSE 0 END) AS has_ac
            FROM submissions
            WHERE user_id = %s AND problem_id IN ({ph})
            GROUP BY problem_id
            """,
            (current_user["id"], *pids),
        )
        for ur in u_rows:
            user_status_map[int(ur["problem_id"])] = "solved" if ur["has_ac"] else "attempted"

    allowed_cnt_map: Dict[int, int] = {}
    if is_staff(current_user):
        ac_rows = db.fetchall(
            f"SELECT problem_id, COUNT(*) AS cnt FROM problem_allowed_users WHERE problem_id IN ({ph}) GROUP BY problem_id",
            tuple(pids),
        )
        allowed_cnt_map = {int(r["problem_id"]): int(r["cnt"]) for r in ac_rows}

    enriched = []
    diff_rank = {"easy": 1, "medium": 2, "hard": 3}
    for row in rows:
        pid = int(row["id"])
        ac_users, total_subs = stats_map.get(pid, (0, 0))
        ac_rate = round((ac_users / total_subs) * 100, 1) if total_subs > 0 else 0.0
        user_status = user_status_map.get(pid, "unsolved")

        if solved_status == "solved" and user_status != "solved":
            continue
        if solved_status == "unsolved" and user_status == "solved":
            continue

        row["tags"] = tags_map.get(pid, [])
        row["ac_count"] = ac_users
        row["submission_count"] = total_subs
        row["ac_rate"] = ac_rate
        row["user_status"] = user_status
        row["submission_retention_mode"] = row.get("submission_retention_mode") or "latest"
        if is_staff(current_user):
            row["allowed_user_count"] = allowed_cnt_map.get(pid, 0)
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
    result = {
        "items": enriched[start : start + page_size],
        "total": total,
        "page": page,
        "page_size": page_size,
    }
    app_cache.set(cache_key, result, ttl_seconds=30.0)
    return result


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

    ensure_problem_access(db, prob, current_user, contest_id=contest_id)

    # Cache static problem metadata + R2 sample files & checker source for 60s
    # so repeated page views never make redundant Cloudflare R2 network round-trips.
    pid = int(prob["id"])
    static_key = f"problem_detail:{pid}:{'staff' if is_staff(current_user) else 'student'}"
    static_bundle = app_cache.get(static_key)
    if static_bundle is None:
        sample_rows = db.fetchall(
            """
            SELECT id, name, input_storage_key, output_storage_key
            FROM testcases
            WHERE problem_id = %s AND is_sample = %s AND is_hidden = %s
            ORDER BY order_index ASC, id ASC
            """,
            (pid, True, False),
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
            "SELECT COUNT(*) AS cnt FROM testcases WHERE problem_id = %s", (pid,)
        )
        static_bundle = {
            "tags": _get_problem_tags(db, pid),
            "samples": samples,
            "testcase_count": int(tc_count["cnt"]) if tc_count else 0,
        }
        if is_staff(current_user):
            static_bundle["checker_source"] = (
                storage.get_text(prob["checker_storage_key"])
                if prob.get("checker_storage_key")
                else ""
            )
        app_cache.set(static_key, static_bundle, ttl_seconds=60.0)

    # If a student opens a problem inside a RUNNING accessible contest, auto-enroll them
    # in contest_participants so contest rules (such as block_old_code) engage immediately.
    if contest_id is not None and current_user and not is_staff(current_user):
        c_row = db.fetchone(
            """
            SELECT c.* FROM contests c
            JOIN contest_problems cp ON cp.contest_id = c.id
            WHERE c.id = %s AND cp.problem_id = %s AND c.deleted_at IS NULL
            """,
            (contest_id, pid),
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
                (pid, current_user["id"], contest_id),
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
                (pid, current_user["id"]),
            )

    prob["tags"] = static_bundle["tags"]
    prob["samples"] = static_bundle["samples"]
    prob["testcase_count"] = static_bundle["testcase_count"]
    prob["recent_submissions"] = recent_subs
    prob["block_old_code"] = bool(blocking)
    prob["checker_language"] = prob.get("checker_language") or "python3"
    prob["submission_retention_mode"] = prob.get("submission_retention_mode") or "latest"
    if is_staff(current_user):
        prob["checker_source"] = static_bundle.get("checker_source", "")
        allowed_users = get_problem_allowed_users(db, pid)
        prob["allowed_users"] = allowed_users
        prob["allowed_user_ids"] = [int(u["id"]) for u in allowed_users]
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

    explanation_val = payload.explanation if (payload.explanation and payload.explanation.strip()) else None
    pid = db.insert_returning_id(
        """
        INSERT INTO problems (
            code, title, statement_md, input_description, output_description,
            constraints_md, sample_input, sample_output, explanation, time_limit_ms,
            memory_limit_mb, points, difficulty, visibility, submission_retention_mode,
            checker_type, checker_language, checker_storage_key, created_by
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
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
            explanation_val,
            payload.time_limit_ms,
            payload.memory_limit_mb,
            payload.points,
            payload.difficulty,
            payload.visibility,
            payload.submission_retention_mode,
            payload.checker_type,
            checker_lang,
            checker_key,
            current_user["id"],
        ),
    )
    _sync_tags(db, pid, payload.tags)
    if payload.allowed_user_ids:
        sync_problem_allowed_users(db, pid, payload.allowed_user_ids)
    record_audit_log(
        db, current_user["id"], "problem.create", "problem", str(pid), get_client_ip(request), {"code": code}
    )
    invalidate_problem_caches()
    prob = db.fetchone("SELECT * FROM problems WHERE id = %s", (pid,))
    prob["tags"] = _get_problem_tags(db, pid)
    allowed_users = get_problem_allowed_users(db, pid)
    prob["allowed_users"] = allowed_users
    prob["allowed_user_ids"] = [int(u["id"]) for u in allowed_users]
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
    if "explanation" in data and not str(data["explanation"]).strip():
        data["explanation"] = None
    tags = data.pop("tags", None)
    allowed_user_ids = data.pop("allowed_user_ids", None)
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
    if allowed_user_ids is not None:
        sync_problem_allowed_users(db, problem_id, allowed_user_ids)

    record_audit_log(
        db, current_user["id"], "problem.update", "problem", str(problem_id), get_client_ip(request)
    )
    invalidate_problem_caches()
    updated = db.fetchone("SELECT * FROM problems WHERE id = %s", (problem_id,))
    updated["tags"] = _get_problem_tags(db, problem_id)
    allowed_users = get_problem_allowed_users(db, problem_id)
    updated["allowed_users"] = allowed_users
    updated["allowed_user_ids"] = [int(u["id"]) for u in allowed_users]
    return updated


@router.get("/{problem_id}/access")
def get_problem_access(
    problem_id: int,
    current_user: dict = Depends(require_roles("admin", "teacher")),
    db: Database = Depends(get_db),
):
    prob = db.fetchone("SELECT * FROM problems WHERE id = %s AND deleted_at IS NULL", (problem_id,))
    if not prob:
        raise HTTPException(status_code=404, detail="Problem not found.")
    if not _can_edit_problem(current_user, prob):
        raise HTTPException(status_code=403, detail="Permission denied.")
    users = get_problem_allowed_users(db, problem_id)
    return {
        "problem_id": problem_id,
        "visibility": prob["visibility"],
        "submission_retention_mode": prob.get("submission_retention_mode") or "latest",
        "allowed_users": users,
        "allowed_user_ids": [int(u["id"]) for u in users],
    }


@router.patch("/{problem_id}/access")
def update_problem_access(
    problem_id: int,
    payload: ProblemAccessUpdateRequest,
    request: Request,
    current_user: dict = Depends(require_roles("admin", "teacher")),
    db: Database = Depends(get_db),
):
    prob = db.fetchone("SELECT * FROM problems WHERE id = %s AND deleted_at IS NULL", (problem_id,))
    if not prob:
        raise HTTPException(status_code=404, detail="Problem not found.")
    if not _can_edit_problem(current_user, prob):
        raise HTTPException(status_code=403, detail="You can only manage access for your own problems.")

    updates: Dict[str, Any] = {}
    if payload.visibility is not None:
        updates["visibility"] = payload.visibility
    if payload.submission_retention_mode is not None:
        updates["submission_retention_mode"] = payload.submission_retention_mode
    if updates:
        updates["updated_at"] = datetime.now(timezone.utc).isoformat()
        sets = ", ".join(f"{k} = %s" for k in updates.keys())
        db.execute(f"UPDATE problems SET {sets} WHERE id = %s", (*updates.values(), problem_id))

    if payload.allowed_user_ids is not None:
        sync_problem_allowed_users(db, problem_id, payload.allowed_user_ids)

    record_audit_log(
        db,
        current_user["id"],
        "problem.access.update",
        "problem",
        str(problem_id),
        get_client_ip(request),
        {
            "visibility": payload.visibility,
            "submission_retention_mode": payload.submission_retention_mode,
            "allowed_user_count": len(payload.allowed_user_ids) if payload.allowed_user_ids is not None else None,
        },
    )
    invalidate_problem_caches()
    refreshed = db.fetchone("SELECT visibility, submission_retention_mode FROM problems WHERE id = %s", (problem_id,))
    users = get_problem_allowed_users(db, problem_id)
    return {
        "problem_id": problem_id,
        "visibility": refreshed["visibility"],
        "submission_retention_mode": refreshed.get("submission_retention_mode") or "latest",
        "allowed_users": users,
        "allowed_user_ids": [int(u["id"]) for u in users],
    }


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
    invalidate_problem_caches()
    return {"deleted": True, "id": problem_id}
