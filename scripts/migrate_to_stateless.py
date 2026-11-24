#!/usr/bin/env python3
"""
Noka JUDGE — Stateless Cloud Migration & Verification Utility (Neon PostgreSQL + Cloudflare R2).

Usage:
  # 1. Verify Neon SSL connection, run Alembic migrations, and inspect table stats
  python scripts/migrate_to_stateless.py verify-neon --database-url "postgresql://...?sslmode=require"

  # 2. Verify Cloudflare R2 credentials (put/get/delete smoke test) & sync local storage/ to R2
  python scripts/migrate_to_stateless.py sync-r2 --source-dir ./storage

  # 3. Copy all rows from an existing PostgreSQL (e.g. Railway) to Neon in pure Python (no pg_dump needed)
  python scripts/migrate_to_stateless.py migrate-db --source-url "postgresql://..." --target-url "postgresql://...?sslmode=require"
"""
import argparse
import os
import subprocess
import sys
from pathlib import Path
from typing import List

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

# Tables ordered topologically by foreign key dependencies
TABLE_COPY_ORDER: List[str] = [
    "roles",
    "users",
    "user_roles",
    "tags",
    "problems",
    "problem_tags",
    "problem_allowed_users",
    "testcase_groups",
    "testcases",
    "classrooms",
    "classroom_students",
    "assignments",
    "assignment_problems",
    "contests",
    "contest_problems",
    "contest_participants",
    "contest_allowed_users",
    "contest_classrooms",
    "submissions",
    "submission_results",
    "announcements",
    "audit_logs",
    "system_settings",
]

SERIAL_TABLES: List[str] = [
    "roles",
    "users",
    "tags",
    "problems",
    "testcase_groups",
    "testcases",
    "classrooms",
    "assignments",
    "contests",
    "submissions",
    "submission_results",
    "announcements",
    "audit_logs",
]


def _run_alembic_upgrade(database_url: str) -> None:
    env = os.environ.copy()
    env["DATABASE_URL"] = database_url
    env["PYTHONPATH"] = REPO_ROOT
    res = subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=os.path.join(REPO_ROOT, "backend"),
        env=env,
        capture_output=True,
        text=True,
    )
    if res.stdout.strip():
        print(res.stdout.strip())
    if res.stderr.strip():
        print(res.stderr.strip())
    if res.returncode != 0:
        raise RuntimeError(f"alembic upgrade head failed with exit code {res.returncode}")


def cmd_verify_neon(args: argparse.Namespace) -> None:
    db_url = (args.database_url or os.getenv("DATABASE_URL") or "").strip()
    if not db_url:
        raise SystemExit("Error: provide --database-url or set DATABASE_URL.")

    from backend.app.core.database import Database

    print("[1/3] Testing Neon PostgreSQL SSL connection...")
    db = Database(db_url)
    row = db.fetchone("SELECT current_database() AS db, version() AS ver")
    print(f"      Connected to database '{row['db']}' ({str(row['ver']).splitlines()[0][:80]})")

    if not args.skip_migrate:
        print("[2/3] Running Alembic migrations (alembic upgrade head)...")
        _run_alembic_upgrade(db_url)
    else:
        print("[2/3] Skipping Alembic (--skip-migrate).")

    print("[3/3] Checking core table counts...")
    for tbl in ("roles", "users", "problems", "testcases", "submissions", "contests", "classrooms"):
        cnt = db.fetchone(f"SELECT COUNT(*) AS c FROM {tbl}")
        print(f"      - {tbl}: {cnt['c']} row(s)")
    print("[OK] Neon PostgreSQL is ready for Noka JUDGE!")


def cmd_sync_r2(args: argparse.Namespace) -> None:
    endpoint = (args.endpoint_url or os.getenv("S3_ENDPOINT_URL") or "").strip()
    bucket = (args.bucket_name or os.getenv("S3_BUCKET_NAME") or "").strip()
    access_key = (args.access_key or os.getenv("S3_ACCESS_KEY") or "").strip()
    secret_key = (args.secret_key or os.getenv("S3_SECRET_KEY") or "").strip()
    region = (args.region or os.getenv("S3_REGION") or "auto").strip()

    if not all([endpoint, bucket, access_key, secret_key]):
        raise SystemExit(
            "Error: S3_ENDPOINT_URL, S3_BUCKET_NAME, S3_ACCESS_KEY, S3_SECRET_KEY are required."
        )

    from backend.app.core.storage import S3Storage

    storage = S3Storage(
        endpoint_url=endpoint,
        bucket=bucket,
        access_key=access_key,
        secret_key=secret_key,
        region_name=region,
    )

    print(f"[1/2] Running R2 smoke test on bucket '{bucket}'...")
    probe_key = "_noka_healthcheck/r2_probe.txt"
    payload = b"noka-judge-r2-ok"
    storage.put_bytes(probe_key, payload)
    got = storage.get_bytes(probe_key)
    storage.delete(probe_key)
    if got != payload:
        raise RuntimeError(f"R2 smoke test mismatch: expected {payload!r}, got {got!r}")
    missing = storage.get_bytes("_noka_healthcheck/does_not_exist.txt")
    if missing != b"":
        raise RuntimeError("R2 missing-key fallback did not return empty bytes.")
    print("      Smoke test PASSED (put -> get -> delete -> missing-key check).")

    if args.test_only:
        return

    src_root = Path(args.source_dir).resolve()
    if not src_root.is_dir():
        print(f"[2/2] Source directory '{src_root}' not found; nothing to sync.")
        return

    skip_names = {".gitkeep", ".DS_Store", "Thumbs.db"}
    skip_suffixes = {".db", ".sqlite3", ".db-journal", ".db-wal", ".db-shm"}
    uploaded = 0
    total_bytes = 0

    print(f"[2/2] Syncing files from '{src_root}' to R2 bucket '{bucket}'...")
    for path in sorted(src_root.rglob("*")):
        if not path.is_file():
            continue
        if path.name in skip_names or path.suffix.lower() in skip_suffixes:
            continue
        rel_key = path.relative_to(src_root).as_posix()
        data = path.read_bytes()
        storage.put_bytes(rel_key, data)
        uploaded += 1
        total_bytes += len(data)
        print(f"      uploaded: {rel_key} ({len(data)} bytes)")

    print(f"[OK] Synced {uploaded} file(s) ({total_bytes / 1024:.1f} KB) to Cloudflare R2.")


