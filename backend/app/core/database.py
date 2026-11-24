"""
Unified parameterized database abstraction for PostgreSQL (production)
and SQLite (lightweight local dev & automated test suite).
100% parameterized queries to prevent SQL injection.
"""
import os
import re
import sqlite3
import threading
import time
from contextlib import contextmanager
from typing import Any, Callable, Dict, Iterator, List, Optional, Sequence, TypeVar

from backend.app.core.config import get_settings

T = TypeVar("T")


SQLITE_SCHEMA_SQL = """
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS roles (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name VARCHAR(32) NOT NULL UNIQUE,
    description TEXT DEFAULT '',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username VARCHAR(64) NOT NULL UNIQUE,
    email VARCHAR(255) NOT NULL UNIQUE,
    full_name VARCHAR(128) NOT NULL DEFAULT '',
    password_hash TEXT NOT NULL,
    is_active BOOLEAN NOT NULL DEFAULT 1,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    deleted_at TIMESTAMP NULL
);

CREATE TABLE IF NOT EXISTS user_roles (
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    role_id INTEGER NOT NULL REFERENCES roles(id) ON DELETE CASCADE,
    assigned_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (user_id, role_id)
);

CREATE TABLE IF NOT EXISTS tags (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name VARCHAR(64) NOT NULL UNIQUE,
    slug VARCHAR(64) NOT NULL UNIQUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS problems (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    code VARCHAR(32) NOT NULL UNIQUE,
    title VARCHAR(255) NOT NULL,
    statement_md TEXT NOT NULL DEFAULT '',
    input_description TEXT NOT NULL DEFAULT '',
    output_description TEXT NOT NULL DEFAULT '',
    constraints_md TEXT NOT NULL DEFAULT '',
    sample_input TEXT NOT NULL DEFAULT '',
    sample_output TEXT NOT NULL DEFAULT '',
    time_limit_ms INTEGER NOT NULL DEFAULT 1000,
    memory_limit_mb INTEGER NOT NULL DEFAULT 256,
    points INTEGER NOT NULL DEFAULT 100,
    difficulty VARCHAR(16) NOT NULL DEFAULT 'easy',
    visibility VARCHAR(16) NOT NULL DEFAULT 'public',
    submission_retention_mode VARCHAR(16) NOT NULL DEFAULT 'latest',
    checker_type VARCHAR(32) NOT NULL DEFAULT 'standard',
    checker_storage_key TEXT NULL,
    created_by INTEGER REFERENCES users(id) ON DELETE SET NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    deleted_at TIMESTAMP NULL
);

CREATE TABLE IF NOT EXISTS problem_tags (
    problem_id INTEGER NOT NULL REFERENCES problems(id) ON DELETE CASCADE,
    tag_id INTEGER NOT NULL REFERENCES tags(id) ON DELETE CASCADE,
    PRIMARY KEY (problem_id, tag_id)
);

CREATE TABLE IF NOT EXISTS problem_allowed_users (
    problem_id INTEGER NOT NULL REFERENCES problems(id) ON DELETE CASCADE,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (problem_id, user_id)
);

CREATE TABLE IF NOT EXISTS testcase_groups (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    problem_id INTEGER NOT NULL REFERENCES problems(id) ON DELETE CASCADE,
    name VARCHAR(128) NOT NULL DEFAULT 'Default Subtask',
    points INTEGER NOT NULL DEFAULT 100,
    order_index INTEGER NOT NULL DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS testcases (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    problem_id INTEGER NOT NULL REFERENCES problems(id) ON DELETE CASCADE,
    group_id INTEGER NULL REFERENCES testcase_groups(id) ON DELETE SET NULL,
    name VARCHAR(64) NOT NULL,
    input_storage_key TEXT NOT NULL,
    output_storage_key TEXT NOT NULL,
    input_size_bytes INTEGER NOT NULL DEFAULT 0,
    output_size_bytes INTEGER NOT NULL DEFAULT 0,
    is_sample BOOLEAN NOT NULL DEFAULT 0,
    is_hidden BOOLEAN NOT NULL DEFAULT 1,
    order_index INTEGER NOT NULL DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS classrooms (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name VARCHAR(160) NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    join_code VARCHAR(16) NOT NULL UNIQUE,
    teacher_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
    is_active BOOLEAN NOT NULL DEFAULT 1,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    deleted_at TIMESTAMP NULL
);

CREATE TABLE IF NOT EXISTS classroom_students (
    classroom_id INTEGER NOT NULL REFERENCES classrooms(id) ON DELETE CASCADE,
    student_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    joined_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (classroom_id, student_id)
);

CREATE TABLE IF NOT EXISTS assignments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    classroom_id INTEGER NOT NULL REFERENCES classrooms(id) ON DELETE CASCADE,
    title VARCHAR(200) NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    due_at TIMESTAMP NULL,
    created_by INTEGER REFERENCES users(id) ON DELETE SET NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    deleted_at TIMESTAMP NULL
);

CREATE TABLE IF NOT EXISTS assignment_problems (
    assignment_id INTEGER NOT NULL REFERENCES assignments(id) ON DELETE CASCADE,
    problem_id INTEGER NOT NULL REFERENCES problems(id) ON DELETE CASCADE,
    points INTEGER NOT NULL DEFAULT 100,
    order_index INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (assignment_id, problem_id)
);

CREATE TABLE IF NOT EXISTS contests (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title VARCHAR(200) NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    start_time TIMESTAMP NOT NULL,
    end_time TIMESTAMP NOT NULL,
    visibility VARCHAR(16) NOT NULL DEFAULT 'public',
    classroom_id INTEGER NULL REFERENCES classrooms(id) ON DELETE SET NULL,
    penalty_minutes INTEGER NOT NULL DEFAULT 20,
    freeze_before_end_minutes INTEGER NOT NULL DEFAULT 0,
    is_scoreboard_enabled BOOLEAN NOT NULL DEFAULT 1,
    created_by INTEGER REFERENCES users(id) ON DELETE SET NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    deleted_at TIMESTAMP NULL
);

CREATE TABLE IF NOT EXISTS contest_problems (
    contest_id INTEGER NOT NULL REFERENCES contests(id) ON DELETE CASCADE,
    problem_id INTEGER NOT NULL REFERENCES problems(id) ON DELETE CASCADE,
    label VARCHAR(8) NOT NULL DEFAULT 'A',
    points INTEGER NOT NULL DEFAULT 100,
    order_index INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (contest_id, problem_id)
);

CREATE TABLE IF NOT EXISTS contest_participants (
    contest_id INTEGER NOT NULL REFERENCES contests(id) ON DELETE CASCADE,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    registered_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (contest_id, user_id)
);

CREATE TABLE IF NOT EXISTS contest_allowed_users (
    contest_id INTEGER NOT NULL REFERENCES contests(id) ON DELETE CASCADE,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (contest_id, user_id)
);

CREATE TABLE IF NOT EXISTS contest_classrooms (
    contest_id INTEGER NOT NULL REFERENCES contests(id) ON DELETE CASCADE,
    classroom_id INTEGER NOT NULL REFERENCES classrooms(id) ON DELETE CASCADE,
    added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (contest_id, classroom_id)
);

CREATE TABLE IF NOT EXISTS submissions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    problem_id INTEGER NOT NULL REFERENCES problems(id) ON DELETE CASCADE,
    contest_id INTEGER NULL REFERENCES contests(id) ON DELETE SET NULL,
    language VARCHAR(32) NOT NULL,
    source_storage_key TEXT NOT NULL,
    source_size_bytes INTEGER NOT NULL DEFAULT 0,
    status VARCHAR(24) NOT NULL DEFAULT 'PENDING',
    verdict VARCHAR(16) NOT NULL DEFAULT 'PENDING',
    score INTEGER NOT NULL DEFAULT 0,
    max_score INTEGER NOT NULL DEFAULT 100,
    execution_time_ms INTEGER NOT NULL DEFAULT 0,
    memory_kb INTEGER NOT NULL DEFAULT 0,
    compile_output TEXT NOT NULL DEFAULT '',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    judged_at TIMESTAMP NULL
);

CREATE TABLE IF NOT EXISTS submission_results (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    submission_id INTEGER NOT NULL REFERENCES submissions(id) ON DELETE CASCADE,
    testcase_id INTEGER NOT NULL REFERENCES testcases(id) ON DELETE CASCADE,
    verdict VARCHAR(16) NOT NULL,
    execution_time_ms INTEGER NOT NULL DEFAULT 0,
    memory_kb INTEGER NOT NULL DEFAULT 0,
    score INTEGER NOT NULL DEFAULT 0,
    checker_message TEXT NOT NULL DEFAULT '',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS announcements (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title VARCHAR(200) NOT NULL,
    content_md TEXT NOT NULL,
    classroom_id INTEGER NULL REFERENCES classrooms(id) ON DELETE CASCADE,
    contest_id INTEGER NULL REFERENCES contests(id) ON DELETE CASCADE,
    created_by INTEGER REFERENCES users(id) ON DELETE SET NULL,
    is_pinned BOOLEAN NOT NULL DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS audit_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NULL REFERENCES users(id) ON DELETE SET NULL,
    action VARCHAR(64) NOT NULL,
    entity_type VARCHAR(64) NOT NULL,
    entity_id VARCHAR(64) NOT NULL DEFAULT '',
    ip_address VARCHAR(64) NOT NULL DEFAULT '',
    details_json TEXT NOT NULL DEFAULT '{}',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS system_settings (
    key VARCHAR(64) PRIMARY KEY,
    value TEXT NOT NULL,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_problems_code ON problems(code);
CREATE INDEX IF NOT EXISTS idx_testcases_problem ON testcases(problem_id, order_index);
CREATE INDEX IF NOT EXISTS idx_submissions_user ON submissions(user_id, created_at);
CREATE INDEX IF NOT EXISTS idx_submissions_problem ON submissions(problem_id, created_at);
CREATE INDEX IF NOT EXISTS idx_submission_results_sub ON submission_results(submission_id);

INSERT OR IGNORE INTO roles (name, description) VALUES
    ('admin', 'Toan quyen quan tri he thong'),
    ('teacher', 'Quan ly bai tap, testcase, lop hoc va ky thi'),
    ('student', 'Xem bai tap, nop bai va theo doi tien do');

INSERT OR IGNORE INTO system_settings (key, value) VALUES
    ('site_name', 'Noka JUDGE'),
    ('allow_registration', 'true'),
    ('default_time_limit_ms', '1000'),
    ('default_memory_limit_mb', '256');
"""


