"""Built-in Testcase Generator Templates (Mode C) and Advanced Randomization Profiles."""
import random
import string
from typing import Any, Callable, Dict, List

BUILTIN_TEMPLATES: Dict[str, Dict[str, Any]] = {
    "random_integer": {
        "name": "Random Integer",
        "description": "Sinh 1 hoặc nhiều số nguyên (ví dụ: A B hoặc N).",
        "default_params": {"count": 2, "min_val": -1000000, "max_val": 1000000},
    },
    "random_array": {
        "name": "Random Array",
        "description": "Dòng 1: N. Dòng 2: N số nguyên trong [min_val, max_val].",
        "default_params": {"n_min": 5, "n_max": 100, "min_val": -1000, "max_val": 1000},
    },
    "increasing_array": {
        "name": "Increasing Array",
        "description": "Mảng tăng dần (có thể tăng nghiêm ngặt hoặc không giảm).",
        "default_params": {"n_min": 5, "n_max": 100, "min_val": 1, "max_val": 1000, "strict": False},
    },
    "decreasing_array": {
        "name": "Decreasing Array",
        "description": "Mảng giảm dần kích thước N.",
        "default_params": {"n_min": 5, "n_max": 100, "min_val": 1, "max_val": 1000},
    },
    "permutation": {
        "name": "Permutation",
        "description": "Hoán vị của 1..N.",
        "default_params": {"n_min": 5, "n_max": 100},
    },
    "random_string": {
        "name": "Random String",
        "description": "Chuỗi ký tự ngẫu nhiên độ dài N theo bảng chữ cái cấu hình.",
        "default_params": {"n_min": 5, "n_max": 100, "alphabet": "lowercase", "include_n": True},
    },
    "random_graph": {
        "name": "Random Graph",
        "description": "Đồ thị vô hướng/có hướng N đỉnh, M cạnh (hỗ trợ sparse/dense/weighted).",
        "default_params": {"n_min": 4, "n_max": 50, "m_min": 4, "m_max": 100, "weighted": False, "min_val": 1, "max_val": 100},
    },
    "tree": {
        "name": "Tree",
        "description": "Cây N đỉnh (random, chain, star, balanced).",
        "default_params": {"n_min": 5, "n_max": 100, "tree_type": "random", "weighted": False, "min_val": 1, "max_val": 100},
    },
    "random_matrix": {
        "name": "Random Matrix",
        "description": "Ma trận N x M các số nguyên.",
        "default_params": {"n_min": 2, "n_max": 20, "m_min": 2, "m_max": 20, "min_val": 0, "max_val": 100},
    },
    "random_queries": {
        "name": "Random Queries",
        "description": "Mảng N phần tử kèm Q truy vấn đoạn [L, R].",
        "default_params": {"n_min": 5, "n_max": 100, "m_min": 5, "m_max": 100, "min_val": 1, "max_val": 1000},
    },
    "edge_cases": {
        "name": "Edge Cases",
        "description": "Tập hợp các trường hợp biên (N=1, toàn số 0, toàn min/max, lặp giá trị).",
        "default_params": {"n_min": 1, "n_max": 100, "min_val": -1000, "max_val": 1000},
    },
}

RANDOMIZATION_PROFILES: List[str] = [
    "min_constraints",
    "max_constraints",
    "random",
    "boundary",
    "special",
    "duplicates",
    "sorted",
    "reverse_sorted",
    "sparse_graph",
    "dense_graph",
    "chain_tree",
    "star_tree",
    "balanced_tree",
    "small_input",
    "large_input",
]


def _pick_n(rng: random.Random, params: Dict[str, Any], profile: str, key_min: str = "n_min", key_max: str = "n_max") -> int:
    lo = max(1, int(params.get(key_min, 1)))
    hi = max(lo, int(params.get(key_max, max(lo, 10))))
    if profile in ("min_constraints", "small_input"):
        return lo
    if profile in ("max_constraints", "large_input"):
        return hi
    if profile == "boundary":
        return rng.choice([lo, min(lo + 1, hi), max(lo, hi - 1), hi])
    return rng.randint(lo, hi)


