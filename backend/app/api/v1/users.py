"""User management API routes (/api/v1/users)."""
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Request, status

from backend.app.core.audit import record_audit_log
from backend.app.core.cache import app_cache, invalidate_user_caches
from backend.app.core.database import Database, get_db
from backend.app.core.security import (
    get_client_ip,
    get_password_hash,
    get_user_roles,
    is_admin,
    require_roles,
)
from backend.app.schemas.schemas import UserCreateRequest, UserUpdateRequest

router = APIRouter(prefix="/users", tags=["Users"])


def _primary_role(roles: List[str]) -> str:
    if "admin" in roles:
        return "admin"
    if "teacher" in roles:
        return "teacher"
    if "student" in roles:
        return "student"
    return roles[0] if roles else "student"


def _list_users_impl(db: Database, search: str = "", role: str = "", limit: int = 500) -> dict:
    params: list = []
    where = ["u.deleted_at IS NULL"]
    cleaned_search = (search or "").strip()
    if cleaned_search:
        where.append("(u.username ILIKE %s OR u.email ILIKE %s OR u.full_name ILIKE %s)")
        like = f"%{cleaned_search}%"
        params.extend([like, like, like])
    cleaned_role = (role or "").strip()
    if cleaned_role:
        where.append(
            "EXISTS (SELECT 1 FROM user_roles ur JOIN roles r ON r.id = ur.role_id "
            "WHERE ur.user_id = u.id AND r.name = %s)"
        )
        params.append(cleaned_role)
    safe_limit = min(2000, max(1, int(limit)))
    params.append(safe_limit)
    rows = db.fetchall(
        f"""
        SELECT u.id, u.username, u.email, u.full_name, u.is_active, u.created_at
        FROM users u
        WHERE {' AND '.join(where)}
        ORDER BY u.id DESC
        LIMIT %s
        """,
        tuple(params),
    )
    if not rows:
        return {"items": [], "total": 0}
    uids = [int(r["id"]) for r in rows]
    ph = ", ".join(["%s"] * len(uids))
    role_rows = db.fetchall(
        f"""
        SELECT ur.user_id, r.name
        FROM user_roles ur
        JOIN roles r ON r.id = ur.role_id
        WHERE ur.user_id IN ({ph})
        ORDER BY r.id ASC
        """,
        tuple(uids),
    )
    roles_map: dict[int, list[str]] = {}
    for rr in role_rows:
        roles_map.setdefault(int(rr["user_id"]), []).append(rr["name"])

    result = []
    for row in rows:
        roles = roles_map.get(int(row["id"]), [])
        row["is_active"] = bool(row["is_active"])
        row["roles"] = roles
        row["role"] = _primary_role(roles)
        result.append(row)
    return {"items": result, "total": len(result)}


