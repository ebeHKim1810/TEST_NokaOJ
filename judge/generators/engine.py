"""
Advanced Testcase Generator Engine (Independent Module).
Supports:
- Mode A: Custom Generator + Reference Solution (AC) in sandbox
- Mode B: Structured Constraints + Input Validator + Reference Solution (AC)
- Mode C: Built-in Templates + Advanced Randomization + Reference Solution (AC)
"""
import random
import tempfile
import time
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional

from judge.compilers.compiler import CompilerManager
from judge.generators.templates import expand_profile_plan, generate_template_input
from judge.generators.validator import InputValidator, generate_structured_input
from judge.sandbox.runner import SandboxRunner, create_exec_temp_dir


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

        with create_exec_temp_dir(prefix="noka_gen_") as work_dir:
            # 1. Compile Reference Solution (AC)
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

            # 2. If Mode A, compile Custom Generator
            gen_comp = None
            if mode == "custom_generator":
                if not generator_code or not generator_language:
                    return GenerationReport(
                        mode=mode,
                        requested_count=num_tests,
                        success_count=0,
                        failed_count=num_tests,
                        duration_ms=int((time.monotonic() - start_total) * 1000),
                        seed=used_seed,
                        generator_compile_error="Mode A requires both generator_code and generator_language.",
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

            profiles = expand_profile_plan(num_tests, profile_distribution)
            items: List[GeneratedTestItem] = []
            success_count = 0
            failed_count = 0

            effective_ref_tl = int(time_limit_ms * ref_comp.language.time_multiplier)
            effective_ref_ml = memory_limit_mb + ref_comp.language.memory_bonus_mb

            for idx in range(1, num_tests + 1):
                test_name = f"{idx:02d}"
                profile = profiles[idx - 1]
                test_seed = rng.randint(1, 2_000_000_000)

                # Step A: Produce input
                gen_input = ""
                gen_err = ""
                if mode == "custom_generator":
                    assert gen_comp is not None
                    gen_res = self.sandbox.run(
                        gen_comp.run_cmd,
                        work_dir=work_dir,
                        stdin_data=f"{idx} {test_seed}\n",
                        args=[str(idx), str(test_seed)],
                        time_limit_ms=int(time_limit_ms * gen_comp.language.time_multiplier),
                        memory_limit_mb=memory_limit_mb + gen_comp.language.memory_bonus_mb,
                    )
                    if gen_res.status != "OK":
                        gen_err = f"Generator {gen_res.status}: {gen_res.error_message or gen_res.stderr[:250]}"
                    elif not gen_res.stdout.strip():
                        gen_err = "Generator produced empty input."
                    else:
                        gen_input = gen_res.stdout

                elif mode == "constraints":
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

                # Step B: Execute Reference Solution (AC) in sandbox
                ref_res = self.sandbox.run(
                    ref_comp.run_cmd,
                    work_dir=work_dir,
                    stdin_data=gen_input,
                    time_limit_ms=effective_ref_tl,
                    memory_limit_mb=effective_ref_ml,
                )
                if ref_res.status != "OK":
                    failed_count += 1
                    items.append(
                        GeneratedTestItem(
                            index=idx,
                            name=test_name,
                            profile=profile,
                            status="FAILED",
                            input_data=gen_input[:2000],
                            input_size_bytes=len(gen_input.encode("utf-8")),
                            execution_time_ms=ref_res.time_ms,
                            memory_kb=ref_res.memory_kb,
                            error=f"Reference Solution {ref_res.status}: {ref_res.error_message or ref_res.stderr[:250]}",
                        )
                    )
                    continue

                if not allow_empty_output and not ref_res.stdout.strip():
                    failed_count += 1
                    items.append(
                        GeneratedTestItem(
                            index=idx,
                            name=test_name,
                            profile=profile,
                            status="FAILED",
                            input_data=gen_input[:2000],
                            input_size_bytes=len(gen_input.encode("utf-8")),
                            execution_time_ms=ref_res.time_ms,
                            memory_kb=ref_res.memory_kb,
                            error="Reference Solution produced empty output.",
                        )
                    )
                    continue

                success_count += 1
                items.append(
                    GeneratedTestItem(
                        index=idx,
                        name=test_name,
                        profile=profile,
                        status="SUCCESS",
                        input_data=gen_input,
                        expected_output=ref_res.stdout,
                        input_size_bytes=len(gen_input.encode("utf-8")),
                        output_size_bytes=len(ref_res.stdout.encode("utf-8")),
                        execution_time_ms=ref_res.time_ms,
                        memory_kb=ref_res.memory_kb,
                    )
                )

        return GenerationReport(
            mode=mode,
            requested_count=num_tests,
            success_count=success_count,
            failed_count=failed_count,
            duration_ms=int((time.monotonic() - start_total) * 1000),
            seed=used_seed,
            items=items,
        )