class Database:
    """Thread-safe database wrapper translating `%s` placeholders for SQLite seamlessly."""

    def __init__(self, database_url: str) -> None:
        normalized = (database_url or "").strip()
        if normalized.startswith("postgres://"):
            normalized = normalized.replace("postgres://", "postgresql://", 1)
        self.database_url = normalized
        self.is_postgres = normalized.startswith("postgres")
        self._lock = threading.RLock()
        self._pg_pool: Any = None
        self._conn_created_at: Dict[int, float] = {}
        self._conn_last_used_at: Dict[int, float] = {}
        self._pool_recycle_sec = int(os.getenv("DB_POOL_RECYCLE_SECONDS", "240"))
        self._pool_min_conn = max(1, int(os.getenv("DB_POOL_MIN_SIZE", "1")))
        self._pool_max_conn = max(self._pool_min_conn, int(os.getenv("DB_POOL_MAX_SIZE", "8")))
        if not self.is_postgres:
            db_path = normalized.replace("sqlite:///", "", 1)
            if db_path != ":memory:":
                os.makedirs(os.path.dirname(os.path.abspath(db_path)), exist_ok=True)
            self._sqlite_path = db_path
        else:
            self._sqlite_path = ""

    def _get_pg_pool(self) -> Any:
        if self._pg_pool is not None:
            return self._pg_pool
        with self._lock:
            if self._pg_pool is None:
                import psycopg2.pool  # type: ignore

                connect_kwargs: Dict[str, Any] = {
                    "keepalives": 1,
                    "keepalives_idle": 30,
                    "keepalives_interval": 10,
                    "keepalives_count": 3,
                }
                if "connect_timeout=" not in self.database_url:
                    connect_kwargs["connect_timeout"] = 15
                self._pg_pool = psycopg2.pool.ThreadedConnectionPool(
                    self._pool_min_conn,
                    self._pool_max_conn,
                    dsn=self.database_url,
                    **connect_kwargs,
                )
            return self._pg_pool

    def _checkout_pg_conn(self) -> Any:
        pool = self._get_pg_pool()
        now = time.monotonic()
        for _ in range(3):
            conn = pool.getconn()
            cid = id(conn)
            created_at = self._conn_created_at.get(cid)
            if created_at is None:
                self._conn_created_at[cid] = now
                created_at = now
            last_used = self._conn_last_used_at.get(cid, created_at)

            # Recycle closed connections or connections older than pool_recycle (240s for Neon)
            if conn.closed != 0 or (now - created_at) >= self._pool_recycle_sec:
                self._conn_created_at.pop(cid, None)
                self._conn_last_used_at.pop(cid, None)
                try:
                    pool.putconn(conn, close=True)
                except Exception:
                    pass
                continue

            # Pre-ping idle connections (idle > 20s) to gracefully handle Neon scale-to-zero
            if (now - last_used) >= 20.0:
                try:
                    with conn.cursor() as cur:
                        cur.execute("SELECT 1")
                    conn.rollback()
                except Exception:
                    self._conn_created_at.pop(cid, None)
                    self._conn_last_used_at.pop(cid, None)
                    try:
                        pool.putconn(conn, close=True)
                    except Exception:
                        pass
                    continue

            return conn

        # Fallback: obtain a fresh connection directly via pool
        conn = pool.getconn()
        self._conn_created_at[id(conn)] = now
        return conn

    def close_pool(self) -> None:
        with self._lock:
            if self._pg_pool is not None:
                try:
                    self._pg_pool.closeall()
                except Exception:
                    pass
                self._pg_pool = None
                self._conn_created_at.clear()
                self._conn_last_used_at.clear()

    def _adapt_query(self, sql: str) -> str:
        if self.is_postgres:
            return sql
        # Convert PostgreSQL %s placeholders and ILIKE to SQLite equivalents
        adapted = sql.replace("%s", "?")
        adapted = re.sub(r"\bILIKE\b", "LIKE", adapted, flags=re.IGNORECASE)
        return adapted

    @contextmanager
    def connection(self) -> Iterator[Any]:
        if self.is_postgres:
            pool = self._get_pg_pool()
            conn = self._checkout_pg_conn()
            broken = False
            try:
                yield conn
                conn.commit()
                self._conn_last_used_at[id(conn)] = time.monotonic()
            except Exception as exc:
                import psycopg2  # type: ignore

                if isinstance(exc, (psycopg2.OperationalError, psycopg2.InterfaceError)) or conn.closed != 0:
                    broken = True
                else:
                    try:
                        conn.rollback()
                    except Exception:
                        broken = True
                raise
            finally:
                if broken:
                    self._conn_created_at.pop(id(conn), None)
                    self._conn_last_used_at.pop(id(conn), None)
                try:
                    pool.putconn(conn, close=broken)
                except Exception:
                    pass
        else:
            with self._lock:
                conn = sqlite3.connect(self._sqlite_path, check_same_thread=False)
                conn.row_factory = sqlite3.Row
                conn.execute("PRAGMA foreign_keys = ON;")
                try:
                    yield conn
                    conn.commit()
                except Exception:
                    conn.rollback()
                    raise
                finally:
                    conn.close()

    def _run_with_pg_retry(self, fn: Callable[[], T]) -> T:
        if not self.is_postgres:
            return fn()
        import psycopg2  # type: ignore

        try:
            return fn()
        except (psycopg2.OperationalError, psycopg2.InterfaceError):
            return fn()

    def init_schema(self) -> None:
        if self.is_postgres:
            schema_path = os.path.abspath(
                os.path.join(os.path.dirname(__file__), "..", "..", "..", "database", "init", "01_schema.sql")
            )
            if os.path.exists(schema_path):
                with open(schema_path, "r", encoding="utf-8") as f:
                    ddl = f.read()
                with self.connection() as conn:
                    with conn.cursor() as cur:
                        cur.execute(ddl)
        else:
            with self.connection() as conn:
                conn.executescript(SQLITE_SCHEMA_SQL)
                # Lightweight idempotent column migrations for existing SQLite databases
                p_cols = {row[1] for row in conn.execute("PRAGMA table_info(problems)").fetchall()}
                if "checker_language" not in p_cols:
                    conn.execute("ALTER TABLE problems ADD COLUMN checker_language VARCHAR(32) NOT NULL DEFAULT 'python3'")
                if "submission_retention_mode" not in p_cols:
                    conn.execute("ALTER TABLE problems ADD COLUMN submission_retention_mode VARCHAR(16) NOT NULL DEFAULT 'latest'")
                cols = {row[1] for row in conn.execute("PRAGMA table_info(contests)").fetchall()}
                if "is_hidden" not in cols:
                    conn.execute("ALTER TABLE contests ADD COLUMN is_hidden BOOLEAN NOT NULL DEFAULT 0")
                if "block_old_code" not in cols:
                    conn.execute("ALTER TABLE contests ADD COLUMN block_old_code BOOLEAN NOT NULL DEFAULT 1")

    def fetchone(self, sql: str, params: Sequence[Any] = ()) -> Optional[Dict[str, Any]]:
        q = self._adapt_query(sql)

        def _op() -> Optional[Dict[str, Any]]:
            with self.connection() as conn:
                if self.is_postgres:
                    import psycopg2.extras  # type: ignore

                    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                        cur.execute(q, params)
                        row = cur.fetchone()
                        return dict(row) if row is not None else None
                else:
                    cur = conn.execute(q, params)
                    row = cur.fetchone()
                    return dict(row) if row is not None else None

        return self._run_with_pg_retry(_op)

    def fetchall(self, sql: str, params: Sequence[Any] = ()) -> List[Dict[str, Any]]:
        q = self._adapt_query(sql)

        def _op() -> List[Dict[str, Any]]:
            with self.connection() as conn:
                if self.is_postgres:
                    import psycopg2.extras  # type: ignore

                    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                        cur.execute(q, params)
                        return [dict(r) for r in cur.fetchall()]
                else:
                    cur = conn.execute(q, params)
                    return [dict(r) for r in cur.fetchall()]

        return self._run_with_pg_retry(_op)

    def execute(self, sql: str, params: Sequence[Any] = ()) -> int:
        q = self._adapt_query(sql)

        def _op() -> int:
            with self.connection() as conn:
                if self.is_postgres:
                    with conn.cursor() as cur:
                        cur.execute(q, params)
                        return cur.rowcount
                else:
                    cur = conn.execute(q, params)
                    return cur.rowcount

        return self._run_with_pg_retry(_op)

    def insert_returning_id(self, sql: str, params: Sequence[Any] = ()) -> int:
        def _op() -> int:
            with self.connection() as conn:
                if self.is_postgres:
                    q = sql.rstrip().rstrip(";")
                    if "RETURNING" not in q.upper():
                        q += " RETURNING id"
                    with conn.cursor() as cur:
                        cur.execute(q, params)
                        row = cur.fetchone()
                        return int(row[0])
                else:
                    q = self._adapt_query(sql)
                    q = re.sub(r"\s+RETURNING\s+id\s*$", "", q, flags=re.IGNORECASE)
                    cur = conn.execute(q, params)
                    return int(cur.lastrowid)

        return self._run_with_pg_retry(_op)


_db_instance: Optional[Database] = None


def get_db() -> Database:
    global _db_instance
    if _db_instance is None:
        _db_instance = Database(get_settings().database_url)
    return _db_instance


def reset_db_instance(database_url: Optional[str] = None) -> Database:
    global _db_instance
    url = database_url or get_settings().database_url
    _db_instance = Database(url)
    return _db_instance
