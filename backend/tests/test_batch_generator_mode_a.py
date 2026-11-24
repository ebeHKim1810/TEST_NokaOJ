"""Tests for Mode A Batch Loop Custom Generator: single invocation, natural sort, Reference Solution pairing, error handling & storage save."""
import os
import subprocess
import sys
import tempfile
import unittest
from typing import List, Optional
from unittest.mock import patch

from fastapi.testclient import TestClient

from judge.compilers.compiler import CompileResult, CompilerManager
from judge.generators.engine import (
    TestcaseGeneratorEngine,
    discover_generated_input_files,
    natural_sort_key,
)
from judge.languages.registry import get_language
from judge.sandbox.runner import ExecutionResult, SandboxRunner


class _CrossPlatformTestCompiler(CompilerManager):
    """Cross-platform compiler helper for local Windows/POSIX tests (maps python3 -> sys.executable)."""

    def compile_source(
        self, source_code: str, language_id: str, work_dir: str, stem: str = "solution"
    ) -> CompileResult:
        if language_id != "python3":
            return super().compile_source(source_code, language_id, work_dir, stem=stem)
        spec = get_language("python3")
        source_path = os.path.join(work_dir, f"{stem}.py")
        with open(source_path, "w", encoding="utf-8") as f:
            f.write(source_code)
        proc = subprocess.run(
            [sys.executable, "-m", "py_compile", source_path],
            cwd=work_dir,
            capture_output=True,
        )
        if proc.returncode != 0:
            return CompileResult(
                success=False,
                source_path=source_path,
                binary_path=None,
                run_cmd=[],
                output=proc.stderr.decode("utf-8", errors="replace"),
                language=spec,
            )
        return CompileResult(
            success=True,
            source_path=source_path,
            binary_path=None,
            run_cmd=[sys.executable, "-I", source_path],
            output="",
            language=spec,
        )


class _CrossPlatformTestSandbox(SandboxRunner):
    """Cross-platform subprocess runner for local Windows/POSIX unit tests that tracks every invocation."""

    def __init__(self) -> None:
        super().__init__(mode="local_posix")
        self.calls: List[dict] = []

    def run(
        self,
        cmd: List[str],
        work_dir: str,
        stdin_data: str = "",
        time_limit_ms: int = 1000,
        memory_limit_mb: int = 256,
        args: Optional[List[str]] = None,
        writable_work_dir: bool = False,
    ) -> ExecutionResult:
        # Map python3 -> current interpreter so tests work identically on Windows & Linux
        mapped = [sys.executable if c == "python3" else c for c in cmd]
        full_cmd = mapped + (args or [])
        self.calls.append(
            {
                "cmd": full_cmd,
                "args": list(args or []),
                "work_dir": work_dir,
                "writable_work_dir": writable_work_dir,
            }
        )
        try:
            proc = subprocess.run(
                full_cmd,
                cwd=work_dir,
                input=stdin_data.encode("utf-8"),
                capture_output=True,
                timeout=max(1.0, time_limit_ms / 1000.0),
            )
        except subprocess.TimeoutExpired:
            return ExecutionResult(
                status="TLE",
                stdout="",
                stderr="",
                exit_code=-1,
                time_ms=time_limit_ms,
                memory_kb=0,
                error_message="Time Limit Exceeded",
            )
        if proc.returncode != 0:
            return ExecutionResult(
                status="RE",
                stdout=proc.stdout.decode("utf-8", errors="replace"),
                stderr=proc.stderr.decode("utf-8", errors="replace"),
                exit_code=proc.returncode,
                time_ms=10,
                memory_kb=512,
                error_message=f"Runtime Error (exit code {proc.returncode})",
            )
        return ExecutionResult(
            status="OK",
            stdout=proc.stdout.decode("utf-8", errors="replace"),
            stderr=proc.stderr.decode("utf-8", errors="replace"),
            exit_code=0,
            time_ms=10,
            memory_kb=512,
        )


