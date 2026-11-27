"""Tests for Admin User Management API (list/search, edit full_name/username, reset password, RBAC, self-protection)."""
import json
import os
import tempfile
import unittest

from fastapi import APIRouter, FastAPI, HTTPException
from fastapi.security import HTTPAuthorizationCredentials
from starlette.requests import Request


def _fake_request(ip: str = "127.0.0.1") -> Request:
    scope = {
        "type": "http",
        "http_version": "1.1",
        "method": "PATCH",
        "scheme": "http",
        "path": "/api/v1/users",
        "query_string": b"",
        "headers": [],
        "client": (ip, 12345),
        "server": ("testserver", 80),
    }
    return Request(scope)


class TestAdminUserManagement(unittest.TestCase):
    def setUp(self) -> None:
        self.tmpdir = tempfile.TemporaryDirectory(prefix="noka_users_")
        os.environ["APP_ENV"] = "test"
        os.environ["JUDGE_DISPATCH_MODE"] = "inline"
        os.environ["JUDGE_MODE"] = "local_posix"
        os.environ["DATABASE_URL"] = f"sqlite:///{os.path.join(self.tmpdir.name, 'test.db')}"
        os.environ["STORAGE_LOCAL_PATH"] = os.path.join(self.tmpdir.name, "storage")
        os.environ["SECRET_KEY"] = "test-secret-key-for-admin-user-mgmt"

        from backend.app.core.cache import app_cache
        from backend.app.core.config import get_settings
        from backend.app.core.database import reset_db_instance
        from backend.app.core.storage import reset_storage_instance

        get_settings.cache_clear()
        app_cache.clear()
        self.db = reset_db_instance(os.environ["DATABASE_URL"])
        self.db.init_schema()
        reset_storage_instance(os.environ["STORAGE_LOCAL_PATH"])

        self.admin_id = self._seed_user("admin01", "admin01@noka.local", "Super Admin", "AdminPass123!", "admin")
        self.teacher_id = self._seed_user("teacher01", "teacher01@noka.local", "Teacher One", "TeacherPass123!", "teacher")
        self.student1_id = self._seed_user("student01", "student01@noka.local", "Nguyen Van A", "StudentPass1!", "student")
        self.student2_id = self._seed_user("student02", "student02@noka.local", "Tran Thi B", "StudentPass2!", "student")

    def _seed_user(self, username: str, email: str, full_name: str, password: str, role_name: str) -> int:
        from backend.app.core.security import get_password_hash

        uid = self.db.insert_returning_id(
            "INSERT INTO users (username, email, full_name, password_hash, is_active) VALUES (%s, %s, %s, %s, %s)",
            (username, email, full_name, get_password_hash(password), True),
        )
        role = self.db.fetchone("SELECT id FROM roles WHERE name = %s", (role_name,))
        self.db.execute("INSERT INTO user_roles (user_id, role_id) VALUES (%s, %s)", (uid, role["id"]))
        return uid

    def tearDown(self) -> None:
        self.tmpdir.cleanup()

    def _login(self, username: str, password: str) -> tuple[str, dict]:
        from backend.app.api.v1 import auth
        from backend.app.core.security import get_current_user
        from backend.app.schemas.schemas import LoginRequest

        res = auth.login(LoginRequest(username=username, password=password), _fake_request(), self.db)
        token = res["access_token"]
        user = get_current_user(HTTPAuthorizationCredentials(scheme="Bearer", credentials=token), self.db)
        return token, user

    def test_routes_registered_with_expected_methods(self) -> None:
        from backend.app.api.v1 import admin, auth, users

        app = FastAPI()
        api = APIRouter(prefix="/api/v1")
        api.include_router(auth.router)
        api.include_router(users.router)
        api.include_router(admin.router)
        app.include_router(api)

        paths = app.openapi()["paths"]
        self.assertIn("get", paths.get("/api/v1/users", {}))
        self.assertIn("patch", paths.get("/api/v1/users/{user_id}", {}))
        self.assertIn("get", paths.get("/api/v1/admin/users", {}))
        self.assertIn("patch", paths.get("/api/v1/admin/users/{user_id}", {}))
        self.assertIn("put", paths.get("/api/v1/admin/users/{user_id}", {}))

    def test_rbac_enforcement(self) -> None:
        from backend.app.core.security import get_current_user, require_roles

        _, student_u = self._login("student01", "StudentPass1!")
        _, teacher_u = self._login("teacher01", "TeacherPass123!")
        _, admin_u = self._login("admin01", "AdminPass123!")

        # Unauthenticated rejected with 401
        with self.assertRaises(HTTPException) as ctx:
            get_current_user(None, self.db)
        self.assertEqual(ctx.exception.status_code, 401)

        # Admin-only guard rejects both student and teacher with 403
        admin_only = require_roles("admin")
        for non_admin in (student_u, teacher_u):
            with self.assertRaises(HTTPException) as ctx:
                admin_only(non_admin)
            self.assertEqual(ctx.exception.status_code, 403)
        self.assertEqual(admin_only(admin_u)["id"], self.admin_id)

        # Staff guard allows teacher & admin, rejects student
        staff_only = require_roles("admin", "teacher")
        with self.assertRaises(HTTPException) as ctx:
            staff_only(student_u)
        self.assertEqual(ctx.exception.status_code, 403)
        self.assertEqual(staff_only(teacher_u)["id"], self.teacher_id)

    def test_list_and_search_users(self) -> None:
        from backend.app.api.v1 import admin, users

        _, admin_u = self._login("admin01", "AdminPass123!")

        data = admin.admin_list_users(search="", role="", limit=500, current_user=admin_u, db=self.db)
        self.assertEqual(data["total"], 4)
        sample = data["items"][0]
        for field in ("id", "username", "full_name", "email", "roles", "role", "is_active", "created_at"):
            self.assertIn(field, sample)
        self.assertIsInstance(sample["is_active"], bool)

        # Filter by role with tight limit (verifies SQL role filter runs before LIMIT)
        by_role = admin.admin_list_users(search="", role="admin", limit=1, current_user=admin_u, db=self.db)
        self.assertEqual(by_role["total"], 1)
        self.assertEqual(by_role["items"][0]["username"], "admin01")

        # Search by full_name
        by_name = users.list_users(search="Tran", role="", limit=500, current_user=admin_u, db=self.db)
        self.assertEqual(by_name["total"], 1)
        self.assertEqual(by_name["items"][0]["username"], "student02")

        # Search by username
        by_uname = admin.admin_list_users(search="student01", role="", limit=500, current_user=admin_u, db=self.db)
        self.assertEqual(by_uname["total"], 1)
        self.assertEqual(by_uname["items"][0]["full_name"], "Nguyen Van A")

    def test_update_full_name_username_and_password_reset(self) -> None:
        from backend.app.api.v1 import admin, auth, users
        from backend.app.schemas.schemas import LoginRequest, UserUpdateRequest

        _, admin_u = self._login("admin01", "AdminPass123!")

        # 1. Duplicate username returns 400 with exact Vietnamese message
        with self.assertRaises(HTTPException) as ctx:
            users.update_user(
                self.student1_id,
                UserUpdateRequest(username="STUDENT02"),
                _fake_request(),
                admin_u,
                self.db,
            )
        self.assertEqual(ctx.exception.status_code, 400)
        self.assertIn("Tên đăng nhập này đã tồn tại", str(ctx.exception.detail))

        # 2. Invalid username (too short or containing whitespace) -> 400
        for bad_u in ("ab", "bad user"):
            with self.assertRaises(HTTPException) as ctx:
                users.update_user(
                    self.student1_id,
                    UserUpdateRequest(username=bad_u),
                    _fake_request(),
                    admin_u,
                    self.db,
                )
            self.assertEqual(ctx.exception.status_code, 400)

        # 3. Password too short -> 400
        with self.assertRaises(HTTPException) as ctx:
            users.update_user(
                self.student1_id,
                UserUpdateRequest(new_password="12345"),
                _fake_request(),
                admin_u,
                self.db,
            )
        self.assertEqual(ctx.exception.status_code, 400)

        # 4. Update full_name & username with blank new_password -> preserves existing password
        updated = users.update_user(
            self.student1_id,
            UserUpdateRequest(
                full_name="Nguyen Van A Updated",
                username="student01_new",
                new_password="",
            ),
            _fake_request(),
            admin_u,
            self.db,
        )
        self.assertEqual(updated["username"], "student01_new")
        self.assertEqual(updated["full_name"], "Nguyen Van A Updated")

        # Old username fails; new username succeeds with original password
        with self.assertRaises(HTTPException) as ctx:
            auth.login(LoginRequest(username="student01", password="StudentPass1!"), _fake_request(), self.db)
        self.assertEqual(ctx.exception.status_code, 401)
        self._login("student01_new", "StudentPass1!")

        # 5. Reset password via admin_update_user
        admin.admin_update_user(
            self.student1_id,
            UserUpdateRequest(new_password="ResetPass2026!"),
            _fake_request(),
            admin_u,
            self.db,
        )

        # Old password rejected, new password accepted
        with self.assertRaises(HTTPException) as ctx:
            auth.login(LoginRequest(username="student01_new", password="StudentPass1!"), _fake_request(), self.db)
        self.assertEqual(ctx.exception.status_code, 401)
        self._login("student01_new", "ResetPass2026!")

        # Audit log must never store plaintext password
        audit_rows = self.db.fetchall("SELECT details_json FROM audit_logs WHERE action = 'user.update' ORDER BY id DESC")
        self.assertTrue(len(audit_rows) >= 1)
        latest_details = json.loads(audit_rows[0]["details_json"])
        self.assertTrue(latest_details.get("password_reset"))
        self.assertNotIn("ResetPass2026!", audit_rows[0]["details_json"])

    def test_role_change_lock_and_self_protection(self) -> None:
        from backend.app.api.v1 import auth, users
        from backend.app.core.security import get_current_user
        from backend.app.schemas.schemas import LoginRequest, UserUpdateRequest

        admin_token, admin_u = self._login("admin01", "AdminPass123!")

        # Admin cannot self-lock
        with self.assertRaises(HTTPException) as ctx:
            users.update_user(
                self.admin_id,
                UserUpdateRequest(is_active=False),
                _fake_request(),
                admin_u,
                self.db,
            )
        self.assertEqual(ctx.exception.status_code, 400)

        # Admin cannot self-demote via `role` or `roles`
        for payload in (UserUpdateRequest(role="student"), UserUpdateRequest(roles=["teacher"])):
            with self.assertRaises(HTTPException) as ctx:
                users.update_user(self.admin_id, payload, _fake_request(), admin_u, self.db)
            self.assertEqual(ctx.exception.status_code, 400)

        # Admin CAN update own display name & username
        self_upd = users.update_user(
            self.admin_id,
            UserUpdateRequest(full_name="Main Administrator", username="admin_main"),
            _fake_request(),
            admin_u,
            self.db,
        )
        self.assertEqual(self_upd["username"], "admin_main")
        self.assertEqual(self_upd["full_name"], "Main Administrator")

        # Existing token immediately reflects updated username/full_name via cache invalidation
        refreshed = get_current_user(HTTPAuthorizationCredentials(scheme="Bearer", credentials=admin_token), self.db)
        self.assertEqual(refreshed["username"], "admin_main")
        self.assertEqual(refreshed["full_name"], "Main Administrator")

        # Admin can change another user's role and lock them
        promoted = users.update_user(
            self.student2_id,
            UserUpdateRequest(role="teacher", is_active=False),
            _fake_request(),
            admin_u,
            self.db,
        )
        self.assertEqual(promoted["role"], "teacher")
        self.assertEqual(promoted["roles"], ["teacher"])
        self.assertIs(promoted["is_active"], False)

        # Locked user cannot log in (403)
        with self.assertRaises(HTTPException) as ctx:
            auth.login(LoginRequest(username="student02", password="StudentPass2!"), _fake_request(), self.db)
        self.assertEqual(ctx.exception.status_code, 403)


if __name__ == "__main__":
    unittest.main()