def cmd_migrate_db(args: argparse.Namespace) -> None:
    src_url = (args.source_url or os.getenv("SOURCE_DATABASE_URL") or "").strip()
    dst_url = (args.target_url or os.getenv("TARGET_DATABASE_URL") or "").strip()
    if not src_url or not dst_url:
        raise SystemExit("Error: provide --source-url and --target-url.")

    import psycopg2  # type: ignore
    import psycopg2.extras  # type: ignore

    print("[1/3] Ensuring target Neon schema is initialized via Alembic...")
    _run_alembic_upgrade(dst_url)

    print("[2/3] Copying tables from source PostgreSQL to target Neon PostgreSQL...")
    src_conn = psycopg2.connect(src_url, connect_timeout=15)
    dst_conn = psycopg2.connect(dst_url, connect_timeout=15)
    try:
        with src_conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as sc, dst_conn.cursor() as dc:
            for table in TABLE_COPY_ORDER:
                sc.execute(f'SELECT * FROM "{table}"')
                rows = sc.fetchall()
                if not rows:
                    print(f"      - {table}: 0 rows (skipped)")
                    continue
                cols = list(rows[0].keys())
                col_list = ", ".join(f'"{c}"' for c in cols)
                placeholders = ", ".join(["%s"] * len(cols))
                insert_sql = f'INSERT INTO "{table}" ({col_list}) VALUES ({placeholders}) ON CONFLICT DO NOTHING'
                values = [tuple(r[c] for c in cols) for r in rows]
                psycopg2.extras.execute_batch(dc, insert_sql, values, page_size=200)
                print(f"      - {table}: copied {len(rows)} row(s)")

            print("[3/3] Resetting PostgreSQL SERIAL sequences...")
            for table in SERIAL_TABLES:
                dc.execute(
                    f"""
                    SELECT setval(
                        pg_get_serial_sequence('{table}', 'id'),
                        COALESCE((SELECT MAX(id) FROM "{table}"), 1),
                        (SELECT COUNT(*) > 0 FROM "{table}")
                    )
                    """
                )
        dst_conn.commit()
    except Exception:
        dst_conn.rollback()
        raise
    finally:
        src_conn.close()
        dst_conn.close()

    print("[OK] Database migration completed cleanly!")


def main() -> None:
    parser = argparse.ArgumentParser(description="Noka JUDGE Stateless Migration Tool")
    sub = parser.add_subparsers(dest="command", required=True)

    p_neon = sub.add_parser("verify-neon", help="Verify Neon SSL connection & run Alembic migrations")
    p_neon.add_argument("--database-url", default="", help="Neon PostgreSQL URL (or set DATABASE_URL)")
    p_neon.add_argument("--skip-migrate", action="store_true", help="Skip running alembic upgrade head")
    p_neon.set_defaults(func=cmd_verify_neon)

    p_r2 = sub.add_parser("sync-r2", help="Test Cloudflare R2 and sync local storage files")
    p_r2.add_argument("--source-dir", default=os.path.join(REPO_ROOT, "storage"), help="Local storage folder")
    p_r2.add_argument("--endpoint-url", default="")
    p_r2.add_argument("--bucket-name", default="")
    p_r2.add_argument("--access-key", default="")
    p_r2.add_argument("--secret-key", default="")
    p_r2.add_argument("--region", default="auto")
    p_r2.add_argument("--test-only", action="store_true", help="Only run put/get/delete smoke test")
    p_r2.set_defaults(func=cmd_sync_r2)

    p_mig = sub.add_parser("migrate-db", help="Copy all rows from source PostgreSQL to Neon PostgreSQL")
    p_mig.add_argument("--source-url", default="", help="Source PostgreSQL URL (e.g. Railway)")
    p_mig.add_argument("--target-url", default="", help="Target Neon PostgreSQL URL")
    p_mig.set_defaults(func=cmd_migrate_db)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
