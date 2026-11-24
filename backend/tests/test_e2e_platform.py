"""End-to-End Platform Verification Tests covering Auth, RBAC, Problems, Testcases, ZIP Upload, Generator, Submissions, Hidden Protection, Contests & Classrooms."""
import io
import os
import tempfile
import unittest
import zipfile
from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient


class TestNokaJudgeEndToEnd(unittest.TestCase):
    def setUp(self) -> None:
        self.tmpdir = tempfile.TemporaryDirectory(prefix="noka_e2e_")
        os.environ["APP_ENV"] = "test"
        os.environ["JUDGE_DISPATCH_MODE"] = "inline"
        os.environ["JUDGE_MODE"] = "local_posix"
        os.environ["DATABASE_URL"] = f"sqlite:///{os.path.join(self.tmpdir.name, 'test.db')}"
        os.environ["STORAGE_LOCAL_PATH"] = os.path.join(self.tmpdir.name, "storage")
        os.environ["SECRET_KEY"] = "test-secret-key-for-e2e-suite-only"

        from backend.app.core.config import get_settings
        from backend.app.core.database import reset_db_instance
        from backend.app.core.security import hash_password
        from backend.app.core.storage import reset_storage_instance
        from backend.app.main import create_app

        get_settings.cache_clear()
        self.db = reset_db_instance(os.environ["DATABASE_URL"])
        self.db.init_schema()
        reset_storage_instance(os.environ["STORAGE_LOCAL_PATH"])

        # Seed initial Admin via secure DB bootstrap (simulating scripts/create_admin.py)
        admin_id = self.db.insert_returning_id(
            "INSERT INTO users (username, email, full_name, password_hash, is_active) VALUES (%s, %s, %s, %s, %s)",
            ("admin", "admin@noka.local", "Admin User", hash_password("AdminPass123!"), True),
        )
        admin_role = self.db.fetchone("SELECT id FROM roles WHERE name = 'admin'")
        self.db.execute("INSERT INTO user_roles (user_id, role_id) VALUES (%s, %s)", (admin_id, admin_role["id"]))

        self.app = create_app()
        self.client = TestClient(self.app)

    def tearDown(self) -> None:
        self.tmpdir.cleanup()

    def _login(self, username: str, password: str) -> dict:
        r = self.client.post("/api/v1/auth/login", json={"username": username, "password": password})
        self.assertEqual(r.status_code, 200, r.text)
        token = r.json()["access_token"]
        return {"Authorization": f"Bearer {token}"}

    def test_full_mvp_workflow(self) -> None:
        # 1. Admin login & create student account
        admin_h = self._login("admin", "AdminPass123!")
        r_stu = self.client.post(
            "/api/v1/users",
            headers=admin_h,
            json={
                "username": "student1",
                "email": "student1@noka.local",
                "full_name": "Nguyen Van A",
                "password": "StudentPass123!",
                "roles": ["student"],
            },
        )
        self.assertEqual(r_stu.status_code, 201, r_stu.text)
        student_h = self._login("student1", "StudentPass123!")

        # 2. RBAC: Student cannot access Admin API or Testcases API
        self.assertEqual(self.client.get("/api/v1/admin/settings", headers=student_h).status_code, 403)
        self.assertEqual(self.client.get("/api/v1/admin/audit-logs", headers=student_h).status_code, 403)

        # 3. Admin creates a problem
        r_prob = self.client.post(
            "/api/v1/problems",
            headers=admin_h,
            json={
                "code": "SUM2",
                "title": "Tong hai so nguyen",
                "statement_md": "Tinh $a + b$.",
                "sample_input": "2 3\n",
                "sample_output": "5\n",
                "time_limit_ms": 1000,
                "memory_limit_mb": 128,
                "points": 100,
                "difficulty": "easy",
                "visibility": "public",
                "tags": ["math", "beginner"],
            },
        )
        self.assertEqual(r_prob.status_code, 201, r_prob.text)
        pid = r_prob.json()["id"]

        # Student cannot view testcases endpoint
        self.assertEqual(self.client.get(f"/api/v1/testcases/problem/{pid}", headers=student_h).status_code, 403)

        # 4. Manual testcase creation
        r_tc1 = self.client.post(
            f"/api/v1/testcases/problem/{pid}",
            headers=admin_h,
            json={"name": "01", "input_data": "2 3\n", "expected_output": "5\n", "is_sample": True, "is_hidden": False},
        )
        self.assertEqual(r_tc1.status_code, 201)

        # 5. Upload ZIP with paired + unpaired warning + bad format check
        bad_zip = self.client.post(
            f"/api/v1/testcases/problem/{pid}/upload-zip",
            headers=admin_h,
            files={"file": ("not_a_zip.txt", b"hello", "text/plain")},
        )
        self.assertEqual(bad_zip.status_code, 400)

        zbuf = io.BytesIO()
        with zipfile.ZipFile(zbuf, "w") as zf:
            zf.writestr("02.in", "10 20\n")
            zf.writestr("02.out", "30\n")
            zf.writestr("03.in", "99 1\n")  # intentionally unpaired to verify warning
        zbuf.seek(0)
        r_zip = self.client.post(
            f"/api/v1/testcases/problem/{pid}/upload-zip",
            headers=admin_h,
            files={"file": ("tests.zip", zbuf.getvalue(), "application/zip")},
        )
        self.assertEqual(r_zip.status_code, 200, r_zip.text)
        self.assertEqual(r_zip.json()["imported_count"], 1)
        self.assertTrue(any("03.in" in w for w in r_zip.json()["warnings"]))

        # 6. Advanced Testcase Generator (Mode A: Custom Generator + AC Solution) -> Preview -> Save Selected
        ref_cpp = "#include <iostream>\nusing namespace std;\nint main(){ long long a,b; cin>>a>>b; cout<<a+b<<'\\n'; }\n"
        gen_py = "import random, sys\nr=random.Random(int(sys.argv[2]))\nprint(r.randint(1,500), r.randint(1,500))\n"
        r_gen = self.client.post(
            "/api/v1/testcase-generator/generate",
            headers=admin_h,
            json={
                "problem_id": pid,
                "mode": "custom_generator",
                "reference_code": ref_cpp,
                "reference_language": "cpp17",
                "generator_code": gen_py,
                "generator_language": "python3",
                "num_tests": 3,
                "seed": 42,
            },
        )
        self.assertEqual(r_gen.status_code, 200, r_gen.text)
        batch = r_gen.json()
        self.assertEqual(batch["success_count"], 3)

        # Must require confirmed=true
        r_save_unconf = self.client.post(
            f"/api/v1/testcase-generator/batches/{batch['batch_id']}/save",
            headers=admin_h,
            json={"problem_id": pid, "selected_indices": [1, 2, 3], "confirmed": False},
        )
        self.assertEqual(r_save_unconf.status_code, 400)

        r_save = self.client.post(
            f"/api/v1/testcase-generator/batches/{batch['batch_id']}/save",
            headers=admin_h,
            json={"problem_id": pid, "selected_indices": [1, 2, 3], "confirmed": True},
        )
        self.assertEqual(r_save.status_code, 200, r_save.text)
        self.assertEqual(r_save.json()["saved_count"], 3)

        # Verify total testcases = 1 manual + 1 zip + 3 generated = 5 (never overwrote existing!)
        tc_list = self.client.get(f"/api/v1/testcases/problem/{pid}", headers=admin_h).json()
        self.assertEqual(tc_list["total"], 5)

        # 7. Student submits AC (C++17), WA (Python3), CE (C++17) & Hidden Testcase Protection
        r_ac = self.client.post(
            "/api/v1/submissions",
            headers=student_h,
            json={"problem_id": pid, "language": "cpp17", "source_code": ref_cpp},
        )
        self.assertEqual(r_ac.status_code, 201, r_ac.text)
        self.assertEqual(r_ac.json()["verdict"], "AC")
        self.assertEqual(r_ac.json()["score"], 100)

        # Verify hidden testcase details are redacted for student in submission detail
        sub_detail = self.client.get(f"/api/v1/submissions/{r_ac.json()['id']}", headers=student_h).json()
        hidden_rows = [x for x in sub_detail["results"] if x.get("is_hidden")]
        self.assertTrue(len(hidden_rows) >= 4)
        for hr in hidden_rows:
            self.assertIn("protected", hr["checker_message"].lower())

        r_wa = self.client.post(
            "/api/v1/submissions",
            headers=student_h,
            json={"problem_id": pid, "language": "python3", "source_code": "print(0)\n"},
        )
        self.assertEqual(r_wa.json()["verdict"], "WA")

        r_ce = self.client.post(
            "/api/v1/submissions",
            headers=student_h,
            json={"problem_id": pid, "language": "cpp17", "source_code": "broken C++ code"},
        )
        self.assertEqual(r_ce.json()["verdict"], "CE")

        # 8. Contest creation, registration & scoreboard
        now = datetime.now(timezone.utc)
        r_con = self.client.post(
            "/api/v1/contests",
            headers=admin_h,
            json={
                "title": "Weekly Contest #1",
                "start_time": (now - timedelta(minutes=10)).isoformat(),
                "end_time": (now + timedelta(hours=2)).isoformat(),
                "problems": [{"problem_id": pid, "label": "A", "points": 100}],
            },
        )
        self.assertEqual(r_con.status_code, 201, r_con.text)
        cid = r_con.json()["id"]
        self.assertEqual(self.client.post(f"/api/v1/contests/{cid}/register", headers=student_h).status_code, 200)
        r_csub = self.client.post(
            "/api/v1/submissions",
            headers=student_h,
            json={"problem_id": pid, "contest_id": cid, "language": "cpp17", "source_code": ref_cpp},
        )
        self.assertEqual(r_csub.json()["verdict"], "AC")
        sb = self.client.get(f"/api/v1/contests/{cid}/scoreboard", headers=student_h).json()
        self.assertEqual(sb["standings"][0]["username"], "student1")
        self.assertEqual(sb["standings"][0]["solved"], 1)

        # 9. Classroom creation, join code, CSV import, assignment & progress
        r_cls = self.client.post(
            "/api/v1/classrooms",
            headers=admin_h,
            json={"name": "Lop Thuat Toan 10A", "description": "Co ban"},
        )
        self.assertEqual(r_cls.status_code, 201)
        cls_id = r_cls.json()["id"]
        join_code = r_cls.json()["join_code"]

        self.assertEqual(
            self.client.post("/api/v1/classrooms/join", headers=student_h, json={"join_code": join_code}).status_code,
            200,
        )
        csv_data = b"username,email,full_name,password\nstudent2,student2@noka.local,Tran Thi B,Pass12345!\n"
        r_imp = self.client.post(
            f"/api/v1/classrooms/{cls_id}/students/import",
            headers=admin_h,
            files={"file": ("students.csv", csv_data, "text/csv")},
        )
        self.assertEqual(r_imp.status_code, 200, r_imp.text)
        self.assertEqual(r_imp.json()["enrolled_count"], 1)

        r_asgn = self.client.post(
            "/api/v1/assignments",
            headers=admin_h,
            json={"classroom_id": cls_id, "title": "Bai tap tuan 1", "problem_ids": [pid]},
        )
        self.assertEqual(r_asgn.status_code, 201)
        prog = self.client.get(f"/api/v1/classrooms/{cls_id}/progress", headers=admin_h).json()
        self.assertEqual(len(prog["students"]), 2)
        s1_prog = next(x for x in prog["students"] if x["username"] == "student1")
        self.assertEqual(s1_prog["ac_count"], 1)


if __name__ == "__main__":
    unittest.main()