def _gen_values(rng: random.Random, n: int, lo: int, hi: int, profile: str) -> List[int]:
    if lo > hi:
        lo, hi = hi, lo
    if profile == "min_constraints":
        return [lo] * n
    if profile == "max_constraints":
        return [hi] * n
    if profile == "duplicates":
        pool = [rng.randint(lo, hi) for _ in range(max(1, min(3, hi - lo + 1)))]
        return [rng.choice(pool) for _ in range(n)]
    if profile == "boundary":
        choices = list({lo, hi, 0 if lo <= 0 <= hi else lo, (lo + hi) // 2})
        return [rng.choice(choices) for _ in range(n)]
    if profile == "special":
        mid = (lo + hi) // 2
        return [lo if i % 2 == 0 else hi if i % 3 == 0 else mid for i in range(n)]
    vals = [rng.randint(lo, hi) for _ in range(n)]
    if profile == "sorted":
        vals.sort()
    elif profile == "reverse_sorted":
        vals.sort(reverse=True)
    return vals


def generate_template_input(
    template_id: str,
    params: Dict[str, Any],
    profile: str,
    rng: random.Random,
) -> str:
    if template_id not in BUILTIN_TEMPLATES:
        raise ValueError(f"Unknown template: {template_id}")

    merged = {**BUILTIN_TEMPLATES[template_id]["default_params"], **(params or {})}
    lo = int(merged.get("min_val", -1000))
    hi = int(merged.get("max_val", 1000))

    if template_id == "random_integer":
        count = max(1, int(merged.get("count", 2)))
        vals = _gen_values(rng, count, lo, hi, profile)
        return " ".join(map(str, vals)) + "\n"

    if template_id == "random_array":
        n = _pick_n(rng, merged, profile)
        vals = _gen_values(rng, n, lo, hi, profile)
        return f"{n}\n" + " ".join(map(str, vals)) + "\n"

    if template_id == "increasing_array":
        n = _pick_n(rng, merged, profile)
        vals = sorted(_gen_values(rng, n, lo, hi, profile))
        if merged.get("strict"):
            for i in range(1, len(vals)):
                if vals[i] <= vals[i - 1]:
                    vals[i] = vals[i - 1] + 1
        return f"{n}\n" + " ".join(map(str, vals)) + "\n"

    if template_id == "decreasing_array":
        n = _pick_n(rng, merged, profile)
        vals = sorted(_gen_values(rng, n, lo, hi, profile), reverse=True)
        return f"{n}\n" + " ".join(map(str, vals)) + "\n"

    if template_id == "permutation":
        n = _pick_n(rng, merged, profile)
        arr = list(range(1, n + 1))
        if profile == "sorted":
            pass
        elif profile == "reverse_sorted":
            arr.reverse()
        else:
            rng.shuffle(arr)
        return f"{n}\n" + " ".join(map(str, arr)) + "\n"

    if template_id == "random_string":
        n = _pick_n(rng, merged, profile)
        alpha_key = merged.get("alphabet", "lowercase")
        alphabets = {
            "lowercase": string.ascii_lowercase,
            "uppercase": string.ascii_uppercase,
            "letters": string.ascii_letters,
            "alphanumeric": string.ascii_letters + string.digits,
            "binary": "01",
            "digits": string.digits,
        }
        chars = alphabets.get(alpha_key, alpha_key if alpha_key else string.ascii_lowercase)
        if profile == "duplicates":
            s = rng.choice(chars) * n
        elif profile == "special":
            half = "".join(rng.choice(chars) for _ in range((n + 1) // 2))
            s = (half + half[::-1])[:n]  # Palindrome edge case
        else:
            s = "".join(rng.choice(chars) for _ in range(n))
        return f"{n}\n{s}\n" if merged.get("include_n", True) else f"{s}\n"

    if template_id == "tree":
        n = _pick_n(rng, merged, profile)
        tree_type = merged.get("tree_type", "random")
        if profile == "chain_tree":
            tree_type = "chain"
        elif profile == "star_tree":
            tree_type = "star"
        elif profile == "balanced_tree":
            tree_type = "balanced"
        edges = []
        for v in range(2, n + 1):
            if tree_type == "chain":
                u = v - 1
            elif tree_type == "star":
                u = 1
            elif tree_type == "balanced":
                u = v // 2
            else:
                u = rng.randint(1, v - 1)
            edges.append((u, v))
        weighted = bool(merged.get("weighted", False))
        lines = [str(n)]
        for u, v in edges:
            if weighted:
                w = rng.randint(lo, hi)
                lines.append(f"{u} {v} {w}")
            else:
                lines.append(f"{u} {v}")
        return "\n".join(lines) + "\n"

    if template_id == "random_graph":
        n = max(2, _pick_n(rng, merged, profile))
        max_edges = n * (n - 1) // 2
        if profile == "sparse_graph":
            m = min(max_edges, max(n - 1, int(n * 1.2)))
        elif profile == "dense_graph":
            m = min(max_edges, max(n - 1, int(max_edges * 0.75)))
        else:
            m_lo = max(0, int(merged.get("m_min", n - 1)))
            m_hi = min(max_edges, max(m_lo, int(merged.get("m_max", min(max_edges, n * 2)))))
            m = rng.randint(min(m_lo, max_edges), m_hi) if max_edges > 0 else 0
        edge_set = set()
        # Start with spanning tree if m >= n - 1 for connectivity
        if m >= n - 1:
            for v in range(2, n + 1):
                u = rng.randint(1, v - 1)
                edge_set.add((min(u, v), max(u, v)))
        attempts = 0
        while len(edge_set) < m and attempts < m * 10 + 100:
            attempts += 1
            u = rng.randint(1, n)
            v = rng.randint(1, n)
            if u != v:
                edge_set.add((min(u, v), max(u, v)))
        edges = list(edge_set)
        rng.shuffle(edges)
        weighted = bool(merged.get("weighted", False))
        lines = [f"{n} {len(edges)}"]
        for u, v in edges:
            if weighted:
                lines.append(f"{u} {v} {rng.randint(lo, hi)}")
            else:
                lines.append(f"{u} {v}")
        return "\n".join(lines) + "\n"

    if template_id == "random_matrix":
        n = _pick_n(rng, merged, profile, "n_min", "n_max")
        m = _pick_n(rng, merged, profile, "m_min", "m_max")
        lines = [f"{n} {m}"]
        for _ in range(n):
            row = _gen_values(rng, m, lo, hi, profile)
            lines.append(" ".join(map(str, row)))
        return "\n".join(lines) + "\n"

    if template_id == "random_queries":
        n = _pick_n(rng, merged, profile, "n_min", "n_max")
        q = _pick_n(rng, merged, profile, "m_min", "m_max")
        arr = _gen_values(rng, n, lo, hi, profile)
        lines = [f"{n} {q}", " ".join(map(str, arr))]
        for _ in range(q):
            l = rng.randint(1, n)
            r = rng.randint(l, n)
            lines.append(f"{l} {r}")
        return "\n".join(lines) + "\n"

    # edge_cases
    n = _pick_n(rng, merged, profile if profile != "random" else "boundary")
    vals = _gen_values(rng, n, lo, hi, "boundary" if profile == "random" else profile)
    return f"{n}\n" + " ".join(map(str, vals)) + "\n"


def expand_profile_plan(
    num_tests: int,
    distribution: Dict[str, int] | None = None,
) -> List[str]:
    """Expand customizable profile distribution into an ordered list of length num_tests."""
    plan: List[str] = []
    if distribution:
        for prof, count in distribution.items():
            if prof in RANDOMIZATION_PROFILES and count > 0:
                plan.extend([prof] * int(count))
    if len(plan) > num_tests:
        return plan[:num_tests]
    if len(plan) < num_tests:
        defaults = ["min_constraints", "boundary", "duplicates", "sorted", "reverse_sorted", "random", "max_constraints"]
        idx = 0
        while len(plan) < num_tests:
            plan.append(defaults[idx % len(defaults)])
            idx += 1
    return plan
