"""User management API routes (/api/v1/users)."""
from fastapi import APIRouter, Depends, HTTPException, Request, status

from backend.app.core.audit import record_audit_log
from backend.app.core.database import Database, get_db
from backend.app.core.security import (
    get_client_ip,
    get_user_roles,
    hash_password,
    is_admin,
    require_roles,
)
from backend.app.schemas.schemas import UserCreateRequest, UserUpdateRequest

router = APIRouter(prefix="/users", tags=["Users"])


@router.get("")
def list_users(
    search: str = "",
    role: str = "",
    current_user: dict = Depends(require_roles("admin", "teacher")),
    db: Database = Depends(get_db),
):
    params = []
    where = ["u.deleted_at IS NULL"]
    if search:
        where.append("(u.username ILIKE %s OR u.email ILIKE %s OR u.full_name ILIKE %s)")
        like = f"%{search}%"
        params.extend([like, like, like])
    rows = db.fetchall(
        f"""
        SELECT u.id, u.username, u.email, u.full_name, u.is_active, u.created_at
        FROM users u
        WHERE {' AND '.join(where)}
        ORDER BY u.id DESC
        LIMIT 200
        """,
        tuple(params),
    )
    result = []
    for row in rows:
        roles = get_user_roles(db, int(row["id"]))
        if role and role not in roles:
            continue
        row["roles"] = roles
        result.append(row)
    return {"items": result, "total": len(result)}


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
        "SELECT id FROM users WHERE username = %s OR email = %s",
        (payload.username, payload.email),
    )
    if existing:
        raise HTTPException(status_code=409, detail="Username or email already exists.")

    uid = db.insert_returning_id(
        """
        INSERT INTO users (username, email, full_name, password_hash, is_active)
        VALUES (%s, %s, %s, %s, %s)
        """,
        (
            payload.username,
            payload.email,
            payload.full_name or payload.username,
            hash_password(payload.password),
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
        {"username": payload.username, "roles": payload.roles},
    )
    return {
        "id": uid,
        "username": payload.username,
        "email": payload.email,
        "full_name": payload.full_name or payload.username,
        "roles": get_user_roles(db, uid),
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
    user = db.fetchone("SELECT id FROM users WHERE id = %s AND deleted_at IS NULL", (user_id,))
    if not user:
        raise HTTPException(status_code=404, detail="User not found.")
    if user_id == int(current_user["id"]) and payload.is_active is False:
        raise HTTPException(
            status_code=400,
            detail="Không thể tự vô hiệu hóa tài khoản đang đăng nhập.",
        )

    if payload.full_name is not None:
        db.execute("UPDATE users SET full_name = %s WHERE id = %s", (payload.full_name, user_id))
    if payload.is_active is not None:
        db.execute("UPDATE users SET is_active = %s WHERE id = %s", (payload.is_active, user_id))
    if payload.roles is not None:
        db.execute("DELETE FROM user_roles WHERE user_id = %s", (user_id,))
        for rname in set(payload.roles):
            r = db.fetchone("SELECT id FROM roles WHERE name = %s", (rname,))
            if r:
                db.execute("INSERT INTO user_roles (user_id, role_id) VALUES (%s, %s)", (user_id, r["id"]))

    record_audit_log(
        db,
        current_user["id"],
        "user.update",
        "user",
        str(user_id),
        get_client_ip(request),
        (payload.model_dump(exclude_none=True) if hasattr(payload, "model_dump") else payload.dict(exclude_none=True)),
    )
    updated = db.fetchone(
        "SELECT id, username, email, full_name, is_active, created_at FROM users WHERE id = %s",
        (user_id,),
    )
    updated["roles"] = get_user_roles(db, user_id)
    return updated


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
    return {"deleted": True, "user_id": user_id}
