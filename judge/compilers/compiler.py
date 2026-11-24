"""Compilation manager for C++17, C++20, and Python 3."""
import os
import subprocess
from dataclasses import dataclass
from typing import List, Optional

from judge.languages.registry import LanguageSpec, get_language


@dataclass
class CompileResult:
    success: bool
    source_path: str
    binary_path: Optional[str]
    run_cmd: List[str]
    output: str
    language: LanguageSpec


class CompilerManager:
    def __init__(self, compile_timeout_sec: int = 15) -> None:
        self.compile_timeout_sec = int(
            os.getenv("JUDGE_COMPILE_TIMEOUT_SEC", str(compile_timeout_sec))
        )

    def compile_source(
        self, source_code: str, language_id: str, work_dir: str, stem: str = "solution"
    ) -> CompileResult:
        spec = get_language(language_id)
        source_path = os.path.join(work_dir, f"{stem}{spec.extension}")
        binary_path = os.path.join(work_dir, stem) if spec.is_compiled else None

        with open(source_path, "w", encoding="utf-8") as f:
            f.write(source_code)

        if spec.compile_cmd:
            cmd = [
                token.format(source=source_path, binary=binary_path or "")
                for token in spec.compile_cmd
            ]
            safe_env = {
                "PATH": "/usr/local/bin:/usr/bin:/bin",
                "LANG": "C.UTF-8",
                "LC_ALL": "C.UTF-8",
            }
            try:
                proc = subprocess.run(
                    cmd,
                    cwd=work_dir,
                    capture_output=True,
                    timeout=self.compile_timeout_sec,
                    env=safe_env,
                )
            except subprocess.TimeoutExpired:
                return CompileResult(
                    success=False,
                    source_path=source_path,
                    binary_path=binary_path,
                    run_cmd=[],
                    output="Compilation timed out.",
                    language=spec,
                )
            except FileNotFoundError as exc:
                return CompileResult(
                    success=False,
                    source_path=source_path,
                    binary_path=binary_path,
                    run_cmd=[],
                    output=f"Compiler not found: {exc}",
                    language=spec,
                )

            combined = (
                proc.stdout.decode("utf-8", errors="replace")
                + proc.stderr.decode("utf-8", errors="replace")
            ).strip()

            if proc.returncode != 0:
                return CompileResult(
                    success=False,
                    source_path=source_path,
                    binary_path=binary_path,
                    run_cmd=[],
                    output=combined[:8000] or "Compilation failed.",
                    language=spec,
                )

        run_cmd = [
            token.format(source=source_path, binary=binary_path or "")
            for token in spec.run_cmd
        ]
        return CompileResult(
            success=True,
            source_path=source_path,
            binary_path=binary_path,
            run_cmd=run_cmd,
            output="",
            language=spec,
        )
