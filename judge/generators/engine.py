"""
Advanced Testcase Generator Engine (Independent Module).
Supports:
- Mode A: Batch Loop Custom Generator (runs ONCE with argv[1]=T, argv[2]=seed, writes *.in files)
          + Reference Solution (AC) compiled once and run per .in file in sandbox
- Mode B: Structured Constraints + Input Validator + Reference Solution (AC)
- Mode C: Built-in Templates + Advanced Randomization + Reference Solution (AC)
"""
import os
import random
import re
import shutil
import time
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from judge.compilers.compiler import CompilerManager
from judge.generators.templates import expand_profile_plan, generate_template_input
from judge.generators.validator import InputValidator, generate_structured_input
from judge.sandbox.runner import SandboxRunner, create_exec_temp_dir

MAX_BATCH_INPUT_FILES = 200
MAX_SINGLE_INPUT_BYTES = 16 * 1024 * 1024  # 16 MB per generated .in file


def natural_sort_key(text: str) -> List[Any]:
    """Natural sort key so test_1.in, test_2.in, ..., test_10.in sort numerically."""
    return [int(tok) if tok.isdigit() else tok.lower() for tok in re.split(r"(\d+)", text)]


def discover_generated_input_files(work_dir: str) -> List[Tuple[str, str]]:
    """
    Scans `work_dir` for all `.in` files produced by the Mode A Batch Generator.
    Returns list of (display_stem, full_path) sorted in natural numeric order.
    """
    found: List[Tuple[str, str, str]] = []  # (relative_path, stem, full_path)
    for root, dirs, files in os.walk(work_dir):
        # Ignore hidden directories
        dirs[:] = [d for d in dirs if not d.startswith(".")]
        for fname in files:
            if fname.startswith(".") or not fname.lower().endswith(".in"):
                continue
            full_path = os.path.join(root, fname)
            if not os.path.isfile(full_path):
                continue
            rel = os.path.relpath(full_path, work_dir).replace("\\", "/")
            stem = os.path.splitext(rel)[0].replace("/", "_") if "/" in rel else os.path.splitext(fname)[0]
            found.append((rel, stem, full_path))

    found.sort(key=lambda entry: natural_sort_key(entry[0]))
    return [(stem, full_path) for _, stem, full_path in found]


@dataclass
class GeneratedTestItem:
    index: int
    name: str
    profile: str
    status: str  # SUCCESS, FAILED
    input_data: str = ""
    expected_output: str = ""
    input_size_bytes: int = 0
    output_size_bytes: int = 0
    execution_time_ms: int = 0
    memory_kb: int = 0
    error: str = ""


