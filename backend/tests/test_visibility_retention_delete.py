"""Integration tests for problem visibility/access control, submission retention (latest/best), and permanent deletion."""
import os
import tempfile
import unittest
from dataclasses import dataclass, field
from typing import List
from unittest.mock import patch

from fastapi.testclient import TestClient


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
    execution_time_ms: int = 12
    memory_kb: int = 1024
    compile_output: str = ""
    results: List[_FakeTestResult] = field(default_factory=list)


class TestVisibilityRetentionAndDelete(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self._db_path = os.path.join(self._tmp.name, "test_noka.db")
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
                "JWT_SECRET_KEY": "test-secret-key-for-unit-tests",
                "SECRET_KEY": "test-secret-key-for-unit-tests",
                "ALLOW_PUBLIC_REGISTRATION": "true",
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

        # Ensure base roles exist
        for rname in ("admin", "teacher", "student"):
            self.db.execute("INSERT OR IGNORE INTO roles (name) VALUES (%s)", (rname,))

        self.app = create_app()
        self.client = TestClient(self.app)

        # Create admin, student1, student2
        self.admin_token, self.admin_id = self._create_user("admin_u", "admin@test.local", ["admin"])
        self.s1_token, self.s1_id = self._create_user("student1", "s1@test.local", ["student"])
        self.s2_token, self.s2_id = self._create_user("student2", "s2@test.local", ["student"])

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

    def _storage_exists(self, key: str) -> bool:
        return os.path.exists(self.storage._safe_path(key))

    def _create_user(self, username: str, email: str, roles: List[str]):
        from backend.app.core.security import create_access_token, hash_password

        uid = self.db.insert_returning_id(
            "INSERT INTO users (username, email, full_name, password_hash, is_active) VALUES (%s, %s, %s, %s, %s)",
            (username, email, username.title(), hash_password("Secret123!"), True),
        )
        for rname in roles:
            role = self.db.fetchone("SELECT id FROM roles WHERE name = %s", (rname,))
            self.db.execute(
                "INSERT INTO user_roles (user_id, role_id) VALUES (%s, %s)",
                (uid, int(role["id"])),
            )
        return create_access_token({"sub": str(uid), "username": username, "roles": roles}), uid

    def _headers(self, token: str):
        return {"Authorization": f"Bearer {token}"}

    def _create_problem(
        self,
        code: str,
        visibility: str = "public",
        allowed_user_ids: List[int] = None,
        retention_mode: str = "latest",
    ) -> dict:
        resp = self.client.post(
            "/api/v1/problems",
            headers=self._headers(self.admin_token),
            json={
                "code": code,
                "title": f"Problem {code}",
                "statement_md": "Solve it.",
                "difficulty": "easy",
                "points": 100,
                "visibility": visibility,
                "submission_retention_mode": retention_mode,
                "allowed_user_ids": allowed_user_ids or [],
                "time_limit_ms": 1000,
                "memory_limit_mb": 256,
            },
        )
        self.assertIn(resp.status_code, (200, 201), resp.text)
        prob = resp.json()
        # Add 1 hidden testcase so judging creates submission_results
        tc_resp = self.client.post(
            f"/api/v1/testcases/problem/{prob['id']}",
            headers=self._headers(self.admin_token),
            json={
                "name": "tc1",
                "input_data": "1 2\n",
                "expected_output": "3\n",
                "is_sample": False,
                "is_hidden": True,
            },
        )
        self.assertIn(tc_resp.status_code, (200, 201), tc_resp.text)
        prob["tc_id"] = tc_resp.json()["id"]
        return prob

    def test_problem_visibility_public_private_hidden(self) -> None:
        p_pub = self._create_problem("PUB01", visibility="public")
        p_priv = self._create_problem("PRIV01", visibility="private", allowed_user_ids=[self.s1_id])
        p_hid = self._create_problem("HID01", visibility="hidden")

        # Admin sees all 3
        r_admin = self.client.get("/api/v1/problems", headers=self._headers(self.admin_token))
        self.assertEqual(r_admin.status_code, 200)
        admin_codes = {item["code"] for item in r_admin.json()["items"]}
        self.assertEqual(admin_codes, {"PUB01", "PRIV01", "HID01"})

        # Admin visibility filter
        r_hid = self.client.get(
            "/api/v1/problems?visibility=hidden", headers=self._headers(self.admin_token)
        )
        self.assertEqual([i["code"] for i in r_hid.json()["items"]], ["HID01"])

        # Student1 sees PUB01 and PRIV01, NOT HID01
        r_s1 = self.client.get("/api/v1/problems", headers=self._headers(self.s1_token))
        s1_codes = {item["code"] for item in r_s1.json()["items"]}
        self.assertEqual(s1_codes, {"PUB01", "PRIV01"})

        # Student2 sees ONLY PUB01
        r_s2 = self.client.get("/api/v1/problems", headers=self._headers(self.s2_token))
        s2_codes = {item["code"] for item in r_s2.json()["items"]}
        self.assertEqual(s2_codes, {"PUB01"})

        # Direct GET & submit checks
        self.assertEqual(
            self.client.get(f"/api/v1/problems/{p_priv['code']}", headers=self._headers(self.s2_token)).status_code,
            403,
        )
        self.assertEqual(
            self.client.post(
                "/api/v1/submissions",
                headers=self._headers(self.s2_token),
                json={"problem_id": p_priv["id"], "language": "python3", "source_code": "print(3)"},
            ).status_code,
            403,
        )
        self.assertEqual(
            self.client.get(f"/api/v1/problems/{p_hid['code']}", headers=self._headers(self.s1_token)).status_code,
            404,
        )
        self.assertEqual(
            self.client.post(
                "/api/v1/submissions",
                headers=self._headers(self.s1_token),
                json={"problem_id": p_hid["id"], "language": "python3", "source_code": "print(3)"},
            ).status_code,
            404,
        )

        # Grant student2 access via PATCH /problems/{id}/access
        patch_resp = self.client.patch(
            f"/api/v1/problems/{p_priv['id']}/access",
            headers=self._headers(self.admin_token),
            json={"visibility": "private", "allowed_user_ids": [self.s1_id, self.s2_id]},
        )
        self.assertEqual(patch_resp.status_code, 200, patch_resp.text)
        self.assertEqual(
            self.client.get(f"/api/v1/problems/{p_priv['code']}", headers=self._headers(self.s2_token)).status_code,
            200,
        )
        r_s2_after = self.client.get("/api/v1/problems", headers=self._headers(self.s2_token))
        self.assertEqual({i["code"] for i in r_s2_after.json()["items"]}, {"PUB01", "PRIV01"})

        # Revoke student2 access
        patch_revoke = self.client.patch(
            f"/api/v1/problems/{p_priv['id']}/access",
            headers=self._headers(self.admin_token),
            json={"allowed_user_ids": [self.s1_id]},
        )
        self.assertEqual(patch_revoke.status_code, 200)
        self.assertEqual(
            self.client.get(f"/api/v1/problems/{p_priv['code']}", headers=self._headers(self.s2_token)).status_code,
            403,
        )
        # Ensure public problem still accessible
        self.assertEqual(
            self.client.get(f"/api/v1/problems/{p_pub['code']}", headers=self._headers(self.s2_token)).status_code,
            200,
        )

    def test_submission_retention_latest_and_best(self) -> None:
        p_latest = self._create_problem("RET_LAT", visibility="public", retention_mode="latest")
        p_best = self._create_problem("RET_BEST", visibility="public", retention_mode="best")

        def make_outcome(tc_id: int, score: int, verdict: str) -> _FakeJudgeOutcome:
            return _FakeJudgeOutcome(
                verdict=verdict,
                score=score,
                max_score=100,
                results=[
                    _FakeTestResult(
                        testcase_id=tc_id,
                        verdict=verdict,
                        execution_time_ms=10,
                        memory_kb=512,
                        score=score,
                        checker_message="SECRET_CHECKER_DETAIL",
                    )
                ],
            )

        # ---- Mode: LATEST ----
        with patch("judge.worker.worker.JudgeEngine.judge_submission") as mock_judge:
            mock_judge.return_value = make_outcome(p_latest["tc_id"], 100, "AC")
            r1 = self.client.post(
                "/api/v1/submissions",
                headers=self._headers(self.s1_token),
                json={"problem_id": p_latest["id"], "language": "python3", "source_code": "# attempt 1"},
            )
            self.assertIn(r1.status_code, (200, 201), r1.text)
            sub1_id = r1.json()["id"]
            sub1_key = f"submissions/sub_{sub1_id}.src"
            self.assertTrue(self._storage_exists(sub1_key))

            mock_judge.return_value = make_outcome(p_latest["tc_id"], 0, "WA")
            r2 = self.client.post(
                "/api/v1/submissions",
                headers=self._headers(self.s1_token),
                json={"problem_id": p_latest["id"], "language": "python3", "source_code": "# attempt 2"},
            )
            self.assertIn(r2.status_code, (200, 201), r2.text)
            sub2_id = r2.json()["id"]
            sub2_key = f"submissions/sub_{sub2_id}.src"

        rows = self.db.fetchall(
            "SELECT id, score, verdict FROM submissions WHERE user_id = %s AND problem_id = %s",
            (self.s1_id, p_latest["id"]),
        )
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["id"], sub2_id)
        self.assertFalse(self._storage_exists(sub1_key))
        self.assertTrue(self._storage_exists(sub2_key))

        # ---- Mode: BEST ----
        with patch("judge.worker.worker.JudgeEngine.judge_submission") as mock_judge:
            # Attempt A: 100 pts AC
            mock_judge.return_value = make_outcome(p_best["tc_id"], 100, "AC")
            ra = self.client.post(
                "/api/v1/submissions",
                headers=self._headers(self.s1_token),
                json={"problem_id": p_best["id"], "language": "python3", "source_code": "# best A"},
            )
            sub_a_id = ra.json()["id"]
            sub_a_key = f"submissions/sub_{sub_a_id}.src"
            self.assertTrue(self._storage_exists(sub_a_key))

            # Attempt B: 40 pts WA (strictly lower -> must be discarded from DB + storage, yet visible ephemerally!)
            mock_judge.return_value = make_outcome(p_best["tc_id"], 40, "WA")
            rb = self.client.post(
                "/api/v1/submissions",
                headers=self._headers(self.s1_token),
                json={"problem_id": p_best["id"], "language": "python3", "source_code": "# lower B"},
            )
            sub_b_id = rb.json()["id"]
            sub_b_key = f"submissions/sub_{sub_b_id}.src"

        # DB + storage must ONLY contain Attempt A
        best_rows = self.db.fetchall(
            "SELECT id, score FROM submissions WHERE user_id = %s AND problem_id = %s",
            (self.s1_id, p_best["id"]),
        )
        self.assertEqual(len(best_rows), 1)
        self.assertEqual(best_rows[0]["id"], sub_a_id)
        self.assertTrue(self._storage_exists(sub_a_key))
        self.assertFalse(self._storage_exists(sub_b_key))

        # Student polling Attempt B gets 200 with discarded_by_retention=True and redacted hidden testcase
        det_s1 = self.client.get(
            f"/api/v1/submissions/{sub_b_id}", headers=self._headers(self.s1_token)
        )
        self.assertEqual(det_s1.status_code, 200, det_s1.text)
        det_data = det_s1.json()
        self.assertTrue(det_data["discarded_by_retention"])
        self.assertEqual(det_data["kept_submission_id"], sub_a_id)
        self.assertEqual(det_data["kept_score"], 100)
        self.assertEqual(det_data["score"], 40)
        self.assertNotIn("SECRET_CHECKER_DETAIL", det_data["results"][0]["checker_message"])

        # Admin viewing ephemeral snapshot still sees unredacted checker detail (cache wasn't mutated in-place)
        det_admin = self.client.get(
            f"/api/v1/submissions/{sub_b_id}", headers=self._headers(self.admin_token)
        )
        self.assertEqual(det_admin.status_code, 200)
        self.assertEqual(det_admin.json()["results"][0]["checker_message"], "SECRET_CHECKER_DETAIL")

        # Attempt C: 100 pts AC (tie -> keeps newer Attempt C and deletes older Attempt A!)
        with patch("judge.worker.worker.JudgeEngine.judge_submission") as mock_judge:
            mock_judge.return_value = make_outcome(p_best["tc_id"], 100, "AC")
            rc = self.client.post(
                "/api/v1/submissions",
                headers=self._headers(self.s1_token),
                json={"problem_id": p_best["id"], "language": "python3", "source_code": "# tie newer C"},
            )
            sub_c_id = rc.json()["id"]
            sub_c_key = f"submissions/sub_{sub_c_id}.src"

        best_rows_after = self.db.fetchall(
            "SELECT id, score FROM submissions WHERE user_id = %s AND problem_id = %s",
            (self.s1_id, p_best["id"]),
        )
        self.assertEqual(len(best_rows_after), 1)
        self.assertEqual(best_rows_after[0]["id"], sub_c_id)
        self.assertFalse(self._storage_exists(sub_a_key))
        self.assertTrue(self._storage_exists(sub_c_key))

    def test_hard_delete_single_and_bulk(self) -> None:
        p1 = self._create_problem("DEL01", visibility="public", retention_mode="latest")
        p2 = self._create_problem("DEL02", visibility="public", retention_mode="latest")

        outcome = _FakeJudgeOutcome(
            verdict="AC",
            score=100,
            max_score=100,
            results=[
                _FakeTestResult(
                    testcase_id=p1["tc_id"],
                    verdict="AC",
                    execution_time_ms=5,
                    memory_kb=256,
                    score=100,
                    checker_message="OK",
                )
            ],
        )

        with patch("judge.worker.worker.JudgeEngine.judge_submission", return_value=outcome):
            s1_p1 = self.client.post(
                "/api/v1/submissions",
                headers=self._headers(self.s1_token),
                json={"problem_id": p1["id"], "language": "python3", "source_code": "print(1)"},
            ).json()["id"]
            s2_p1 = self.client.post(
                "/api/v1/submissions",
                headers=self._headers(self.s2_token),
                json={"problem_id": p1["id"], "language": "python3", "source_code": "print(2)"},
            ).json()["id"]
            outcome2 = _FakeJudgeOutcome(
                verdict="AC",
                score=100,
                max_score=100,
                results=[
                    _FakeTestResult(
                        testcase_id=p2["tc_id"],
                        verdict="AC",
                        execution_time_ms=5,
                        memory_kb=256,
                        score=100,
                        checker_message="OK",
                    )
                ],
            )
        with patch("judge.worker.worker.JudgeEngine.judge_submission", return_value=outcome2):
            s1_p2 = self.client.post(
                "/api/v1/submissions",
                headers=self._headers(self.s1_token),
                json={"problem_id": p2["id"], "language": "python3", "source_code": "print(3)"},
            ).json()["id"]

        # Student2 cannot delete Student1's submission
        self.assertEqual(
            self.client.delete(
                f"/api/v1/submissions/{s1_p1}", headers=self._headers(self.s2_token)
            ).status_code,
            403,
        )

        # Student1 can delete own submission (removes DB + storage)
        del_own = self.client.delete(
            f"/api/v1/submissions/{s1_p1}", headers=self._headers(self.s1_token)
        )
        self.assertEqual(del_own.status_code, 200)
        self.assertFalse(self._storage_exists(f"submissions/sub_{s1_p1}.src"))
        self.assertIsNone(self.db.fetchone("SELECT id FROM submissions WHERE id = %s", (s1_p1,)))

        # Student cannot call bulk delete
        self.assertEqual(
            self.client.delete(
                "/api/v1/submissions?delete_all=true", headers=self._headers(self.s1_token)
            ).status_code,
            403,
        )

        # Admin bulk delete by problem_code=DEL01 deletes s2_p1 only, keeps s1_p2
        bulk_p1 = self.client.delete(
            "/api/v1/submissions?problem_code=DEL01", headers=self._headers(self.admin_token)
        )
        self.assertEqual(bulk_p1.status_code, 200)
        self.assertEqual(bulk_p1.json()["deleted_count"], 1)
        self.assertFalse(self._storage_exists(f"submissions/sub_{s2_p1}.src"))
        self.assertTrue(self._storage_exists(f"submissions/sub_{s1_p2}.src"))

        # Admin bulk delete all removes s1_p2
        bulk_all = self.client.delete(
            "/api/v1/submissions?delete_all=true", headers=self._headers(self.admin_token)
        )
        self.assertEqual(bulk_all.status_code, 200)
        self.assertEqual(bulk_all.json()["deleted_count"], 1)
        self.assertFalse(self._storage_exists(f"submissions/sub_{s1_p2}.src"))
        self.assertEqual(len(self.db.fetchall("SELECT id FROM submissions")), 0)

    def test_contest_override_for_hidden_and_private_problems(self) -> None:
        from datetime import datetime, timedelta, timezone

        # Create a hidden problem and a private problem (NOT assigned to student1 or student2)
        p_hid = self._create_problem("CON_HID", visibility="hidden")
        p_priv = self._create_problem("CON_PRIV", visibility="private", allowed_user_ids=[])
        p_pub = self._create_problem("CON_PUB", visibility="public")

        now = datetime.now(timezone.utc)

        # 1. Create an UPCOMING restricted contest (only student1 is allowed) containing hidden + private problems
        r_con = self.client.post(
            "/api/v1/contests",
            headers=self._headers(self.admin_token),
            json={
                "title": "Restricted Contest Hidden/Private",
                "start_time": (now + timedelta(hours=1)).isoformat(),
                "end_time": (now + timedelta(hours=3)).isoformat(),
                "block_old_code": False,
                "problems": [
                    {"problem_id": p_hid["id"], "label": "A", "points": 100},
                    {"problem_id": p_priv["id"], "label": "B", "points": 100},
                ],
                "allowed_user_ids": [self.s1_id],
            },
        )
        self.assertEqual(r_con.status_code, 201, r_con.text)
        cid = r_con.json()["id"]

        # Problemset MUST keep hidden and private problems hidden for both students
        for tok in (self.s1_token, self.s2_token):
            ps = self.client.get("/api/v1/problems", headers=self._headers(tok))
            self.assertEqual({item["code"] for item in ps.json()["items"]}, {"CON_PUB"})

        # Admin sees all 3 problems (and visibility field on contest detail)
        admin_con = self.client.get(f"/api/v1/contests/{cid}", headers=self._headers(self.admin_token))
        self.assertEqual(admin_con.status_code, 200)
        self.assertEqual(
            {p["code"]: p["visibility"] for p in admin_con.json()["problems"]},
            {"CON_HID": "hidden", "CON_PRIV": "private"},
        )

        # BEFORE contest starts: student1 CANNOT see contest problem list, CANNOT view/run/submit hidden or private
        s1_up = self.client.get(f"/api/v1/contests/{cid}", headers=self._headers(self.s1_token))
        self.assertEqual(s1_up.status_code, 200)
        self.assertEqual(s1_up.json()["problems"], [])
        self.assertEqual(
            self.client.get(
                f"/api/v1/problems/{p_hid['code']}?contest_id={cid}",
                headers=self._headers(self.s1_token),
            ).status_code,
            404,
        )
        self.assertEqual(
            self.client.get(
                f"/api/v1/problems/{p_priv['code']}?contest_id={cid}",
                headers=self._headers(self.s1_token),
            ).status_code,
            403,
        )
        self.assertEqual(
            self.client.post(
                "/api/v1/submissions",
                headers=self._headers(self.s1_token),
                json={
                    "problem_id": p_hid["id"],
                    "contest_id": cid,
                    "language": "python3",
                    "source_code": "print(3)",
                },
            ).status_code,
            403,
        )
        self.assertEqual(
            self.client.post(
                "/api/v1/submissions/run-sample",
                headers=self._headers(self.s1_token),
                json={
                    "problem_id": p_hid["id"],
                    "contest_id": cid,
                    "language": "python3",
                    "source_code": "print(3)",
                },
            ).status_code,
            404,
        )

        # 2. Start the contest (RUNNING window)
        r_start = self.client.patch(
            f"/api/v1/contests/{cid}",
            headers=self._headers(self.admin_token),
            json={
                "start_time": (now - timedelta(minutes=10)).isoformat(),
                "end_time": (now + timedelta(hours=2)).isoformat(),
            },
        )
        self.assertEqual(r_start.status_code, 200, r_start.text)

        # Problemset STILL hides CON_HID and CON_PRIV even while contest is RUNNING
        ps_running = self.client.get("/api/v1/problems", headers=self._headers(self.s1_token))
        self.assertEqual({item["code"] for item in ps_running.json()["items"]}, {"CON_PUB"})

        # Allowed participant (student1) sees both problems on contest detail (without internal visibility leaked)
        s1_run = self.client.get(f"/api/v1/contests/{cid}", headers=self._headers(self.s1_token))
        self.assertEqual(s1_run.status_code, 200)
        self.assertEqual([p["code"] for p in s1_run.json()["problems"]], ["CON_HID", "CON_PRIV"])
        for p in s1_run.json()["problems"]:
            self.assertNotIn("visibility", p)

        # Allowed participant (student1) can GET full problem detail for both hidden and private (with or without contest_id)
        for prob in (p_hid, p_priv):
            r_det = self.client.get(
                f"/api/v1/problems/{prob['code']}?contest_id={cid}",
                headers=self._headers(self.s1_token),
            )
            self.assertEqual(r_det.status_code, 200, r_det.text)
            self.assertEqual(r_det.json()["statement_md"], "Solve it.")
            r_det_auto = self.client.get(
                f"/api/v1/problems/{prob['code']}",
                headers=self._headers(self.s1_token),
            )
            self.assertEqual(r_det_auto.status_code, 200, r_det_auto.text)

        # Allowed participant can run sample on hidden & private contest problems
        with patch("judge.worker.worker.JudgeEngine.run_sample", return_value={"verdict": "AC", "stdout": "3\n", "execution_time_ms": 5}):
            for prob in (p_hid, p_priv):
                r_rs = self.client.post(
                    "/api/v1/submissions/run-sample",
                    headers=self._headers(self.s1_token),
                    json={
                        "problem_id": prob["id"],
                        "contest_id": cid,
                        "language": "python3",
                        "source_code": "print(3)",
                    },
                )
                self.assertEqual(r_rs.status_code, 200, r_rs.text)

        # Allowed participant can SUBMIT hidden & private problems (both with contest_id and via active contest auto-override)
        outcome_hid = _FakeJudgeOutcome(
            verdict="AC",
            score=100,
            max_score=100,
            results=[_FakeTestResult(p_hid["tc_id"], "AC", 5, 256, 100, "OK")],
        )
        outcome_priv = _FakeJudgeOutcome(
            verdict="AC",
            score=100,
            max_score=100,
            results=[_FakeTestResult(p_priv["tc_id"], "AC", 5, 256, 100, "OK")],
        )
        with patch("judge.worker.worker.JudgeEngine.judge_submission", return_value=outcome_hid):
            r_sub_hid = self.client.post(
                "/api/v1/submissions",
                headers=self._headers(self.s1_token),
                json={
                    "problem_id": p_hid["id"],
                    "contest_id": cid,
                    "language": "python3",
                    "source_code": "print(3)",
                },
            )
            self.assertEqual(r_sub_hid.status_code, 201, r_sub_hid.text)
            sub_hid_id = r_sub_hid.json()["id"]

        with patch("judge.worker.worker.JudgeEngine.judge_submission", return_value=outcome_priv):
            r_sub_priv = self.client.post(
                "/api/v1/submissions",
                headers=self._headers(self.s1_token),
                json={
                    "problem_id": p_priv["id"],
                    "contest_id": cid,
                    "language": "python3",
                    "source_code": "print(3)",
                },
            )
            self.assertEqual(r_sub_priv.status_code, 201, r_sub_priv.text)
            sub_priv_id = r_sub_priv.json()["id"]

        # Student1 can view own submissions & details; scoreboard counts both AC problems
        s1_subs = self.client.get("/api/v1/submissions", headers=self._headers(self.s1_token)).json()["items"]
        self.assertTrue({sub_hid_id, sub_priv_id}.issubset({s["id"] for s in s1_subs}))
        self.assertEqual(
            self.client.get(f"/api/v1/submissions/{sub_hid_id}", headers=self._headers(self.s1_token)).status_code,
            200,
        )
        sb = self.client.get(f"/api/v1/contests/{cid}/scoreboard", headers=self._headers(self.s1_token)).json()
        self.assertEqual(sb["standings"][0]["username"], "student1")
        self.assertEqual(sb["standings"][0]["solved"], 2)

        # Outsider student2 is strictly blocked from restricted contest, its hidden/private problems, and cannot see student1's hidden/private submissions
        self.assertEqual(
            self.client.get(f"/api/v1/contests/{cid}", headers=self._headers(self.s2_token)).status_code,
            403,
        )
        self.assertEqual(
            self.client.get(
                f"/api/v1/problems/{p_hid['code']}?contest_id={cid}",
                headers=self._headers(self.s2_token),
            ).status_code,
            404,
        )
        self.assertEqual(
            self.client.get(
                f"/api/v1/problems/{p_priv['code']}?contest_id={cid}",
                headers=self._headers(self.s2_token),
            ).status_code,
            403,
        )
        self.assertEqual(
            self.client.post(
                "/api/v1/submissions",
                headers=self._headers(self.s2_token),
                json={
                    "problem_id": p_hid["id"],
                    "contest_id": cid,
                    "language": "python3",
                    "source_code": "print(3)",
                },
            ).status_code,
            403,
        )
        self.assertEqual(
            self.client.post(
                "/api/v1/submissions",
                headers=self._headers(self.s2_token),
                json={"problem_id": p_hid["id"], "language": "python3", "source_code": "print(3)"},
            ).status_code,
            404,
        )
        s2_subs = self.client.get("/api/v1/submissions", headers=self._headers(self.s2_token)).json()["items"]
        self.assertEqual(s2_subs, [])

        # 3. End the contest (ENDED window)
        r_end = self.client.patch(
            f"/api/v1/contests/{cid}",
            headers=self._headers(self.admin_token),
            json={
                "start_time": (now - timedelta(hours=3)).isoformat(),
                "end_time": (now - timedelta(minutes=5)).isoformat(),
            },
        )
        self.assertEqual(r_end.status_code, 200, r_end.text)

        # After contest ends: student1 can STILL review hidden & private statements via contest page
        self.assertEqual(
            self.client.get(
                f"/api/v1/problems/{p_hid['code']}?contest_id={cid}",
                headers=self._headers(self.s1_token),
            ).status_code,
            200,
        )
        # After contest ends: submitting with contest_id returns 403 (contest ended), and submitting without contest_id is blocked
        self.assertEqual(
            self.client.post(
                "/api/v1/submissions",
                headers=self._headers(self.s1_token),
                json={
                    "problem_id": p_hid["id"],
                    "contest_id": cid,
                    "language": "python3",
                    "source_code": "print(3)",
                },
            ).status_code,
            403,
        )
        self.assertEqual(
            self.client.post(
                "/api/v1/submissions",
                headers=self._headers(self.s1_token),
                json={"problem_id": p_hid["id"], "language": "python3", "source_code": "print(3)"},
            ).status_code,
            404,
        )

        # 4. Public (open) running contest grants hidden-problem access to any student while keeping Problemset clean
        p_open_hid = self._create_problem("OPEN_HID", visibility="hidden")
        r_open = self.client.post(
            "/api/v1/contests",
            headers=self._headers(self.admin_token),
            json={
                "title": "Public Open Contest",
                "start_time": (now - timedelta(minutes=10)).isoformat(),
                "end_time": (now + timedelta(hours=1)).isoformat(),
                "problems": [{"problem_id": p_open_hid["id"], "label": "A", "points": 100}],
            },
        )
        self.assertEqual(r_open.status_code, 201, r_open.text)
        open_cid = r_open.json()["id"]

        self.assertEqual(
            self.client.get(
                f"/api/v1/problems/{p_open_hid['code']}?contest_id={open_cid}",
                headers=self._headers(self.s2_token),
            ).status_code,
            200,
        )
        outcome_open = _FakeJudgeOutcome(
            verdict="AC",
            score=100,
            max_score=100,
            results=[_FakeTestResult(p_open_hid["tc_id"], "AC", 5, 256, 100, "OK")],
        )
        with patch("judge.worker.worker.JudgeEngine.judge_submission", return_value=outcome_open):
            r_open_sub = self.client.post(
                "/api/v1/submissions",
                headers=self._headers(self.s2_token),
                json={
                    "problem_id": p_open_hid["id"],
                    "contest_id": open_cid,
                    "language": "python3",
                    "source_code": "print(3)",
                },
            )
            self.assertEqual(r_open_sub.status_code, 201, r_open_sub.text)

        # Problemset STILL never leaks OPEN_HID
        ps_s2 = self.client.get("/api/v1/problems", headers=self._headers(self.s2_token)).json()["items"]
        self.assertEqual({item["code"] for item in ps_s2}, {"CON_PUB"})


if __name__ == "__main__":
    unittest.main()