def _update_user_impl(
    user_id: int,
    payload: UserUpdateRequest,
    request: Request,
    current_user: dict,
    db: Database,
) -> dict:
    user = db.fetchone(
        "SELECT id, username, email, full_name, is_active FROM users WHERE id = %s AND deleted_at IS NULL",
        (user_id,),
    )
    if not user:
        raise HTTPException(status_code=404, detail="Không tìm thấy tài khoản người dùng.")

    is_self = user_id == int(current_user["id"])

    # Resolve target roles (supports both `roles: [...]` and single `role: "..."`)
    target_roles: Optional[List[str]] = None
    if payload.roles is not None:
        target_roles = list(dict.fromkeys(payload.roles))
    elif payload.role is not None:
        target_roles = [payload.role]

    if target_roles is not None and len(target_roles) == 0:
        raise HTTPException(status_code=400, detail="Tài khoản phải có ít nhất một vai trò.")

    # Self-protection: Admin cannot deactivate/lock or demote their own active account
    if is_self and payload.is_active is False:
        raise HTTPException(
            status_code=400,
            detail="Không thể tự khóa hoặc vô hiệu hóa tài khoản đang đăng nhập.",
        )
    if is_self and target_roles is not None and "admin" not in target_roles:
        raise HTTPException(
            status_code=400,
            detail="Không thể tự hạ quyền Admin của chính tài khoản đang đăng nhập.",
        )

    # Validate username if provided
    new_username: Optional[str] = None
    if payload.username is not None:
        new_username = payload.username.strip()
        if len(new_username) < 3 or len(new_username) > 64 or any(ch.isspace() for ch in new_username):
            raise HTTPException(
                status_code=400,
                detail="Tên đăng nhập phải từ 3 đến 64 ký tự và không chứa khoảng trắng.",
            )
        dup_user = db.fetchone(
            "SELECT id FROM users WHERE LOWER(username) = LOWER(%s) AND id <> %s",
            (new_username, user_id),
        )
        if dup_user:
            raise HTTPException(
                status_code=400,
                detail="Tên đăng nhập này đã tồn tại",
            )

    # Validate email if provided
    new_email: Optional[str] = None
    if payload.email is not None:
        new_email = payload.email.strip()
        if len(new_email) < 5 or "@" not in new_email:
            raise HTTPException(status_code=400, detail="Địa chỉ email không hợp lệ.")
        dup_email = db.fetchone(
            "SELECT id FROM users WHERE LOWER(email) = LOWER(%s) AND id <> %s",
            (new_email, user_id),
        )
        if dup_email:
            raise HTTPException(status_code=400, detail="Email này đã tồn tại.")

    # Validate new_password if provided and non-empty
    password_to_hash: Optional[str] = None
    if payload.new_password is not None and payload.new_password != "":
        if len(payload.new_password) < 6:
            raise HTTPException(
                status_code=400,
                detail="Mật khẩu mới phải có ít nhất 6 ký tự.",
            )
        if payload.new_password.strip() == "":
            raise HTTPException(
                status_code=400,
                detail="Mật khẩu mới không được chỉ chứa khoảng trắng.",
            )
        password_to_hash = payload.new_password

    # Build atomic UPDATE statement for user columns
    set_clauses: List[str] = []
    set_params: list = []
    audit_details: dict = {}

    if new_username is not None:
        set_clauses.append("username = %s")
        set_params.append(new_username)
        if new_username != user["username"]:
            audit_details["old_username"] = user["username"]
            audit_details["username"] = new_username
    if payload.full_name is not None:
        cleaned_full_name = payload.full_name.strip()
        set_clauses.append("full_name = %s")
        set_params.append(cleaned_full_name)
        audit_details["full_name"] = cleaned_full_name
    if new_email is not None:
        set_clauses.append("email = %s")
        set_params.append(new_email)
        audit_details["email"] = new_email
    if payload.is_active is not None:
        set_clauses.append("is_active = %s")
        set_params.append(payload.is_active)
        audit_details["is_active"] = payload.is_active
    if password_to_hash is not None:
        set_clauses.append("password_hash = %s")
        set_params.append(get_password_hash(password_to_hash))
        audit_details["password_reset"] = True

    if set_clauses:
        set_clauses.append("updated_at = CURRENT_TIMESTAMP")
        set_params.append(user_id)
        db.execute(
            f"UPDATE users SET {', '.join(set_clauses)} WHERE id = %s",
            tuple(set_params),
        )

    if target_roles is not None:
        db.execute("DELETE FROM user_roles WHERE user_id = %s", (user_id,))
        for rname in target_roles:
            r = db.fetchone("SELECT id FROM roles WHERE name = %s", (rname,))
            if r:
                db.execute("INSERT INTO user_roles (user_id, role_id) VALUES (%s, %s)", (user_id, r["id"]))
        audit_details["roles"] = target_roles

    record_audit_log(
        db,
        current_user["id"],
        "user.update",
        "user",
        str(user_id),
        get_client_ip(request),
        audit_details,
    )
    invalidate_user_caches(user_id)
    if new_username is not None or payload.full_name is not None:
        app_cache.invalidate_prefix("scoreboard:")

    updated = db.fetchone(
        "SELECT id, username, email, full_name, is_active, created_at FROM users WHERE id = %s",
        (user_id,),
    )
    roles = get_user_roles(db, user_id)
    updated["is_active"] = bool(updated["is_active"])
    updated["roles"] = roles
    updated["role"] = _primary_role(roles)
    return updated