@dataclass
class GenerationReport:
    mode: str
    requested_count: int
    success_count: int
    failed_count: int
    duration_ms: int
    seed: int
    reference_compile_error: str = ""
    generator_compile_error: str = ""
    items: List[GeneratedTestItem] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class TestcaseGeneratorEngine:
    def __init__(
        self,
        sandbox: Optional[SandboxRunner] = None,
        compiler: Optional[CompilerManager] = None,
    ) -> None:
        self.sandbox = sandbox or SandboxRunner()
        self.compiler = compiler or CompilerManager()
        self.validator = InputValidator()

    def _run_reference_on_input(
        self,
        idx: int,
        test_name: str,
        profile: str,
        gen_input: str,
        ref_run_cmd: List[str],
        work_dir: str,
        effective_ref_tl: int,
        effective_ref_ml: int,
        allow_empty_output: bool,
    ) -> GeneratedTestItem:
        input_bytes = len(gen_input.encode("utf-8"))
        ref_res = self.sandbox.run(
            ref_run_cmd,
            work_dir=work_dir,
            stdin_data=gen_input,
            time_limit_ms=effective_ref_tl,
            memory_limit_mb=effective_ref_ml,
        )
        if ref_res.status != "OK":
            detail = ref_res.error_message or ref_res.stderr[:250]
            return GeneratedTestItem(
                index=idx,
                name=test_name,
                profile=profile,
                status="FAILED",
                input_data=gen_input[:2000],
                input_size_bytes=input_bytes,
                execution_time_ms=ref_res.time_ms,
                memory_kb=ref_res.memory_kb,
                error=f"Test #{idx} ({test_name}) — Reference Solution {ref_res.status}: {detail}",
            )

        if not allow_empty_output and not ref_res.stdout.strip():
            return GeneratedTestItem(
                index=idx,
                name=test_name,
                profile=profile,
                status="FAILED",
                input_data=gen_input[:2000],
                input_size_bytes=input_bytes,
                execution_time_ms=ref_res.time_ms,
                memory_kb=ref_res.memory_kb,
                error=f"Test #{idx} ({test_name}) — Reference Solution produced empty output.",
            )

        return GeneratedTestItem(
            index=idx,
            name=test_name,
            profile=profile,
            status="SUCCESS",
            input_data=gen_input,
            expected_output=ref_res.stdout,
            input_size_bytes=input_bytes,
            output_size_bytes=len(ref_res.stdout.encode("utf-8")),
            execution_time_ms=ref_res.time_ms,
            memory_kb=ref_res.memory_kb,
        )

    def generate(
        self,
        mode: str,
        reference_code: str,
        reference_language: str,
        num_tests: int,
        time_limit_ms: int = 2000,
        memory_limit_mb: int = 256,
        seed: Optional[int] = None,
        generator_code: Optional[str] = None,
        generator_language: Optional[str] = None,
        constraint_schema: Optional[Dict[str, Any]] = None,
        template_id: Optional[str] = None,
        template_params: Optional[Dict[str, Any]] = None,
        profile_distribution: Optional[Dict[str, int]] = None,
        allow_empty_output: bool = False,
    ) -> GenerationReport:
        start_total = time.monotonic()
        used_seed = seed if seed is not None else random.randint(1, 2_000_000_000)
        rng = random.Random(used_seed)
        num_tests = max(1, min(int(num_tests), 100))

        tmp_ctx = create_exec_temp_dir(prefix="noka_gen_")
        work_dir = tmp_ctx.name
        try:
            # 1. Compile Reference Solution (AC) ONCE
            ref_comp = self.compiler.compile_source(
                reference_code, reference_language, work_dir, stem="ref_solution"
            )
            if not ref_comp.success:
                return GenerationReport(
                    mode=mode,
                    requested_count=num_tests,
                    success_count=0,
                    failed_count=num_tests,
                    duration_ms=int((time.monotonic() - start_total) * 1000),
                    seed=used_seed,
                    reference_compile_error=ref_comp.output,
                    items=[],
                )

            effective_ref_tl = int(time_limit_ms * ref_comp.language.time_multiplier)
            effective_ref_ml = memory_limit_mb + ref_comp.language.memory_bonus_mb

            # 2. Mode A: Batch Loop Custom Generator (compile once, run ONCE, scan *.in files)
            if mode == "custom_generator":
                if not generator_code or not generator_language:
                    return GenerationReport(
                        mode=mode,
                        requested_count=num_tests,
                        success_count=0,
                        failed_count=num_tests,
                        duration_ms=int((time.monotonic() - start_total) * 1000),
                        seed=used_seed,
                        generator_compile_error="Mode A yêu cầu nhập cả mã nguồn Generator và ngôn ngữ tương ứng.",
                        items=[],
                    )

                gen_comp = self.compiler.compile_source(
                    generator_code, generator_language, work_dir, stem="custom_gen"
                )
                if not gen_comp.success:
                    return GenerationReport(
                        mode=mode,
                        requested_count=num_tests,
                        success_count=0,
                        failed_count=num_tests,
                        duration_ms=int((time.monotonic() - start_total) * 1000),
                        seed=used_seed,
                        generator_compile_error=gen_comp.output,
                        items=[],
                    )

                # Execute batch generator ONCE in work_dir, passing argv[1]=T, argv[2]=seed
                batch_gen_tl = max(
                    10_000,
                    min(
                        60_000,
                        int(time_limit_ms * gen_comp.language.time_multiplier) + num_tests * 400,
                    ),
                )
                batch_gen_ml = max(256, memory_limit_mb + gen_comp.language.memory_bonus_mb)
                gen_res = self.sandbox.run(
                    gen_comp.run_cmd,
                    work_dir=work_dir,
                    stdin_data=f"{num_tests} {used_seed}\n",
                    args=[str(num_tests), str(used_seed)],
                    time_limit_ms=batch_gen_tl,
                    memory_limit_mb=batch_gen_ml,
                    writable_work_dir=True,
                )
                if gen_res.status != "OK":
                    err_detail = gen_res.error_message or ""
                    stderr_snippet = (gen_res.stderr or "").strip()[:1000]
                    msg = f"Generator gặp lỗi khi thực thi ({gen_res.status}): {err_detail}"
                    if stderr_snippet:
                        msg += f"\n{stderr_snippet}"
                    return GenerationReport(
                        mode=mode,
                        requested_count=num_tests,
                        success_count=0,
                        failed_count=num_tests,
                        duration_ms=int((time.monotonic() - start_total) * 1000),
                        seed=used_seed,
                        generator_compile_error=msg,
                        items=[],
                    )

                in_files = discover_generated_input_files(work_dir)
                if not in_files:
                    stderr_snippet = (gen_res.stderr or "").strip()[:500]
                    msg = (
                        "Generator đã chạy xong (exit code 0) nhưng không tìm thấy file .in nào "
                        "trong thư mục làm việc. Hãy chắc chắn code của bạn lặp từ 1 đến T (argv[1]) "
                        "và ghi ra các file như test_01.in, test_02.in, ..."
                    )
                    if stderr_snippet:
                        msg += f"\nStderr: {stderr_snippet}"
                    return GenerationReport(
                        mode=mode,
                        requested_count=num_tests,
                        success_count=0,
                        failed_count=num_tests,
                        duration_ms=int((time.monotonic() - start_total) * 1000),
                        seed=used_seed,
                        generator_compile_error=msg,
                        items=[],
                    )

                if len(in_files) > MAX_BATCH_INPUT_FILES:
                    in_files = in_files[:MAX_BATCH_INPUT_FILES]

                items: List[GeneratedTestItem] = []
                success_count = 0
                failed_count = 0

                for idx, (stem, full_path) in enumerate(in_files, start=1):
                    test_name = stem or f"test_{idx:02d}"
                    fsize = os.path.getsize(full_path)
                    if fsize > MAX_SINGLE_INPUT_BYTES:
                        failed_count += 1
                        items.append(
                            GeneratedTestItem(
                                index=idx,
                                name=test_name,
                                profile="custom_batch",
                                status="FAILED",
                                input_size_bytes=fsize,
                                error=f"Test #{idx} ({test_name}.in) vượt quá giới hạn 16MB/file.",
                            )
                        )
                        continue

                    with open(full_path, "r", encoding="utf-8", errors="replace") as f:
                        gen_input = f.read()

                    if not gen_input.strip():
                        failed_count += 1
                        items.append(
                            GeneratedTestItem(
                                index=idx,
                                name=test_name,
                                profile="custom_batch",
                                status="FAILED",
                                error=f"Test #{idx} ({test_name}.in) bị trống (không có dữ liệu input).",
                            )
                        )
                        continue

                    item = self._run_reference_on_input(
                        idx=idx,
                        test_name=test_name,
                        profile="custom_batch",
                        gen_input=gen_input,
                        ref_run_cmd=ref_comp.run_cmd,
                        work_dir=work_dir,
                        effective_ref_tl=effective_ref_tl,
                        effective_ref_ml=effective_ref_ml,
                        allow_empty_output=allow_empty_output,
                    )
                    if item.status == "SUCCESS":
                        success_count += 1
                    else:
                        failed_count += 1
                    items.append(item)

                return GenerationReport(
                    mode=mode,
                    requested_count=len(in_files),
                    success_count=success_count,
                    failed_count=failed_count,
                    duration_ms=int((time.monotonic() - start_total) * 1000),
                    seed=used_seed,
                    items=items,
                )

            # 3. Mode B (Constraints Schema) & Mode C (Built-in Templates)
            profiles = expand_profile_plan(num_tests, profile_distribution)
            items = []
            success_count = 0
            failed_count = 0

            for idx in range(1, num_tests + 1):
                test_name = f"{idx:02d}"
                profile = profiles[idx - 1]
                test_seed = rng.randint(1, 2_000_000_000)

                gen_input = ""
                gen_err = ""
                if mode == "constraints":
                    try:
                        test_rng = random.Random(test_seed)
                        gen_input = generate_structured_input(
                            constraint_schema or {}, profile, test_rng
                        )
                        valid, vmsg = self.validator.validate(
                            gen_input, constraint_schema or {}
                        )
                        if not valid:
                            gen_err = f"Validator rejected input: {vmsg}"
                    except Exception as exc:
                        gen_err = f"Constraint generation error: {exc}"
                elif mode == "builtin_template":
                    try:
                        test_rng = random.Random(test_seed)
                        gen_input = generate_template_input(
                            template_id or "random_array",
                            template_params or {},
                            profile,
                            test_rng,
                        )
                    except Exception as exc:
                        gen_err = f"Template generation error: {exc}"
                else:
                    gen_err = f"Unsupported generator mode: {mode}"

                if gen_err:
                    failed_count += 1
                    items.append(
                        GeneratedTestItem(
                            index=idx,
                            name=test_name,
                            profile=profile,
                            status="FAILED",
                            error=gen_err,
                        )
                    )
                    continue

                item = self._run_reference_on_input(
                    idx=idx,
                    test_name=test_name,
                    profile=profile,
                    gen_input=gen_input,
                    ref_run_cmd=ref_comp.run_cmd,
                    work_dir=work_dir,
                    effective_ref_tl=effective_ref_tl,
                    effective_ref_ml=effective_ref_ml,
                    allow_empty_output=allow_empty_output,
                )
                if item.status == "SUCCESS":
                    success_count += 1
                else:
                    failed_count += 1
                items.append(item)

            return GenerationReport(
                mode=mode,
                requested_count=num_tests,
                success_count=success_count,
                failed_count=failed_count,
                duration_ms=int((time.monotonic() - start_total) * 1000),
                seed=used_seed,
                items=items,
            )
        finally:
            try:
                tmp_ctx.cleanup()
            except Exception:
                pass
            if os.path.isdir(work_dir):
                shutil.rmtree(work_dir, ignore_errors=True)
