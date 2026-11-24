"""
Independent Judge Engine & Worker.
Runs completely separated from FastAPI backend in production, consuming jobs
from Redis queue (noka:judge:submissions) or DB pending polling.
"""
import json
import logging
import os
import sys
import tempfile
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from judge.checkers.checker import evaluate_compiled_custom_checker, evaluate_output
from judge.compilers.compiler import CompilerManager
from judge.sandbox.runner import SandboxRunner, create_exec_temp_dir

logging.basicConfig(level=logging.INFO, format="[%(asctime)s] [JUDGE] %(levelname)s: %(message)s")
logger = logging.getLogger("noka.judge")

VERDICT_PRIORITY = ["CE", "IE", "MLE", "TLE", "OLE", "RE", "WA", "AC"]


@dataclass
class TestcaseInput:
    testcase_id: int
    name: str
    input_data: str
    expected_output: str
    group_id: Optional[int] = None
    group_points: int = 0


@dataclass
class TestcaseJudgeResult:
    testcase_id: int
    verdict: str
    execution_time_ms: int
    memory_kb: int
    score: int
    checker_message: str


@dataclass
class SubmissionJudgeResult:
    verdict: str
    score: int
    max_score: int
    execution_time_ms: int
    memory_kb: int
    compile_output: str = ""
    results: List[TestcaseJudgeResult] = field(default_factory=list)


class JudgeEngine:
    """Core judging pipeline: Compile -> Run per testcase -> Check -> Subtask scoring."""

    def __init__(
        self,
        sandbox: Optional[SandboxRunner] = None,
        compiler: Optional[CompilerManager] = None,
    ) -> None:
        self.sandbox = sandbox or SandboxRunner()
        self.compiler = compiler or CompilerManager()

    def run_sample(
        self,
        source_code: str,
        language_id: str,
        sample_input: str,
        expected_output: Optional[str] = None,
        time_limit_ms: int = 1000,
        memory_limit_mb: int = 256,
        checker_type: str = "standard",
        checker_source: Optional[str] = None,
        checker_language: str = "python3",
    ) -> Dict[str, Any]:
        with create_exec_temp_dir(prefix="noka_sample_") as work_dir:
            comp = self.compiler.compile_source(source_code, language_id, work_dir)
            if not comp.success:
                return {
                    "verdict": "CE",
                    "stdout": "",
                    "stderr": "",
                    "compile_output": comp.output,
                    "execution_time_ms": 0,
                    "memory_kb": 0,
                    "checker_message": "Compilation Error",
                }
            res = self.sandbox.run(
                comp.run_cmd,
                work_dir=work_dir,
                stdin_data=sample_input,
                time_limit_ms=int(time_limit_ms * comp.language.time_multiplier),
                memory_limit_mb=memory_limit_mb + comp.language.memory_bonus_mb,
            )
            if res.status != "OK":
                return {
                    "verdict": res.status,
                    "stdout": res.stdout,
                    "stderr": res.stderr,
                    "compile_output": "",
                    "execution_time_ms": res.time_ms,
                    "memory_kb": res.memory_kb,
                    "checker_message": res.error_message,
                }
            verdict = "OK"
            chk_msg = "Executed successfully."
            if checker_type == "custom" and checker_source:
                chk = evaluate_output(
                    "custom",
                    expected_output or "",
                    res.stdout,
                    sample_input,
                    checker_source=checker_source,
                    checker_language=checker_language,
                    sandbox=self.sandbox,
                )
                verdict = "AC" if chk.accepted else "WA"
                chk_msg = chk.message
            elif expected_output is not None and expected_output != "":
                chk = evaluate_output(checker_type, expected_output, res.stdout, sample_input)
                verdict = "AC" if chk.accepted else "WA"
                chk_msg = chk.message
            return {
                "verdict": verdict,
                "stdout": res.stdout,
                "stderr": res.stderr,
                "compile_output": "",
                "execution_time_ms": res.time_ms,
                "memory_kb": res.memory_kb,
                "checker_message": chk_msg,
            }

    def judge_submission(
        self,
        source_code: str,
        language_id: str,
        testcases: List[TestcaseInput],
        time_limit_ms: int = 1000,
        memory_limit_mb: int = 256,
        max_points: int = 100,
        checker_type: str = "standard",
        checker_source: Optional[str] = None,
        checker_language: str = "python3",
    ) -> SubmissionJudgeResult:
        if not testcases:
            return SubmissionJudgeResult(
                verdict="IE",
                score=0,
                max_score=max_points,
                execution_time_ms=0,
                memory_kb=0,
                compile_output="No testcases configured for this problem.",
                results=[],
            )

        with create_exec_temp_dir(prefix="noka_sub_") as work_dir:
            comp = self.compiler.compile_source(source_code, language_id, work_dir)
            if not comp.success:
                return SubmissionJudgeResult(
                    verdict="CE",
                    score=0,
                    max_score=max_points,
                    execution_time_ms=0,
                    memory_kb=0,
                    compile_output=comp.output,
                    results=[],
                )

            # Pre-compile custom checker ONCE for all testcases
            chk_temp_ctx = None
            chk_work_dir: Optional[str] = None
            chk_run_cmd: Optional[List[str]] = None
            try:
                if checker_type == "custom":
                    if not checker_source or not checker_source.strip():
                        return SubmissionJudgeResult(
                            verdict="IE",
                            score=0,
                            max_score=max_points,
                            execution_time_ms=0,
                            memory_kb=0,
                            compile_output="Custom checker source is not configured for this problem.",
                            results=[],
                        )
                    chk_temp_ctx = create_exec_temp_dir(prefix="noka_chk_")
                    chk_work_dir = chk_temp_ctx.__enter__()
                    chk_comp = self.compiler.compile_source(
                        checker_source, checker_language or "python3", chk_work_dir, stem="checker"
                    )
                    if not chk_comp.success:
                        return SubmissionJudgeResult(
                            verdict="IE",
                            score=0,
                            max_score=max_points,
                            execution_time_ms=0,
                            memory_kb=0,
                            compile_output=f"Custom checker compile error:\n{chk_comp.output}",
                            results=[],
                        )
                    chk_run_cmd = chk_comp.run_cmd

                eff_tl = int(time_limit_ms * comp.language.time_multiplier)
                eff_ml = memory_limit_mb + comp.language.memory_bonus_mb

                tc_results: List[TestcaseJudgeResult] = []
                max_time = 0
                max_mem = 0
                verdicts_seen: List[str] = []

                # Track subtasks if groups are assigned
                has_groups = any(tc.group_id is not None for tc in testcases)
                group_passed: Dict[int, bool] = {}
                group_points_map: Dict[int, int] = {}

                for tc in testcases:
                    if tc.group_id is not None:
                        group_passed.setdefault(tc.group_id, True)
                        group_points_map[tc.group_id] = tc.group_points

                    run_res = self.sandbox.run(
                        comp.run_cmd,
                        work_dir=work_dir,
                        stdin_data=tc.input_data,
                        time_limit_ms=eff_tl,
                        memory_limit_mb=eff_ml,
                    )
                    max_time = max(max_time, run_res.time_ms)
                    max_mem = max(max_mem, run_res.memory_kb)

                    if run_res.status != "OK":
                        verdict = run_res.status
                        msg = run_res.error_message or run_res.stderr[:250]
                    else:
                        if checker_type == "custom" and chk_run_cmd and chk_work_dir:
                            chk = evaluate_compiled_custom_checker(
                                chk_run_cmd,
                                chk_work_dir,
                                tc.input_data,
                                tc.expected_output,
                                run_res.stdout,
                                sandbox=self.sandbox,
                            )
                        else:
                            chk = evaluate_output(
                                checker_type=checker_type,
                                expected=tc.expected_output,
                                actual=run_res.stdout,
                                input_data=tc.input_data,
                                checker_source=checker_source,
                                checker_language=checker_language,
                                sandbox=self.sandbox,
                            )
                        verdict = "AC" if chk.accepted else "WA"
                        msg = chk.message

                    verdicts_seen.append(verdict)
                    if tc.group_id is not None and verdict != "AC":
                        group_passed[tc.group_id] = False

                    tc_results.append(
                        TestcaseJudgeResult(
                            testcase_id=tc.testcase_id,
                            verdict=verdict,
                            execution_time_ms=run_res.time_ms,
                            memory_kb=run_res.memory_kb,
                            score=1 if verdict == "AC" else 0,
                            checker_message=msg,
                        )
                    )
            finally:
                if chk_temp_ctx is not None:
                    chk_temp_ctx.__exit__(None, None, None)

            # Calculate score (subtask all-or-nothing if groups exist, else proportional partial scoring)
            if has_groups and sum(group_points_map.values()) > 0:
                total_score = sum(
                    pts for gid, pts in group_points_map.items() if group_passed.get(gid, False)
                )
                effective_max = sum(group_points_map.values())
            else:
                ac_count = sum(1 for r in tc_results if r.verdict == "AC")
                total_score = int(round((ac_count / len(tc_results)) * max_points))
                effective_max = max_points

            # Overall verdict by severity priority
            overall = "AC"
            for v in VERDICT_PRIORITY:
                if v in verdicts_seen:
                    overall = v
                    break

            return SubmissionJudgeResult(
                verdict=overall,
                score=total_score,
                max_score=effective_max,
                execution_time_ms=max_time,
                memory_kb=max_mem,
                compile_output="",
                results=tc_results,
            )


