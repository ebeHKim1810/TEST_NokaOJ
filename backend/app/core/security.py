"""Security utilities: Argon2/scrypt password hashing, JWT authentication, and RBAC dependencies."""
import base64
import hashlib
import hmac
import json
import os
import time
from typing import Any, Callable, Dict, List, Optional

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from backend.app.core.cache import app_cache
from backend.app.core.config import get_settings
from backend.app.core.database import Database, get_db

bearer_scheme = HTTPBearer(auto_error=False)

# Prefer Argon2id when argon2-cffi is installed; fallback to cryptographic scrypt from stdlib.
try:
    from argon2 import PasswordHasher as _Argon2Hasher  # type: ignore

    _argon2 = _Argon2Hasher()
except Exception:
    _argon2 = None


def hash_password(password: str) -> str:
    if _argon2 is not None:
        return _argon2.hash(password)
    salt = os.urandom(16)
    dk = hashlib.scrypt(password.encode("utf-8"), salt=salt, n=16384, r=8, p=1, dklen=32)
    return "scrypt$" + base64.b64encode(salt).decode("ascii") + "$" + base64.b64encode(dk).decode("ascii")


# Alias matching standard FastAPI auth naming conventions
get_password_hash = hash_password


def verify_password(password: str, stored_hash: str) -> bool:
    if stored_hash.startswith("$argon2") and _argon2 is not None:
        try:
            return bool(_argon2.verify(stored_hash, password))
        except Exception:
            return False
    if stored_hash.startswith("scrypt$"):
        try:
            _, salt_b64, dk_b64 = stored_hash.split("$", 2)
            salt = base64.b64decode(salt_b64)
            expected = base64.b64decode(dk_b64)
            actual = hashlib.scrypt(password.encode("utf-8"), salt=salt, n=16384, r=8, p=1, dklen=32)
            return hmac.compare_digest(actual, expected)
        except Exception:
            return False
    return False


def _b64url_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _b64url_decode(data: str) -> bytes:
    padding = "=" * (-len(data) % 4)
    return base64.urlsafe_b64decode(data + padding)


def create_access_token(subject: Dict[str, Any], expires_minutes: Optional[int] = None) -> str:
    settings = get_settings()
    ttl = (expires_minutes or settings.access_token_expire_minutes) * 60
    now = int(time.time())
    payload = {**subject, "iat": now, "exp": now + ttl}
    header = {"alg": "HS256", "typ": "JWT"}
    h_b64 = _b64url_encode(json.dumps(header, separators=(",", ":")).encode("utf-8"))
    p_b64 = _b64url_encode(json.dumps(payload, separators=(",", ":")).encode("utf-8"))
    signing_input = f"{h_b64}.{p_b64}".encode("ascii")
    sig = hmac.new(settings.secret_key.encode("utf-8"), signing_input, hashlib.sha256).digest()
    return f"{h_b64}.{p_b64}.{_b64url_encode(sig)}"


def decode_access_token(token: str) -> Dict[str, Any]:
    settings = get_settings()
    try:
        parts = token.split(".")
        if len(parts) != 3:
            raise ValueError("Invalid token format")
        h_b64, p_b64, s_b64 = parts
        signing_input = f"{h_b64}.{p_b64}".encode("ascii")
        expected_sig = hmac.new(
            settings.secret_key.encode("utf-8"), signing_input, hashlib.sha256
        ).digest()
        actual_sig = _b64url_decode(s_b64)
        if not hmac.compare_digest(expected_sig, actual_sig):
            raise ValueError("Invalid token signature")
        payload = json.loads(_b64url_decode(p_b64).decode("utf-8"))
        if int(payload.get("exp", 0)) < int(time.time()):
            raise ValueError("Token expired")
        return payload
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Invalid or expired authentication token: {exc}",
        )


def get_user_roles(db: Database, user_id: int) -> List[str]:
    rows = db.fetchall(
        """
        SELECT r.name
        FROM roles r
        JOIN user_roles ur ON ur.role_id = r.id
        WHERE ur.user_id = %s
        ORDER BY r.id ASC
        """,
        (user_id,),
    )
    return [r["name"] for r in rows]


def load_user_by_id(db: Database, user_id: int) -> Optional[Dict[str, Any]]:
    cache_key = f"user_auth:{user_id}"
    cached = app_cache.get(cache_key)
    if cached is not None:
        return cached

    rows = db.fetchall(
        """
        SELECT u.id, u.username, u.email, u.full_name, u.is_active, u.created_at,
               r.name AS role_name
        FROM users u
        LEFT JOIN user_roles ur ON ur.user_id = u.id
        LEFT JOIN roles r ON r.id = ur.role_id
        WHERE u.id = %s AND u.deleted_at IS NULL
        ORDER BY r.id ASC
        """,
        (user_id,),
    )
    if not rows or not rows[0]["is_active"]:
        return None
    first = rows[0]
    roles = [r["role_name"] for r in rows if r.get("role_name")]
    user = {
        "id": first["id"],
        "username": first["username"],
        "email": first["email"],
        "full_name": first["full_name"],
        "is_active": bool(first["is_active"]),
        "created_at": first["created_at"],
        "roles": roles,
    }
    app_cache.set(cache_key, user, ttl_seconds=30.0)
    return user


def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(bearer_scheme),
    db: Database = Depends(get_db),
) -> Dict[str, Any]:
    if not credentials or not credentials.credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required.",
        )
    payload = decode_access_token(credentials.credentials)
    user = load_user_by_id(db, int(payload["sub"]))
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Account not found or disabled.",
        )
    return user


def get_optional_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(bearer_scheme),
    db: Database = Depends(get_db),
) -> Optional[Dict[str, Any]]:
    if not credentials or not credentials.credentials:
        return None
    try:
        payload = decode_access_token(credentials.credentials)
        return load_user_by_id(db, int(payload["sub"]))
    except HTTPException:
        return None


def require_roles(*allowed_roles: str) -> Callable:
    def _checker(user: Dict[str, Any] = Depends(get_current_user)) -> Dict[str, Any]:
        user_roles = set(user.get("roles", []))
        if not user_roles.intersection(set(allowed_roles)):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You do not have permission to perform this action.",
            )
        return user

    return _checker


def is_admin(user: Optional[Dict[str, Any]]) -> bool:
    return bool(user and "admin" in user.get("roles", []))


def is_staff(user: Optional[Dict[str, Any]]) -> bool:
    return bool(user and ({"admin", "teacher"} & set(user.get("roles", []))))


def get_client_ip(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"
