"""Authentication API routes (/api/v1/auth)."""
from fastapi import APIRouter, Depends, HTTPException, Request, status

from backend.app.core.audit import record_audit_log
from backend.app.core.database import Database, get_db
from backend.app.core.security import (
    create_access_token,
    get_client_ip,
    get_current_user,
    get_user_roles,
    hash_password,
    verify_password,
)
from backend.app.schemas.schemas import LoginRequest, RegisterRequest

router = APIRouter(prefix="/auth", tags=["Authentication"])


@router.post("/register", status_code=status.HTTP_201_CREATED)
def register(
    payload: RegisterRequest,
    request: Request,
    db: Database = Depends(get_db),
):
    setting = db.fetchone("SELECT value FROM system_settings WHERE key = 'allow_registration'")
    if setting and setting["value"].lower() != "true":
        raise HTTPException(status_code=403, detail="Public registration is disabled.")

    existing = db.fetchone(
        "SELECT id FROM users WHERE username = %s OR email = %s",
        (payload.username, payload.email),
    )
    if existing:
        raise HTTPException(status_code=409, detail="Username or email already exists.")

    pw_hash = hash_password(payload.password)
    user_id = db.insert_returning_id(
        """
        INSERT INTO users (username, email, full_name, password_hash, is_active)
        VALUES (%s, %s, %s, %s, %s)
        """,
        (payload.username, payload.email, payload.full_name or payload.username, pw_hash, True),
    )
    role = db.fetchone("SELECT id FROM roles WHERE name = 'student'")
    if role:
        db.execute(
            "INSERT INTO user_roles (user_id, role_id) VALUES (%s, %s)",
            (user_id, role["id"]),
        )
    record_audit_log(db, user_id, "user.register", "user", str(user_id), get_client_ip(request))
    roles = get_user_roles(db, user_id)
    token = create_access_token({"sub": str(user_id), "username": payload.username, "roles": roles})
    return {
        "access_token": token,
        "token_type": "bearer",
        "user": {
            "id": user_id,
            "username": payload.username,
            "email": payload.email,
            "full_name": payload.full_name or payload.username,
            "roles": roles,
        },
    }


@router.post("/login")
def login(
    payload: LoginRequest,
    request: Request,
    db: Database = Depends(get_db),
):
    user = db.fetchone(
        """
        SELECT id, username, email, full_name, password_hash, is_active
        FROM users
        WHERE (username = %s OR email = %s) AND deleted_at IS NULL
        """,
        (payload.username, payload.username),
    )
    if not user or not verify_password(payload.password, user["password_hash"]):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid username or password.",
        )
    if not user["is_active"]:
        raise HTTPException(status_code=403, detail="Account is disabled.")

    roles = get_user_roles(db, int(user["id"]))
    token = create_access_token({"sub": str(user["id"]), "username": user["username"], "roles": roles})
    record_audit_log(db, int(user["id"]), "user.login", "user", str(user["id"]), get_client_ip(request))
    return {
        "access_token": token,
        "token_type": "bearer",
        "user": {
            "id": int(user["id"]),
            "username": user["username"],
            "email": user["email"],
            "full_name": user["full_name"],
            "roles": roles,
        },
    }


@router.get("/me")
def get_me(current_user: dict = Depends(get_current_user), db: Database = Depends(get_db)):
    row = db.fetchone(
        """
        SELECT COUNT(DISTINCT CASE WHEN verdict = 'AC' THEN problem_id END) AS solved_cnt,
               COUNT(*) AS total_cnt
        FROM submissions
        WHERE user_id = %s
        """,
        (current_user["id"],),
    )
    return {
        **current_user,
        "stats": {
            "solved_count": int(row["solved_cnt"]) if row and row["solved_cnt"] is not None else 0,
            "submission_count": int(row["total_cnt"]) if row and row["total_cnt"] is not None else 0,
        },
    }
