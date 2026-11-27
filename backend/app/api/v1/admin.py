"""Admin & System Configuration API (/api/v1/admin)."""
from fastapi import APIRouter, Depends, Request

from backend.app.api.v1.users import _list_users_impl, _update_user_impl
from backend.app.core.audit import record_audit_log
from backend.app.core.cache import app_cache, invalidate_settings_caches
from backend.app.core.config import get_settings
from backend.app.core.database import Database, get_db
from backend.app.core.security import get_client_ip, require_roles
from backend.app.schemas.schemas import SystemSettingsUpdateRequest, UserUpdateRequest

router = APIRouter(prefix="/admin", tags=["Admin"])


@router.get("/public-config")
def get_public_config(db: Database = Depends(get_db)):
    """Centralized system branding & public settings consumed by Frontend (60s TTL cached)."""
    def _load():
        rows = db.fetchall("SELECT key, value FROM system_settings")
        kv = {r["key"]: r["value"] for r in rows}
        return {
            "site_name": kv.get("site_name") or get_settings().app_name,
            "allow_registration": kv.get("allow_registration", "true").lower() == "true",
        }

    return app_cache.get_or_set("public_config:global", _load, ttl_seconds=60.0)


@router.get("/stats")
def get_system_stats(
    current_user: dict = Depends(require_roles("admin", "teacher")),
    db: Database = Depends(get_db),
):
    def _load():
        counts = db.fetchone(
            """
            SELECT
                (SELECT COUNT(*) FROM users WHERE deleted_at IS NULL) AS users_count,
                (SELECT COUNT(*) FROM problems WHERE deleted_at IS NULL) AS problems_count,
                (SELECT COUNT(*) FROM submissions) AS submissions_count,
                (SELECT COUNT(*) FROM contests WHERE deleted_at IS NULL) AS contests_count,
                (SELECT COUNT(*) FROM classrooms WHERE deleted_at IS NULL) AS classrooms_count
            """
        )
        verdict_rows = db.fetchall(
            "SELECT verdict, COUNT(*) AS cnt FROM submissions GROUP BY verdict ORDER BY cnt DESC"
        )
        return {
            "users_count": int(counts["users_count"]) if counts else 0,
            "problems_count": int(counts["problems_count"]) if counts else 0,
            "submissions_count": int(counts["submissions_count"]) if counts else 0,
            "contests_count": int(counts["contests_count"]) if counts else 0,
            "classrooms_count": int(counts["classrooms_count"]) if counts else 0,
            "verdict_breakdown": verdict_rows,
        }

    return app_cache.get_or_set("admin_stats:global", _load, ttl_seconds=30.0)


@router.get("/settings")
def get_admin_settings(
    current_user: dict = Depends(require_roles("admin")),
    db: Database = Depends(get_db),
):
    rows = db.fetchall("SELECT key, value, updated_at FROM system_settings ORDER BY key ASC")
    return {"settings": {r["key"]: r["value"] for r in rows}}


@router.put("/settings")
def update_admin_settings(
    payload: SystemSettingsUpdateRequest,
    request: Request,
    current_user: dict = Depends(require_roles("admin")),
    db: Database = Depends(get_db),
):
    for k, v in payload.settings.items():
        existing = db.fetchone("SELECT key FROM system_settings WHERE key = %s", (k,))
        if existing:
            db.execute("UPDATE system_settings SET value = %s WHERE key = %s", (v, k))
        else:
            db.execute("INSERT INTO system_settings (key, value) VALUES (%s, %s)", (k, v))
    record_audit_log(
        db,
        current_user["id"],
        "settings.update",
        "system_settings",
        "global",
        get_client_ip(request),
        payload.settings,
    )
    invalidate_settings_caches()
    return {"updated": True, "settings": payload.settings}


@router.get("/audit-logs")
def list_audit_logs(
    limit: int = 100,
    current_user: dict = Depends(require_roles("admin")),
    db: Database = Depends(get_db),
):
    rows = db.fetchall(
        """
        SELECT a.*, u.username
        FROM audit_logs a
        LEFT JOIN users u ON u.id = a.user_id
        ORDER BY a.id DESC
        LIMIT %s
        """,
        (min(500, max(1, limit)),),
    )
    return {"items": rows}


@router.get("/users")
def admin_list_users(
    search: str = "",
    role: str = "",
    limit: int = 500,
    current_user: dict = Depends(require_roles("admin")),
    db: Database = Depends(get_db),
):
    return _list_users_impl(db, search=search, role=role, limit=limit)


@router.put("/users/{user_id}")
@router.patch("/users/{user_id}")
def admin_update_user(
    user_id: int,
    payload: UserUpdateRequest,
    request: Request,
    current_user: dict = Depends(require_roles("admin")),
    db: Database = Depends(get_db),
):
    return _update_user_impl(user_id, payload, request, current_user, db)
