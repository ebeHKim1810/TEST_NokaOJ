"""Audit logging helper for administrative and security-sensitive operations."""
import json
from typing import Any, Dict, Optional

from backend.app.core.database import Database


def record_audit_log(
    db: Database,
    user_id: Optional[int],
    action: str,
    entity_type: str,
    entity_id: str = "",
    ip_address: str = "",
    details: Optional[Dict[str, Any]] = None,
) -> None:
    try:
        db.execute(
            """
            INSERT INTO audit_logs (user_id, action, entity_type, entity_id, ip_address, details_json)
            VALUES (%s, %s, %s, %s, %s, %s)
            """,
            (
                user_id,
                action,
                entity_type,
                str(entity_id),
                ip_address,
                json.dumps(details or {}, ensure_ascii=False),
            ),
        )
    except Exception:
        pass
