"""Output checkers: Standard (CRLF/LF & trailing-space safe), Strict, Float Tolerance, Custom Checker."""
import math
import os
import tempfile
from dataclasses import dataclass
from typing import Optional

from judge.compilers.compiler import CompilerManager
from judge.sandbox.runner import SandboxRunner, create_exec_temp_dir


@dataclass
class CheckResult:
    accepted: bool
    message: str = ""


def _normalize_standard(text: str) -> list[str]:
    """
    Normalize CRLF/CR to LF, strip trailing horizontal spaces per line,
    and strip trailing blank lines without blindly ignoring internal whitespace.
    """
    normalized = text.replace("\r\n", "\n").replace("\r", "\n")
    lines = [line.rstrip(" \t") for line in normalized.split("\n")]
    while lines and lines[-1] == "":
        lines.pop()
    return lines


def check_standard(expected: str, actual: str) -> CheckResult:
    exp_lines = _normalize_standard(expected)
    act_lines = _normalize_standard(actual)
    if exp_lines == act_lines:
        return CheckResult(True, "Output matched.")
    if len(exp_lines) != len(act_lines):
        return CheckResult(
            False,
            f"Line count mismatch: expected {len(exp_lines)} line(s), got {len(act_lines)}.",
        )
    for idx, (e, a) in enumerate(zip(exp_lines, act_lines), start=1):
        if e != a:
            return CheckResult(
                False,
                f"Mismatch on line {idx}: expected '{e[:80]}', got '{a[:80]}'.",
            )
    return CheckResult(False, "Wrong Answer.")


def check_strict(expected: str, actual: str) -> CheckResult:
    exp = expected.replace("\r\n", "\n")
    act = actual.replace("\r\n", "\n")
    if exp == act:
        return CheckResult(True, "Exact match.")
    return CheckResult(False, "Strict output mismatch.")


def check_float_tol(expected: str, actual: str, eps: float = 1e-6) -> CheckResult:
    exp_tokens = expected.split()
    act_tokens = actual.split()
    if len(exp_tokens) != len(act_tokens):
        return CheckResult(
            False,
            f"Token count mismatch: expected {len(exp_tokens)}, got {len(act_tokens)}.",
        )
    for idx, (et, at) in enumerate(zip(exp_tokens, act_tokens), start=1):
        if et == at:
            continue
        try:
            ef = float(et)
            af = float(at)
            if math.isnan(af) or math.isinf(af):
                return CheckResult(False, f"Invalid float on token {idx}: {at}")
            if abs(ef - af) <= eps * max(1.0, abs(ef)):
                continue
        except ValueError:
            pass
        return CheckResult(
            False, f"Token {idx} mismatch: expected '{et[:60]}', got '{at[:60]}'."
        )
    return CheckResult(True, f"Matched within tolerance {eps}.")


def evaluate_compiled_custom_checker(
    run_cmd: list[str],
    work_dir: str,
    input_data: str,
    expected_output: str,
    actual_output: str,
    sandbox: Optional[SandboxRunner] = None,
) -> CheckResult:
    """
    Executes an already-compiled teacher checker inside the sandbox.
    - Contestant's actual output is fed directly into stdin (`actual_output`).
    - Testcase input, expected output, and actual output are also written to
      `input.txt`, `expected.txt`, `actual.txt` and passed as argv[1..3].
    - Checker prints "OK" -> Accepted (AC); prints "NO" (or anything else) -> Wrong Answer (WA).
    """
    sbx = sandbox or SandboxRunner()
    in_path = os.path.join(work_dir, "input.txt")
    exp_path = os.path.join(work_dir, "expected.txt")
    act_path = os.path.join(work_dir, "actual.txt")
    with open(in_path, "w", encoding="utf-8") as f:
        f.write(input_data)
    with open(exp_path, "w", encoding="utf-8") as f:
        f.write(expected_output)
    with open(act_path, "w", encoding="utf-8") as f:
        f.write(actual_output)

    res = sbx.run(
        run_cmd,
        work_dir=work_dir,
        stdin_data=actual_output,
        args=[in_path, exp_path, act_path],
        time_limit_ms=3000,
        memory_limit_mb=256,
    )
    if res.status != "OK" or res.exit_code != 0:
        msg = (res.stdout or res.stderr or res.error_message or f"Checker error ({res.status})").strip()[:300]
        return CheckResult(False, msg)

    out = (res.stdout or "").strip()
    tokens = out.split()
    first = tokens[0].upper() if tokens else ""
    if first == "OK":
        return CheckResult(True, out[:300])
    if first == "NO":
        return CheckResult(False, out[:300])
    return CheckResult(
        False,
        f"Trình chấm phải in 'OK' hoặc 'NO' (nhận được: '{out[:150]}')",
    )


def check_custom(
    checker_source: str,
    checker_language: str,
    input_data: str,
    expected_output: str,
    actual_output: str,
    sandbox: Optional[SandboxRunner] = None,
) -> CheckResult:
    """Compiles and runs a teacher-provided Special Judge inside the sandbox."""
    sbx = sandbox or SandboxRunner()
    compiler = CompilerManager()
    with create_exec_temp_dir(prefix="noka_chk_") as work_dir:
        comp = compiler.compile_source(
            checker_source, checker_language, work_dir, stem="checker"
        )
        if not comp.success:
            return CheckResult(False, f"Custom checker compile error: {comp.output[:300]}")
        return evaluate_compiled_custom_checker(
            comp.run_cmd,
            work_dir,
            input_data,
            expected_output,
            actual_output,
            sandbox=sbx,
        )


def evaluate_output(
    checker_type: str,
    expected: str,
    actual: str,
    input_data: str = "",
    checker_source: Optional[str] = None,
    checker_language: str = "python3",
    sandbox: Optional[SandboxRunner] = None,
) -> CheckResult:
    if checker_type == "strict":
        return check_strict(expected, actual)
    if checker_type == "float_tol":
        return check_float_tol(expected, actual)
    if checker_type == "custom":
        if not checker_source or not checker_source.strip():
            return CheckResult(False, "Chưa cấu hình mã nguồn cho trình chấm tùy chỉnh.")
        return check_custom(
            checker_source,
            checker_language,
            input_data,
            expected,
            actual,
            sandbox=sandbox,
        )
    return check_standard(expected, actual)
