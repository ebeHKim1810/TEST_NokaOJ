"""Lightweight thread-safe in-memory TTL cache for stateless FastAPI (512 MB RAM safe)."""
import copy
import threading
import time
from typing import Any, Callable, Dict, Optional, Tuple, TypeVar

T = TypeVar("T")


class InMemoryTTLCache:
    def __init__(self, max_entries: int = 1024) -> None:
        self._lock = threading.RLock()
        self._store: Dict[str, Tuple[float, Any]] = {}
        self._max_entries = max_entries

    def get(self, key: str) -> Optional[Any]:
        now = time.monotonic()
        with self._lock:
            entry = self._store.get(key)
            if entry is None:
                return None
            expires_at, val = entry
            if now >= expires_at:
                self._store.pop(key, None)
                return None
            return copy.deepcopy(val)

    def set(self, key: str, value: Any, ttl_seconds: float = 45.0) -> None:
        now = time.monotonic()
        with self._lock:
            if len(self._store) >= self._max_entries:
                # Evict expired entries first, then oldest entry
                expired = [k for k, (exp, _) in self._store.items() if now >= exp]
                for k in expired:
                    self._store.pop(k, None)
                if len(self._store) >= self._max_entries:
                    oldest_key = min(self._store.items(), key=lambda kv: kv[1][0])[0]
                    self._store.pop(oldest_key, None)
            self._store[key] = (now + ttl_seconds, copy.deepcopy(value))

    def get_or_set(self, key: str, loader: Callable[[], T], ttl_seconds: float = 45.0) -> T:
        cached = self.get(key)
        if cached is not None:
            return cached
        val = loader()
        self.set(key, val, ttl_seconds=ttl_seconds)
        return copy.deepcopy(val)

    def invalidate_prefix(self, *prefixes: str) -> int:
        removed = 0
        with self._lock:
            keys = [k for k in self._store.keys() if any(k.startswith(p) for p in prefixes)]
            for k in keys:
                self._store.pop(k, None)
                removed += 1
        return removed

    def clear(self) -> None:
        with self._lock:
            self._store.clear()


app_cache = InMemoryTTLCache(max_entries=1024)


def invalidate_problem_caches() -> None:
    app_cache.invalidate_prefix("problems:", "problem_detail:", "tags:", "admin_stats:")


def invalidate_contest_caches() -> None:
    app_cache.invalidate_prefix("contests:", "scoreboard:", "admin_stats:")


def invalidate_submission_caches() -> None:
    app_cache.invalidate_prefix("problems:", "scoreboard:", "admin_stats:")


def invalidate_user_caches(user_id: Optional[int] = None) -> None:
    if user_id is not None:
        app_cache.invalidate_prefix(f"user_auth:{user_id}", "admin_stats:")
    else:
        app_cache.invalidate_prefix("user_auth:", "admin_stats:")


def invalidate_settings_caches() -> None:
    app_cache.invalidate_prefix("public_config:")
