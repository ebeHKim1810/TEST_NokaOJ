"""Admin & System Configuration API (/api/v1/admin)."""
from fastapi import APIRouter, Depends, Request

from backend.app.core.audit import record_audit_log
from backend.app.core.config import get_settings
from backend.app.core.database import Database, get_db
from backend.app.core.security import get_client_ip, require_roles
from backend.app.schemas.schemas import SystemSettingsUpdateRequest

router = APIRouter(prefix="/admin", tags=["Admin"])


@router.get("/public-config")
def get_public_config(db: Database = Depends(get_db)):
    """Centralized system branding & public settings consumed by Frontend."""
    rows = db.fetchall("SELECT key, value FROM system_settings")
    kv = {r["key"]: r["value"] for r in rows}
    return {
        "site_name": kv.get("site_name") or get_settings().app_name,
        "allow_registration": kv.get("allow_registration", "true").lower() == "true",
    }


@router.get("/stats")
def get_system_stats(
    current_user: dict = Depends(require_roles("admin", "teacher")),
    db: Database = Depends(get_db),
):
    def _cnt(sql: str) -> int:
        r = db.fetchone(sql)
        return int(r["cnt"]) if r else 0

    verdict_rows = db.fetchall(
        "SELECT verdict, COUNT(*) AS cnt FROM submissions GROUP BY verdict ORDER BY cnt DESC"
    )
    return {
        "users_count": _cnt("SELECT COUNT(*) AS cnt FROM users WHERE deleted_at IS NULL"),
        "problems_count": _cnt("SELECT COUNT(*) AS cnt FROM problems WHERE deleted_at IS NULL"),
        "submissions_count": _cnt("SELECT COUNT(*) AS cnt FROM submissions"),
        "contests_count": _cnt("SELECT COUNT(*) AS cnt FROM contests WHERE deleted_at IS NULL"),
        "classrooms_count": _cnt("SELECT COUNT(*) AS cnt FROM classrooms WHERE deleted_at IS NULL"),
        "verdict_breakdown": verdict_rows,
    }


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
