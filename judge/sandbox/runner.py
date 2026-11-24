"""Isolated Sandbox Execution Runner supporting Docker and POSIX rlimit sandboxing."""
import os
import resource
import shutil
import signal
import stat
import subprocess
import tempfile
import time
from dataclasses import dataclass
from typing import List, Optional


_CACHED_EXEC_ROOT: Optional[str] = None


def _dir_supports_exec(base_dir: str) -> bool:
    try:
        os.makedirs(base_dir, exist_ok=True)
        probe = os.path.join(base_dir, f".noka_exec_probe_{os.getpid()}.sh")
        with open(probe, "w", encoding="utf-8") as f:
            f.write("#!/bin/sh\nexit 0\n")
        os.chmod(probe, stat.S_IRWXU)
        res = subprocess.run([probe], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        os.remove(probe)
        return res.returncode == 0
    except Exception:
        return False


def get_exec_work_root() -> str:
    """Returns a writable directory whose filesystem allows executing compiled binaries (handles noexec /tmp)."""
    global _CACHED_EXEC_ROOT
    if _CACHED_EXEC_ROOT and os.path.isdir(_CACHED_EXEC_ROOT):
        return _CACHED_EXEC_ROOT

    candidates = []
    env_dir = os.getenv("JUDGE_WORK_DIR")
    if env_dir:
        candidates.append(env_dir)
    candidates.extend([
        "/tmp/noka_judge_runs",
        "/var/tmp/noka_judge_runs",
        os.path.join(os.getcwd(), ".noka_judge_runs"),
        os.path.expanduser("~/.cache/noka_judge_runs"),
    ])
    for cand in candidates:
        if _dir_supports_exec(cand):
            _CACHED_EXEC_ROOT = cand
            return cand
    fallback = os.path.join(os.getcwd(), ".noka_judge_runs")
    os.makedirs(fallback, exist_ok=True)
    _CACHED_EXEC_ROOT = fallback
    return fallback


def create_exec_temp_dir(prefix: str = "noka_run_") -> tempfile.TemporaryDirectory:
    return tempfile.TemporaryDirectory(prefix=prefix, dir=get_exec_work_root())


@dataclass
class ExecutionResult:
    status: str  # OK, TLE, MLE, RE, OLE, IE
    stdout: str
    stderr: str
    exit_code: int
    time_ms: int
    memory_kb: int
    error_message: str = ""


class SandboxRunner:
    """
    Executes untrusted binaries/scripts in an isolated sandbox.
    - Production (JUDGE_MODE=docker): runs inside dedicated unprivileged Docker container
      with --network none, --read-only, --cap-drop=ALL, --user 65534:65534, CPU/RAM/PIDs limits.
    - Local/CI (JUDGE_MODE=local_posix): runs in isolated temp directory with POSIX rlimits,
      sanitized environment (no secrets/DB vars), strict timeout, and output size cap.
    """

    def __init__(
        self,
        mode: Optional[str] = None,
        sandbox_image: Optional[str] = None,
        max_output_bytes: int = 16 * 1024 * 1024,
    ) -> None:
        self.mode = mode or os.getenv("JUDGE_MODE", "local_posix")
        self.sandbox_image = sandbox_image or os.getenv(
            "JUDGE_SANDBOX_IMAGE", "noka-judge-sandbox:latest"
        )
        self.max_output_bytes = int(
            os.getenv("JUDGE_MAX_OUTPUT_BYTES", str(max_output_bytes))
        )

    def run(
        self,
        cmd: List[str],
        work_dir: str,
        stdin_data: str = "",
        time_limit_ms: int = 1000,
        memory_limit_mb: int = 256,
        args: Optional[List[str]] = None,
    ) -> ExecutionResult:
        full_cmd = list(cmd) + (args or [])
        if self.mode == "docker" and shutil.which("docker"):
            return self._run_docker(
                full_cmd, work_dir, stdin_data, time_limit_ms, memory_limit_mb
            )
        return self._run_local_posix(
            full_cmd, work_dir, stdin_data, time_limit_ms, memory_limit_mb
        )

    def _run_docker(
        self,
        cmd: List[str],
        work_dir: str,
        stdin_data: str,
        time_limit_ms: int,
        memory_limit_mb: int,
    ) -> ExecutionResult:
        container_name = f"noka-sbx-{os.getpid()}-{int(time.time() * 1000000)}"
        mapped_cmd = [
            part.replace(work_dir, "/work") if work_dir in part else part
            for part in cmd
        ]
        docker_cmd = [
            "docker",
            "run",
            "--rm",
            "--name",
            container_name,
            "--network",
            "none",
            "--read-only",
            "--tmpfs",
            "/tmp:rw,noexec,nosuid,size=64m",
            "--user",
            "65534:65534",
            "--cap-drop=ALL",
            "--security-opt=no-new-privileges:true",
            "--cpus=1.0",
            f"--memory={memory_limit_mb}m",
            f"--memory-swap={memory_limit_mb}m",
            "--pids-limit=64",
            "-v",
            f"{work_dir}:/work:ro",
            "-w",
            "/work",
            "-i",
            self.sandbox_image,
        ] + mapped_cmd

        timeout_sec = max(0.5, (time_limit_ms / 1000.0) + 0.35)
        start = time.monotonic()
        try:
            proc = subprocess.run(
                docker_cmd,
                input=stdin_data.encode("utf-8", errors="replace"),
                capture_output=True,
                timeout=timeout_sec,
            )
            elapsed_ms = int((time.monotonic() - start) * 1000)
        except subprocess.TimeoutExpired:
            subprocess.run(
                ["docker", "rm", "-f", container_name],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            return ExecutionResult(
                status="TLE",
                stdout="",
                stderr="",
                exit_code=-1,
                time_ms=time_limit_ms,
                memory_kb=0,
                error_message="Time Limit Exceeded",
            )
        except Exception as exc:
            return ExecutionResult(
                status="IE",
                stdout="",
                stderr=str(exc),
                exit_code=-1,
                time_ms=0,
                memory_kb=0,
                error_message=f"Sandbox internal error: {exc}",
            )

        if len(proc.stdout) > self.max_output_bytes:
            return ExecutionResult(
                status="OLE",
                stdout="",
                stderr="",
                exit_code=proc.returncode,
                time_ms=elapsed_ms,
                memory_kb=0,
                error_message="Output Limit Exceeded",
            )

        if proc.returncode == 137:
            return ExecutionResult(
                status="MLE",
                stdout="",
                stderr=proc.stderr.decode("utf-8", errors="replace")[:1000],
                exit_code=137,
                time_ms=elapsed_ms,
                memory_kb=memory_limit_mb * 1024,
                error_message="Memory Limit Exceeded (OOM killed)",
            )

        if proc.returncode != 0:
            return ExecutionResult(
                status="RE",
                stdout=proc.stdout.decode("utf-8", errors="replace")[:2000],
                stderr=proc.stderr.decode("utf-8", errors="replace")[:2000],
                exit_code=proc.returncode,
                time_ms=elapsed_ms,
                memory_kb=0,
                error_message=f"Runtime Error (exit code {proc.returncode})",
            )

        if elapsed_ms > time_limit_ms:
            return ExecutionResult(
                status="TLE",
                stdout="",
                stderr="",
                exit_code=0,
                time_ms=elapsed_ms,
                memory_kb=0,
                error_message="Time Limit Exceeded",
            )

        return ExecutionResult(
            status="OK",
            stdout=proc.stdout.decode("utf-8", errors="replace"),
            stderr=proc.stderr.decode("utf-8", errors="replace")[:2000],
            exit_code=0,
            time_ms=elapsed_ms,
            memory_kb=0,
        )

    def _run_local_posix(
        self,
        cmd: List[str],
        work_dir: str,
        stdin_data: str,
        time_limit_ms: int,
        memory_limit_mb: int,
    ) -> ExecutionResult:
        safe_env = {
            "PATH": "/usr/local/bin:/usr/bin:/bin",
            "LANG": "C.UTF-8",
            "LC_ALL": "C.UTF-8",
            "PYTHONNOUSERSITE": "1",
        }
        mem_bytes = max(32, memory_limit_mb) * 1024 * 1024
        cpu_sec = max(1, int((time_limit_ms / 1000.0) + 1.5))
        fsize_bytes = max(self.max_output_bytes, 32 * 1024 * 1024)

        def _preexec() -> None:
            os.setsid()
            try:
                resource.setrlimit(resource.RLIMIT_CPU, (cpu_sec, cpu_sec + 1))
            except Exception:
                pass
            try:
                resource.setrlimit(resource.RLIMIT_AS, (mem_bytes, mem_bytes))
            except Exception:
                pass
            try:
                resource.setrlimit(resource.RLIMIT_FSIZE, (fsize_bytes, fsize_bytes))
            except Exception:
                pass

        timeout_sec = max(0.2, (time_limit_ms / 1000.0) + 0.15)
        start = time.monotonic()
        stdout_file = tempfile.TemporaryFile()
        stderr_file = tempfile.TemporaryFile()
        stdin_file = tempfile.TemporaryFile()
        stdin_file.write(stdin_data.encode("utf-8", errors="replace"))
        stdin_file.seek(0)

        proc = None
        try:
            proc = subprocess.Popen(
                cmd,
                cwd=work_dir,
                stdin=stdin_file,
                stdout=stdout_file,
                stderr=stderr_file,
                env=safe_env,
                preexec_fn=_preexec,
            )
            timed_out = False
            peak_kb = 0
            while True:
                pid, status, rusage = os.wait4(proc.pid, os.WNOHANG)
                if pid != 0:
                    peak_kb = int(getattr(rusage, "ru_maxrss", 0))
                    if os.WIFEXITED(status):
                        returncode = os.WEXITSTATUS(status)
                    elif os.WIFSIGNALED(status):
                        returncode = -os.WTERMSIG(status)
                    else:
                        returncode = -1
                    proc.returncode = returncode
                    break
                if (time.monotonic() - start) > timeout_sec:
                    timed_out = True
                    try:
                        os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
                    except Exception:
                        proc.kill()
                    try:
                        os.wait4(proc.pid, 0)
                    except Exception:
                        pass
                    returncode = -9
                    proc.returncode = returncode
                    break
                time.sleep(0.01)

            elapsed_ms = int((time.monotonic() - start) * 1000)
            stdout_file.seek(0)
            raw_stdout = stdout_file.read(self.max_output_bytes + 1)
            stderr_file.seek(0)
            raw_stderr = stderr_file.read(65536)
        except Exception as exc:
            return ExecutionResult(
                status="IE",
                stdout="",
                stderr=str(exc),
                exit_code=-1,
                time_ms=0,
                memory_kb=0,
                error_message=f"Sandbox execution error: {exc}",
            )
        finally:
            stdin_file.close()
            stdout_file.close()
            stderr_file.close()

        stderr_text = raw_stderr.decode("utf-8", errors="replace")

        if timed_out or returncode == -signal.SIGXCPU:
            return ExecutionResult(
                status="TLE",
                stdout="",
                stderr=stderr_text[:1000],
                exit_code=returncode,
                time_ms=time_limit_ms,
                memory_kb=peak_kb,
                error_message="Time Limit Exceeded",
            )

        if len(raw_stdout) > self.max_output_bytes or returncode == -signal.SIGXFSZ:
            return ExecutionResult(
                status="OLE",
                stdout="",
                stderr=stderr_text[:1000],
                exit_code=returncode,
                time_ms=elapsed_ms,
                memory_kb=peak_kb,
                error_message="Output Limit Exceeded",
            )

        mle_indicators = ("MemoryError", "bad_alloc", "Cannot allocate memory")
        if (
            peak_kb > memory_limit_mb * 1024
            or (returncode != 0 and any(tok in stderr_text for tok in mle_indicators))
            or returncode == -signal.SIGKILL
        ):
            return ExecutionResult(
                status="MLE",
                stdout="",
                stderr=stderr_text[:1000],
                exit_code=returncode,
                time_ms=elapsed_ms,
                memory_kb=max(peak_kb, memory_limit_mb * 1024),
                error_message="Memory Limit Exceeded",
            )

        if returncode != 0:
            return ExecutionResult(
                status="RE",
                stdout=raw_stdout.decode("utf-8", errors="replace")[:2000],
                stderr=stderr_text[:2000],
                exit_code=returncode,
                time_ms=elapsed_ms,
                memory_kb=peak_kb,
                error_message=f"Runtime Error (exit code {returncode})",
            )

        if elapsed_ms > time_limit_ms:
            return ExecutionResult(
                status="TLE",
                stdout="",
                stderr="",
                exit_code=0,
                time_ms=elapsed_ms,
                memory_kb=peak_kb,
                error_message="Time Limit Exceeded",
            )

        return ExecutionResult(
            status="OK",
            stdout=raw_stdout.decode("utf-8", errors="replace"),
            stderr=stderr_text[:2000],
            exit_code=0,
            time_ms=elapsed_ms,
            memory_kb=peak_kb,
        )
