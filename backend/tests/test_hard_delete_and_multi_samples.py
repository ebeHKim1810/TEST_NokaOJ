"""Integration tests for Hard Delete of problems (DB + R2 + orphan images) and Multi-Samples with per-example explanations."""
import json
import os
import tempfile
import unittest
from dataclasses import dataclass, field
from typing import List
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi.testclient import TestClient

VALID_PNG = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
    b"\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\rIDATx\x9cc`\x00\x00"
    b"\x00\x02\x00\x01H\xaf\xa4q\x00\x00\x00\x00IEND\xaeB`\x82"
)


@dataclass
class _FakeTestResult:
    testcase_id: int
    verdict: str
    execution_time_ms: int
    memory_kb: int
    score: int
    checker_message: str


@dataclass
class _FakeJudgeOutcome:
    verdict: str
    score: int
    max_score: int
    execution_time_ms: int = 8
    memory_kb: int = 512
    compile_output: str = ""
    results: List[_FakeTestResult] = field(default_factory=list)


class TestHardDeleteAndMultiSamples(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self._db_path = os.path.join(self._tmp.name, "test_hd_samples.db")
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
                "SECRET_KEY": "test-secret-hd-samples",
                "GEMINI_API_KEY": "fake-gemini-key",
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

        self.client = TestClient(create_app())
        self.admin_token, self.admin_id = self._create_user("admin_hd", "ahd@test.local", ["admin"])
        self.t1_token, self.t1_id = self._create_user("teacher1", "t1@test.local", ["teacher"])
        self.t2_token, self.t2_id = self._create_user("teacher2", "t2@test.local", ["teacher"])
        self.stu_token, self.stu_id = self._create_user("student_hd", "shd@test.local", ["student"])

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

    def _create_user(self, username: str, email: str, roles: List[str]):
        from backend.app.core.security import create_access_token, hash_password

        uid = self.db.insert_returning_id(
            "INSERT INTO users (username, email, full_name, password_hash, is_active) VALUES (%s, %s, %s, %s, %s)",
            (username, email, username, hash_password("Secret123!"), True),
        )
        for rname in roles:
            role = self.db.fetchone("SELECT id FROM roles WHERE name = %s", (rname,))
            self.db.execute("INSERT INTO user_roles (user_id, role_id) VALUES (%s, %s)", (uid, int(role["id"])))
        return create_access_token({"sub": str(uid), "username": username, "roles": roles}), uid

    def _headers(self, token: str):
        return {"Authorization": f"Bearer {token}"}

    def _storage_exists(self, key: str) -> bool:
        return os.path.exists(self.storage._safe_path(key))

    def test_multi_samples_crud_backward_compat_and_auto_import(self) -> None:
        # 1. Create problem with 2 samples having distinct explanations
        r = self.client.post(
            "/api/v1/problems",
            headers=self._headers(self.admin_token),
            json={
                "code": "MS01",
                "title": "Multi Examples",
                "statement_md": "Sum of two numbers.",
                "samples": [
                    {"input": "1 2", "output": "3", "explanation": "Ta có $1 + 2 = 3$."},
                    {"input": "10 20", "output": "30", "explanation": "Ta có $10 + 20 = 30$."},
                ],
            },
        )
        self.assertEqual(r.status_code, 201, r.text)
        pid = r.json()["id"]
        self.assertEqual(len(r.json()["samples"]), 2)
        self.assertEqual(r.json()["sample_input"], "1 2")
        self.assertEqual(r.json()["sample_output"], "3")

        # GET returns both examples intact
        g = self.client.get("/api/v1/problems/MS01", headers=self._headers(self.stu_token))
        self.assertEqual(g.status_code, 200)
        self.assertEqual(len(g.json()["samples"]), 2)
        self.assertEqual(g.json()["samples"][1]["explanation"], "Ta có $10 + 20 = 30$.")

        # PUT updates samples to 3 items
        u = self.client.put(
            f"/api/v1/problems/{pid}",
            headers=self._headers(self.admin_token),
            json={
                "samples": [
                    {"input": "5 5", "output": "10", "explanation": "Ex 1"},
                    {"input": "0 0", "output": "0", "explanation": ""},
                    {"input": "-1 1", "output": "0", "explanation": "Ex 3"},
                ]
            },
        )
        self.assertEqual(u.status_code, 200)
        self.assertEqual(len(u.json()["samples"]), 3)
        self.assertEqual(u.json()["sample_input"], "5 5")

        # 2. Backward compatibility: legacy row with samples='[]' but sample_input/sample_output populated
        legacy_id = self.db.insert_returning_id(
            """
            INSERT INTO problems (code, title, statement_md, sample_input, sample_output, explanation, samples, visibility)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            """,
            ("LEG01", "Legacy Prob", "Desc", "7 8", "15", "Legacy explain", "[]", "public"),
        )
        gl = self.client.get(f"/api/v1/problems/{legacy_id}", headers=self._headers(self.stu_token))
        self.assertEqual(gl.status_code, 200)
        self.assertEqual(
            gl.json()["samples"],
            [{"input": "7 8", "output": "15", "explanation": "Legacy explain"}],
        )

        # 3. Auto-Import extracts multi-sample array
        ai_payload = {
            "title": "AI Multi",
            "description": "Đề bài",
            "input_description": "Input",
            "output_description": "Output",
            "constraints": "$N \\le 10^5$",
            "samples": [
                {"input": "2\n1 2", "output": "3", "explanation": "Ví dụ 1: $1+2=3$"},
                {"input": "3\n4 5 6", "output": "15", "explanation": "Ví dụ 2: $4+5+6=15$"},
            ],
            "sample_input": "2\n1 2",
            "sample_output": "3",
            "explanation": "Ví dụ 1: $1+2=3$",
            "time_limit_ms": 1000,
            "memory_limit_mb": 256,
        }
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "candidates": [{"content": {"parts": [{"text": json.dumps(ai_payload, ensure_ascii=False)}]}}]
        }
        with patch("httpx.AsyncClient.post", new=AsyncMock(return_value=mock_resp)):
            r_ai = self.client.post(
                "/api/v1/problems/auto-import",
                headers=self._headers(self.admin_token),
                files={"file": ("multi.png", VALID_PNG, "image/png")},
            )
        self.assertEqual(r_ai.status_code, 200, r_ai.text)
        self.assertEqual(len(r_ai.json()["samples"]), 2)
        self.assertEqual(r_ai.json()["samples"][1]["output"], "15")

    def test_hard_delete_problem_rbac_db_and_r2_including_orphan_images(self) -> None:
        # Upload 2 images: img_orphan (used only in P1) and img_shared (used in BOTH P1 and P2)
        up1 = self.client.post(
            "/api/v1/problems/upload-image",
            headers=self._headers(self.t1_token),
            files={"file": ("orphan.png", VALID_PNG, "image/png")},
        ).json()
        up2 = self.client.post(
            "/api/v1/problems/upload-image",
            headers=self._headers(self.t1_token),
            files={"file": ("shared.png", VALID_PNG, "image/png")},
        ).json()

        # Teacher 1 creates P1 (custom checker + orphan image in statement + shared image in sample explanation)
        p1 = self.client.post(
            "/api/v1/problems",
            headers=self._headers(self.t1_token),
            json={
                "code": "HDEL01",
                "title": "To Be Hard Deleted",
                "statement_md": f"Statement ![img1]({up1['url']})",
                "samples": [
                    {
                        "input": "1 2",
                        "output": "3",
                        "explanation": f"Shared diagram ![img2]({up2['url']})",
                    }
                ],
                "visibility": "private",
                "allowed_user_ids": [self.stu_id],
                "checker_type": "custom",
                "checker_language": "python3",
                "checker_source": "print('OK')\n",
                "tags": ["math"],
            },
        ).json()
        p1_id = p1["id"]

        # Teacher 1 creates P2 also referencing img_shared
        p2 = self.client.post(
            "/api/v1/problems",
            headers=self._headers(self.t1_token),
            json={
                "code": "KEEP02",
                "title": "Kept Problem",
                "statement_md": f"Also uses ![img2]({up2['url']})",
            },
        ).json()

        # Add testcase + submission to P1
        tc = self.client.post(
            f"/api/v1/testcases/problem/{p1_id}",
            headers=self._headers(self.t1_token),
            json={"name": "01", "input_data": "1 2\n", "expected_output": "3\n", "is_hidden": True},
        ).json()

        outcome = _FakeJudgeOutcome(
            verdict="AC",
            score=100,
            max_score=100,
            results=[_FakeTestResult(tc["id"], "AC", 5, 256, 100, "OK")],
        )
        with patch("judge.worker.worker.JudgeEngine.judge_submission", return_value=outcome):
            sub = self.client.post(
                "/api/v1/submissions",
                headers=self._headers(self.stu_token),
                json={"problem_id": p1_id, "language": "python3", "source_code": "print(3)"},
            ).json()

        tc_row = self.db.fetchone("SELECT * FROM testcases WHERE id = %s", (tc["id"],))
        sub_row = self.db.fetchone("SELECT * FROM submissions WHERE id = %s", (sub["id"],))
        p1_row = self.db.fetchone("SELECT * FROM problems WHERE id = %s", (p1_id,))

        # Confirm all files exist in storage before delete
        self.assertTrue(self._storage_exists(tc_row["input_storage_key"]))
        self.assertTrue(self._storage_exists(tc_row["output_storage_key"]))
        self.assertTrue(self._storage_exists(sub_row["source_storage_key"]))
        self.assertTrue(self._storage_exists(p1_row["checker_storage_key"]))
        self.assertTrue(self._storage_exists(up1["storage_key"]))
        self.assertTrue(self._storage_exists(up2["storage_key"]))

        # RBAC: Student -> 403; Teacher 2 (non-owner) -> 403
        self.assertEqual(
            self.client.delete(f"/api/v1/problems/{p1_id}", headers=self._headers(self.stu_token)).status_code,
            403,
        )
        self.assertEqual(
            self.client.delete(f"/api/v1/problems/{p1_id}", headers=self._headers(self.t2_token)).status_code,
            403,
        )

        # Owner Teacher 1 hard-deletes P1 -> 200
        del_resp = self.client.delete(f"/api/v1/problems/{p1_id}", headers=self._headers(self.t1_token))
        self.assertEqual(del_resp.status_code, 200, del_resp.text)
        del_data = del_resp.json()
        self.assertTrue(del_data["deleted"])
        self.assertEqual(del_data["deleted_testcases"], 1)
        self.assertEqual(del_data["deleted_submissions"], 1)
        self.assertEqual(del_data["deleted_storage_files"], 5)  # 2 tc + 1 sub + 1 checker + 1 orphan image

        # Verify ALL P1 files deleted from storage, while shared image is PRESERVED!
        self.assertFalse(self._storage_exists(tc_row["input_storage_key"]))
        self.assertFalse(self._storage_exists(tc_row["output_storage_key"]))
        self.assertFalse(self._storage_exists(sub_row["source_storage_key"]))
        self.assertFalse(self._storage_exists(p1_row["checker_storage_key"]))
        self.assertFalse(self._storage_exists(up1["storage_key"]))
        self.assertTrue(self._storage_exists(up2["storage_key"]))

        # Verify HARD DELETE in DB (completely gone, NOT soft-deleted)
        self.assertIsNone(self.db.fetchone("SELECT * FROM problems WHERE id = %s", (p1_id,)))
        self.assertEqual(self.db.fetchall("SELECT * FROM testcases WHERE problem_id = %s", (p1_id,)), [])
        self.assertEqual(self.db.fetchall("SELECT * FROM submissions WHERE problem_id = %s", (p1_id,)), [])
        self.assertEqual(self.db.fetchall("SELECT * FROM submission_results WHERE submission_id = %s", (sub["id"],)), [])
        self.assertEqual(self.db.fetchall("SELECT * FROM problem_allowed_users WHERE problem_id = %s", (p1_id,)), [])
        # P2 still intact
        self.assertIsNotNone(self.db.fetchone("SELECT * FROM problems WHERE id = %s", (p2["id"],)))


if __name__ == "__main__":
    unittest.main()