def run_worker_loop() -> None:
    """Standalone Judge Worker entry point for Docker / production deployments."""
    # Ensure repository root is importable
    repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
    if repo_root not in sys.path:
        sys.path.insert(0, repo_root)

    from backend.app.core.database import get_db
    from backend.app.core.storage import get_storage
    from backend.app.services.submission_service import process_submission_job

    redis_url = os.getenv("REDIS_URL", "")
    redis_client = None
    if redis_url:
        try:
            import redis  # type: ignore
            redis_client = redis.Redis.from_url(redis_url, decode_responses=True)
            redis_client.ping()
            logger.info("Connected to Redis queue at %s", redis_url)
        except Exception as exc:
            logger.warning("Redis unavailable (%s); falling back to DB polling.", exc)
            redis_client = None

    logger.info("Noka JUDGE Worker started (mode=%s).", os.getenv("JUDGE_MODE", "local_posix"))
    while True:
        try:
            submission_id = None
            if redis_client is not None:
                item = redis_client.blpop("noka:judge:submissions", timeout=2)
                if item:
                    payload = json.loads(item[1])
                    submission_id = int(payload["submission_id"])
            if submission_id is None:
                db = get_db()
                row = db.fetchone(
                    "SELECT id FROM submissions WHERE status = 'PENDING' ORDER BY id ASC LIMIT 1"
                )
                if row:
                    submission_id = int(row["id"])
            if submission_id is not None:
                logger.info("Judging submission #%d ...", submission_id)
                process_submission_job(submission_id, get_db(), get_storage())
                logger.info("Finished submission #%d.", submission_id)
            else:
                time.sleep(0.5)
        except KeyboardInterrupt:
            logger.info("Judge Worker shutting down.")
            break
        except Exception as exc:
            logger.exception("Worker error: %s", exc)
            time.sleep(1.0)


if __name__ == "__main__":
    run_worker_loop()