@router.get("")
def list_users(
    search: str = "",
    role: str = "",
    limit: int = 500,
    current_user: dict = Depends(require_roles("admin", "teacher")),
    db: Database = Depends(get_db),
):
    return _list_users_impl(db, search=search, role=role, limit=limit)


@router.post("", status_code=status.HTTP_201_CREATED)
def create_user(
    payload: UserCreateRequest,
    request: Request,
    current_user: dict = Depends(require_roles("admin", "teacher")),
    db: Database = Depends(get_db),
):
    # Teachers can only create student accounts; only Admins can assign teacher/admin roles
    if not is_admin(current_user) and any(r != "student" for r in payload.roles):
        raise HTTPException(
            status_code=403,
            detail="Only administrators can assign teacher or admin roles.",
        )

    existing = db.fetchone(
        "SELECT id FROM users WHERE LOWER(username) = LOWER(%s) OR LOWER(email) = LOWER(%s)",
        (payload.username.strip(), payload.email.strip()),
    )
    if existing:
        raise HTTPException(status_code=409, detail="Username or email already exists.")

    cleaned_username = payload.username.strip()
    cleaned_email = payload.email.strip()
    cleaned_full_name = (payload.full_name or "").strip() or cleaned_username

    uid = db.insert_returning_id(
        """
        INSERT INTO users (username, email, full_name, password_hash, is_active)
        VALUES (%s, %s, %s, %s, %s)
        """,
        (
            cleaned_username,
            cleaned_email,
            cleaned_full_name,
            get_password_hash(payload.password),
            True,
        ),
    )
    for rname in set(payload.roles):
        r = db.fetchone("SELECT id FROM roles WHERE name = %s", (rname,))
        if r:
            db.execute(
                "INSERT INTO user_roles (user_id, role_id) VALUES (%s, %s)",
                (uid, r["id"]),
            )
    record_audit_log(
        db,
        current_user["id"],
        "user.create",
        "user",
        str(uid),
        get_client_ip(request),
        {"username": cleaned_username, "roles": payload.roles},
    )
    invalidate_user_caches(uid)
    roles = get_user_roles(db, uid)
    return {
        "id": uid,
        "username": cleaned_username,
        "email": cleaned_email,
        "full_name": cleaned_full_name,
        "roles": roles,
        "role": _primary_role(roles),
        "is_active": True,
    }


@router.patch("/{user_id}")
def update_user(
    user_id: int,
    payload: UserUpdateRequest,
    request: Request,
    current_user: dict = Depends(require_roles("admin")),
    db: Database = Depends(get_db),
):
    return _update_user_impl(user_id, payload, request, current_user, db)


@router.delete("/{user_id}")
def delete_user(
    user_id: int,
    request: Request,
    current_user: dict = Depends(require_roles("admin")),
    db: Database = Depends(get_db),
):
    if user_id == int(current_user["id"]):
        raise HTTPException(
            status_code=400,
            detail="Không thể tự xóa tài khoản đang đăng nhập.",
        )
    user = db.fetchone(
        "SELECT id, username, email FROM users WHERE id = %s AND deleted_at IS NULL",
        (user_id,),
    )
    if not user:
        raise HTTPException(status_code=404, detail="User not found.")

    db.execute("DELETE FROM users WHERE id = %s", (user_id,))
    record_audit_log(
        db,
        current_user["id"],
        "user.delete",
        "user",
        str(user_id),
        get_client_ip(request),
        {"username": user["username"], "email": user["email"]},
    )
    invalidate_user_caches(user_id)
    return {"deleted": True, "user_id": user_id}
