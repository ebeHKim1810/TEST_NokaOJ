#!/usr/bin/env python3
"""
Secure first Administrator creation utility for Noka JUDGE.
Never hardcodes any default production password; prompts interactively or reads
NOKA_ADMIN_USERNAME / NOKA_ADMIN_EMAIL / NOKA_ADMIN_PASSWORD from environment.
"""
import getpass
import os
import sys

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

from backend.app.core.database import get_db
from backend.app.core.security import hash_password


def main() -> None:
    db = get_db()
    db.init_schema()

    username = os.getenv("NOKA_ADMIN_USERNAME") or input("Admin username [admin]: ").strip() or "admin"
    email = os.getenv("NOKA_ADMIN_EMAIL") or input("Admin email: ").strip()
    if not email:
        print("Error: email is required.")
        sys.exit(1)

    password = os.getenv("NOKA_ADMIN_PASSWORD")
    if not password:
        password = getpass.getpass("Admin password (min 8 chars): ")
        confirm = getpass.getpass("Confirm password: ")
        if password != confirm:
            print("Error: passwords do not match.")
            sys.exit(1)
    if len(password) < 8:
        print("Error: password must be at least 8 characters.")
        sys.exit(1)

    existing = db.fetchone("SELECT id FROM users WHERE username = %s OR email = %s", (username, email))
    if existing:
        print(f"Account '{username}' / '{email}' already exists (id={existing['id']}).")
        sys.exit(0)

    uid = db.insert_returning_id(
        """
        INSERT INTO users (username, email, full_name, password_hash, is_active)
        VALUES (%s, %s, %s, %s, %s)
        """,
        (username, email, "System Administrator", hash_password(password), True),
    )
    role = db.fetchone("SELECT id FROM roles WHERE name = 'admin'")
    if role:
        db.execute("INSERT INTO user_roles (user_id, role_id) VALUES (%s, %s)", (uid, role["id"]))
    print(f"Administrator account '{username}' created successfully (id={uid}).")


if __name__ == "__main__":
    main()
