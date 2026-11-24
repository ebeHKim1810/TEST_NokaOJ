"""Mode B Structured Constraints Input Generator & Validator."""
import random
import string
from typing import Any, Dict, List, Tuple


class InputValidator:
    """Validates generated input against structured Mode B field constraints."""

    def validate(self, input_text: str, schema: Dict[str, Any]) -> Tuple[bool, str]:
        fields = schema.get("fields", [])
        if not fields:
            return True, "No schema constraints specified."
        tokens = input_text.split()
        pos = 0
        env: Dict[str, int] = {}

        for field in fields:
            ftype = field.get("type", "int")
            name = field.get("name", f"field_{pos}")
            if ftype == "int":
                if pos >= len(tokens):
                    return False, f"Missing integer field '{name}'."
                try:
                    val = int(tokens[pos])
                except ValueError:
                    return False, f"Field '{name}' expected integer, got '{tokens[pos]}'."
                lo = field.get("min")
                hi = field.get("max")
                if lo is not None and val < int(lo):
                    return False, f"Field '{name}'={val} < min {lo}."
                if hi is not None and val > int(hi):
                    return False, f"Field '{name}'={val} > max {hi}."
                env[name] = val
                pos += 1
            elif ftype == "array":
                length_ref = field.get("length_ref")
                length = env.get(length_ref, int(field.get("length", 1))) if length_ref else int(field.get("length", 1))
                if pos + length > len(tokens):
                    return False, f"Array '{name}' expected {length} elements."
                lo = field.get("min")
                hi = field.get("max")
                arr = []
                for i in range(length):
                    try:
                        v = int(tokens[pos + i])
                    except ValueError:
                        return False, f"Array '{name}[{i}]' is not an integer."
                    if lo is not None and v < int(lo):
                        return False, f"Array '{name}[{i}]'={v} < min {lo}."
                    if hi is not None and v > int(hi):
                        return False, f"Array '{name}[{i}]'={v} > max {hi}."
                    arr.append(v)
                if field.get("unique") and len(set(arr)) != len(arr):
                    return False, f"Array '{name}' contains duplicate values."
                pos += length
            elif ftype == "string":
                if pos >= len(tokens):
                    return False, f"Missing string field '{name}'."
                s = tokens[pos]
                min_len = field.get("min_len", 1)
                max_len = field.get("max_len", 100000)
                if not (int(min_len) <= len(s) <= int(max_len)):
                    return False, f"String '{name}' length {len(s)} out of [{min_len}, {max_len}]."
                pos += 1
        return True, "Valid."


def generate_structured_input(
    schema: Dict[str, Any], profile: str, rng: random.Random
) -> str:
    """Generates Mode B input from structured field definitions."""
    fields: List[Dict[str, Any]] = schema.get("fields", [])
    if not fields:
        raise ValueError("Mode B requires at least one field in constraint_schema.fields")

    env: Dict[str, int] = {}
    lines: List[str] = []
    inline_buf: List[str] = []

    def _flush_inline() -> None:
        if inline_buf:
            lines.append(" ".join(inline_buf))
            inline_buf.clear()

    for field in fields:
        ftype = field.get("type", "int")
        name = field.get("name", "x")
        newline = bool(field.get("newline", True))

        if ftype == "int":
            lo = int(field.get("min", 1))
            hi = int(field.get("max", 100))
            if profile in ("min_constraints", "small_input"):
                val = lo
            elif profile in ("max_constraints", "large_input"):
                val = hi
            elif profile == "boundary":
                val = rng.choice([lo, hi, (lo + hi) // 2])
            else:
                val = rng.randint(lo, hi)
            env[name] = val
            inline_buf.append(str(val))
            if newline:
                _flush_inline()

        elif ftype == "array":
            _flush_inline()
            length_ref = field.get("length_ref")
            length = max(1, env.get(length_ref, int(field.get("length", 5)))) if length_ref else max(1, int(field.get("length", 5)))
            lo = int(field.get("min", 0))
            hi = int(field.get("max", 100))
            unique = bool(field.get("unique", False))
            if unique and (hi - lo + 1) >= length:
                arr = rng.sample(range(lo, hi + 1), length)
            else:
                if profile == "min_constraints":
                    arr = [lo] * length
                elif profile == "max_constraints":
                    arr = [hi] * length
                elif profile == "duplicates":
                    v = rng.randint(lo, hi)
                    arr = [v] * length
                else:
                    arr = [rng.randint(lo, hi) for _ in range(length)]
            if profile == "sorted":
                arr.sort()
            elif profile == "reverse_sorted":
                arr.sort(reverse=True)
            lines.append(" ".join(map(str, arr)))

        elif ftype == "string":
            _flush_inline()
            length_ref = field.get("length_ref")
            if length_ref and length_ref in env:
                length = max(1, env[length_ref])
            else:
                min_l = max(1, int(field.get("min_len", 5)))
                max_l = max(min_l, int(field.get("max_len", 20)))
                length = min_l if profile == "min_constraints" else max_l if profile == "max_constraints" else rng.randint(min_l, max_l)
            alphabet = field.get("alphabet", string.ascii_lowercase)
            s = "".join(rng.choice(alphabet) for _ in range(length))
            lines.append(s)

    _flush_inline()
    return "\n".join(lines) + "\n"
