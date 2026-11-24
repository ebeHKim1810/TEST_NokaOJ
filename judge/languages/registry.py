"""Extensible programming language registry for Noka JUDGE."""
from dataclasses import dataclass
from typing import Dict, List, Optional


@dataclass(frozen=True)
class LanguageSpec:
    id: str
    name: str
    extension: str
    monaco_language: str
    compile_cmd: Optional[List[str]]  # None or syntax check for interpreted languages
    run_cmd: List[str]
    is_compiled: bool
    time_multiplier: float = 1.0
    memory_bonus_mb: int = 0
    default_template: str = ""


LANGUAGES: Dict[str, LanguageSpec] = {
    "cpp17": LanguageSpec(
        id="cpp17",
        name="C++17 (GCC)",
        extension=".cpp",
        monaco_language="cpp",
        compile_cmd=["g++", "-O2", "-std=c++17", "-pipe", "-s", "{source}", "-o", "{binary}"],
        run_cmd=["{binary}"],
        is_compiled=True,
        time_multiplier=1.0,
        memory_bonus_mb=0,
        default_template=(
            "#include <bits/stdc++.h>\n"
            "using namespace std;\n\n"
            "int main() {\n"
            "    ios::sync_with_stdio(false);\n"
            "    cin.tie(nullptr);\n\n"
            "    return 0;\n"
            "}\n"
        ),
    ),
    "cpp20": LanguageSpec(
        id="cpp20",
        name="C++20 (GCC)",
        extension=".cpp",
        monaco_language="cpp",
        compile_cmd=["g++", "-O2", "-std=c++20", "-pipe", "-s", "{source}", "-o", "{binary}"],
        run_cmd=["{binary}"],
        is_compiled=True,
        time_multiplier=1.0,
        memory_bonus_mb=0,
        default_template=(
            "#include <bits/stdc++.h>\n"
            "using namespace std;\n\n"
            "int main() {\n"
            "    ios::sync_with_stdio(false);\n"
            "    cin.tie(nullptr);\n\n"
            "    return 0;\n"
            "}\n"
        ),
    ),
    "python3": LanguageSpec(
        id="python3",
        name="Python 3",
        extension=".py",
        monaco_language="python",
        compile_cmd=["python3", "-m", "py_compile", "{source}"],
        run_cmd=["python3", "-I", "{source}"],
        is_compiled=False,
        time_multiplier=2.0,
        memory_bonus_mb=32,
        default_template=(
            "import sys\n\n"
            "def solve() -> None:\n"
            "    data = sys.stdin.read().split()\n"
            "    if not data:\n"
            "        return\n\n"
            "if __name__ == '__main__':\n"
            "    solve()\n"
        ),
    ),
}


def get_language(lang_id: str) -> LanguageSpec:
    if lang_id not in LANGUAGES:
        raise ValueError(f"Unsupported language: {lang_id}")
    return LANGUAGES[lang_id]


def list_languages() -> List[dict]:
    return [
        {
            "id": spec.id,
            "name": spec.name,
            "extension": spec.extension,
            "monaco_language": spec.monaco_language,
            "default_template": spec.default_template,
        }
        for spec in LANGUAGES.values()
    ]