class TestBatchGeneratorModeA(unittest.TestCase):
    def test_natural_sort_and_discovery(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            for name in ["test_10.in", "test_2.in", "test_1.in", "test_11.in", "readme.txt", ".hidden.in"]:
                with open(os.path.join(td, name), "w", encoding="utf-8") as f:
                    f.write("1\n")
            found = discover_generated_input_files(td)
            self.assertEqual([s for s, _ in found], ["test_1", "test_2", "test_10", "test_11"])
            self.assertLess(natural_sort_key("test_2.in"), natural_sort_key("test_10.in"))

    def test_mode_a_runs_once_splits_subtasks_and_saves_to_storage(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        db_path = os.path.join(tmp.name, "test_gen.db")
        storage_path = os.path.join(tmp.name, "storage")
        os.makedirs(storage_path, exist_ok=True)

        env_patch = patch.dict(
            os.environ,
            {
                "DATABASE_URL": f"sqlite:///{db_path}",
                "STORAGE_BACKEND": "local",
                "STORAGE_LOCAL_PATH": storage_path,
                "JUDGE_DISPATCH_MODE": "inline",
                "APP_ENV": "test",
                "SECRET_KEY": "test-secret-batch-gen",
            },
        )
        env_patch.start()
        self.addCleanup(env_patch.stop)

        from backend.app.core import database, storage
        from backend.app.core.cache import app_cache
        from backend.app.core.config import get_settings
        from backend.app.core.security import create_access_token, hash_password
        from backend.app.main import create_app

        app_cache.clear()
        get_settings.cache_clear()
        database._db_instance = None
        storage._storage_instance = None

        db = database.get_db()
        db.init_schema()
        st = storage.get_storage()
        for rname in ("admin", "teacher", "student"):
            db.execute("INSERT OR IGNORE INTO roles (name) VALUES (%s)", (rname,))

        uid = db.insert_returning_id(
            "INSERT INTO users (username, email, full_name, password_hash, is_active) VALUES (%s, %s, %s, %s, %s)",
            ("admin_g", "ag@test.local", "Admin G", hash_password("Secret123!"), True),
        )
        role = db.fetchone("SELECT id FROM roles WHERE name = 'admin'")
        db.execute("INSERT INTO user_roles (user_id, role_id) VALUES (%s, %s)", (uid, int(role["id"])))
        token = create_access_token({"sub": str(uid), "username": "admin_g", "roles": ["admin"]})
        headers = {"Authorization": f"Bearer {token}"}

        client = TestClient(create_app())
        p_resp = client.post(
            "/api/v1/problems",
            headers=headers,
            json={"code": "BATCH01", "title": "Array Sum", "statement_md": "Sum n numbers."},
        )
        self.assertEqual(p_resp.status_code, 201)
        pid = p_resp.json()["id"]

        gen_py = """
import sys
T = int(sys.argv[1])
for t in range(1, T + 1):
    # Subtask 1 (t <= 4): small n=t; Subtask 2 (t > 4): larger n=10+t
    n = t if t <= 4 else 10 + t
    with open(f"test_{t}.in", "w", encoding="utf-8") as f:
        f.write(f"{n}\\n")
        f.write(" ".join(str(i) for i in range(1, n + 1)) + "\\n")
"""
        ref_py = """
import sys
data = list(map(int, sys.stdin.read().split()))
n = data[0]
print(sum(data[1:1+n]))
"""

        fake_sandbox = _CrossPlatformTestSandbox()
        fake_compiler = _CrossPlatformTestCompiler()
        with patch("backend.app.api.v1.testcase_generator.TestcaseGeneratorEngine") as mock_cls:
            mock_cls.return_value = TestcaseGeneratorEngine(sandbox=fake_sandbox, compiler=fake_compiler)
            res = client.post(
                "/api/v1/testcase-generator/generate",
                headers=headers,
                json={
                    "problem_id": pid,
                    "mode": "custom_generator",
                    "reference_code": ref_py,
                    "reference_language": "python3",
                    "generator_code": gen_py,
                    "generator_language": "python3",
                    "num_tests": 10,
                    "seed": 12345,
                },
            )
        self.assertEqual(res.status_code, 200, res.text)
        batch = res.json()
        self.assertEqual(batch["requested_count"], 10)
        self.assertEqual(batch["success_count"], 10)
        self.assertEqual(batch["failed_count"], 0)
        # Verify natural order: test_1 .. test_10 (not test_1, test_10, test_2)
        self.assertEqual([i["name"] for i in batch["items"]], [f"test_{t}" for t in range(1, 11)])
        # Verify subtask outputs: test_1 (n=1 -> sum=1), test_10 (n=20 -> sum=210)
        self.assertEqual(batch["items"][0]["output_preview"].strip(), "1")
        self.assertEqual(batch["items"][9]["output_preview"].strip(), "210")

        # Verify generator ran EXACTLY ONCE with writable_work_dir=True and argv=["10", "12345"]
        gen_calls = [c for c in fake_sandbox.calls if c["writable_work_dir"]]
        ref_calls = [c for c in fake_sandbox.calls if not c["writable_work_dir"]]
        self.assertEqual(len(gen_calls), 1)
        self.assertEqual(gen_calls[0]["args"], ["10", "12345"])
        self.assertEqual(len(ref_calls), 10)
        # Verify temp directory was cleaned up completely
        self.assertFalse(os.path.exists(gen_calls[0]["work_dir"]))

        # Save batch to problem & verify storage + DB metadata
        save_resp = client.post(
            f"/api/v1/testcase-generator/batches/{batch['batch_id']}/save",
            headers=headers,
            json={
                "problem_id": pid,
                "selected_indices": list(range(1, 11)),
                "confirmed": True,
            },
        )
        self.assertEqual(save_resp.status_code, 200, save_resp.text)
        self.assertEqual(save_resp.json()["saved_count"], 10)

        tc_rows = db.fetchall("SELECT * FROM testcases WHERE problem_id = %s ORDER BY order_index ASC", (pid,))
        self.assertEqual(len(tc_rows), 10)
        self.assertEqual([r["name"] for r in tc_rows], [f"test_{t}" for t in range(1, 11)])
        self.assertEqual(st.get_text(tc_rows[9]["output_storage_key"]).strip(), "210")

    def test_mode_a_error_when_no_in_files_and_per_test_ref_failure(self) -> None:
        fake_sandbox = _CrossPlatformTestSandbox()
        engine = TestcaseGeneratorEngine(sandbox=fake_sandbox, compiler=_CrossPlatformTestCompiler())

        # 1. Generator creates NO .in files -> clear Vietnamese error
        rep_empty = engine.generate(
            mode="custom_generator",
            reference_code="print(1)\n",
            reference_language="python3",
            generator_code="print('forgot to write .in files')\n",
            generator_language="python3",
            num_tests=3,
        )
        self.assertEqual(rep_empty.success_count, 0)
        self.assertIn(".in", rep_empty.generator_compile_error)

        # 2. Reference Solution crashes on test #2 only -> reports Test #2 clearly while #1 & #3 succeed
        gen_3 = """
import sys
for t in range(1, 4):
    with open(f"test_{t:02d}.in", "w") as f:
        f.write(f"{t}\\n")
"""
        ref_crash_on_2 = """
x = int(input())
if x == 2:
    raise RuntimeError("boom on test 2")
print(x * 10)
"""
        rep_partial = engine.generate(
            mode="custom_generator",
            reference_code=ref_crash_on_2,
            reference_language="python3",
            generator_code=gen_3,
            generator_language="python3",
            num_tests=3,
        )
        self.assertEqual(rep_partial.success_count, 2)
        self.assertEqual(rep_partial.failed_count, 1)
        self.assertEqual(rep_partial.items[0].status, "SUCCESS")
        self.assertEqual(rep_partial.items[1].status, "FAILED")
        self.assertIn("Test #2", rep_partial.items[1].error)
        self.assertIn("test_02", rep_partial.items[1].error)
        self.assertEqual(rep_partial.items[2].status, "SUCCESS")


if __name__ == "__main__":
    unittest.main()
