"""Integration tests for Problem explanation CRUD and R2/storage problem image upload & cached serving."""
import os
import tempfile
import unittest
from typing import List
from unittest.mock import patch

from fastapi.testclient import TestClient

# Minimal valid 1x1 transparent PNG
VALID_PNG = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
    b"\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\rIDATx\x9cc`\x00\x00"
    b"\x00\x02\x00\x01H\xaf\xa4q\x00\x00\x00\x00IEND\xaeB`\x82"
)


class TestProblemExplanationAndImages(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self._db_path = os.path.join(self._tmp.name, "test_noka_exp.db")
        self._storage_path = os.path.join(self._tmp.name, "storage")
        os.makedirs(self._storage_path, exist_ok=True)

        self._env_patch = patch.dict(
            os.environ,
            {
                "DATABASE_URL": f"sqlite:///{self._db_path}",
                "STORAGE_BACKEND": "local",
                "STORAGE_LOCAL_PATH": self._storage_path,
                "JUDGE_DISPATCH_MODE": "inline",
                "APP_ENV": "test",
                "SECRET_KEY": "test-secret-key-explanation-images",
            },
        )
        self._env_patch.start()

        from backend.app.core import database, storage
        from backend.app.core.cache import app_cache
        from backend.app.core.config import get_settings
        from backend.app.main import create_app

        app_cache.clear()
        get_settings.cache_clear()
        database._db_instance = None
        storage._storage_instance = None

        self.db = database.get_db()
        self.db.init_schema()
        self.storage = storage.get_storage()

        for rname in ("admin", "teacher", "student"):
            self.db.execute("INSERT OR IGNORE INTO roles (name) VALUES (%s)", (rname,))

        self.app = create_app()
        self.client = TestClient(self.app)

        self.admin_token = self._create_user("admin_img", "admin_img@test.local", ["admin"])
        self.student_token = self._create_user("student_img", "stu_img@test.local", ["student"])

    def tearDown(self) -> None:
        from backend.app.core import database, storage
        from backend.app.core.cache import app_cache
        from backend.app.core.config import get_settings

        app_cache.clear()
        get_settings.cache_clear()
        database._db_instance = None
        storage._storage_instance = None
        self._env_patch.stop()
        self._tmp.cleanup()

    def _create_user(self, username: str, email: str, roles: List[str]) -> str:
        from backend.app.core.security import create_access_token, hash_password

        uid = self.db.insert_returning_id(
            "INSERT INTO users (username, email, full_name, password_hash, is_active) VALUES (%s, %s, %s, %s, %s)",
            (username, email, username, hash_password("Secret123!"), True),
        )
        for rname in roles:
            role = self.db.fetchone("SELECT id FROM roles WHERE name = %s", (rname,))
            self.db.execute("INSERT INTO user_roles (user_id, role_id) VALUES (%s, %s)", (uid, int(role["id"])))
        return create_access_token({"sub": str(uid), "username": username, "roles": roles})

    def _headers(self, token: str):
        return {"Authorization": f"Bearer {token}"}

    def test_explanation_create_read_update_and_clear(self) -> None:
        # Create with explanation
        r = self.client.post(
            "/api/v1/problems",
            headers=self._headers(self.admin_token),
            json={
                "code": "EXP01",
                "title": "Test Explanation",
                "statement_md": "Find $\\frac{a}{b}$.",
                "sample_input": "6 2",
                "sample_output": "3",
                "explanation": "Ta có $\\frac{6}{2} = 3$.",
                "visibility": "public",
            },
        )
        self.assertEqual(r.status_code, 201, r.text)
        pid = r.json()["id"]
        self.assertEqual(r.json()["explanation"], "Ta có $\\frac{6}{2} = 3$.")

        # Student reads problem and sees explanation
        g = self.client.get("/api/v1/problems/EXP01", headers=self._headers(self.student_token))
        self.assertEqual(g.status_code, 200)
        self.assertEqual(g.json()["explanation"], "Ta có $\\frac{6}{2} = 3$.")

        # Admin updates explanation
        u = self.client.put(
            f"/api/v1/problems/{pid}",
            headers=self._headers(self.admin_token),
            json={"explanation": "Cập nhật: $\\sqrt{9} = 3$."},
        )
        self.assertEqual(u.status_code, 200)
        self.assertEqual(u.json()["explanation"], "Cập nhật: $\\sqrt{9} = 3$.")

        # Admin clears explanation to empty string -> stored as NULL
        u_clear = self.client.put(
            f"/api/v1/problems/{pid}",
            headers=self._headers(self.admin_token),
            json={"explanation": "   "},
        )
        self.assertEqual(u_clear.status_code, 200)
        self.assertIsNone(u_clear.json()["explanation"])

    def test_upload_and_serve_problem_image_with_validation(self) -> None:
        # Student forbidden from uploading
        r_stu = self.client.post(
            "/api/v1/problems/upload-image",
            headers=self._headers(self.student_token),
            files={"file": ("diagram.png", VALID_PNG, "image/png")},
        )
        self.assertEqual(r_stu.status_code, 403)

        # Unsupported MIME rejected
        r_bad_mime = self.client.post(
            "/api/v1/problems/upload-image",
            headers=self._headers(self.admin_token),
            files={"file": ("script.svg", b"<svg></svg>", "image/svg+xml")},
        )
        self.assertEqual(r_bad_mime.status_code, 400)

        # Fake PNG magic bytes rejected
        r_fake = self.client.post(
            "/api/v1/problems/upload-image",
            headers=self._headers(self.admin_token),
            files={"file": ("fake.png", b"not-a-real-png", "image/png")},
        )
        self.assertEqual(r_fake.status_code, 400)

        # Oversized (> 5MB) rejected with 413
        oversized = VALID_PNG + b"\x00" * (5 * 1024 * 1024 + 10)
        r_big = self.client.post(
            "/api/v1/problems/upload-image",
            headers=self._headers(self.admin_token),
            files={"file": ("huge.png", oversized, "image/png")},
        )
        self.assertEqual(r_big.status_code, 413)

        # Valid PNG upload succeeds and stores under problem-images/
        r_ok = self.client.post(
            "/api/v1/problems/upload-image",
            headers=self._headers(self.admin_token),
            files={"file": ("graph.png", VALID_PNG, "image/png")},
        )
        self.assertEqual(r_ok.status_code, 201, r_ok.text)
        body = r_ok.json()
        self.assertTrue(body["storage_key"].startswith("problem-images/"))
        self.assertTrue(body["filename"].endswith(".png"))
        self.assertIn("/api/v1/problems/images/", body["url"])

        # Public GET serves exact bytes with immutable 1-year cache & cross-origin header
        r_get = self.client.get(f"/api/v1/problems/images/{body['filename']}")
        self.assertEqual(r_get.status_code, 200)
        self.assertEqual(r_get.content, VALID_PNG)
        self.assertEqual(r_get.headers["content-type"], "image/png")
        self.assertIn("max-age=31536000", r_get.headers["cache-control"])
        self.assertEqual(r_get.headers["cross-origin-resource-policy"], "cross-origin")

        # Invalid filename rejected
        self.assertEqual(self.client.get("/api/v1/problems/images/not_valid.txt").status_code, 400)
        # Missing valid-pattern filename returns 404
        self.assertEqual(
            self.client.get("/api/v1/problems/images/0123456789abcdef0123456789abcdef.png").status_code,
            404,
        )


if __name__ == "__main__":
    unittest.main()
