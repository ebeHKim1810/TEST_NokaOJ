"""Unit & integration tests for Judge Engine (AC/WA/TLE/MLE/RE/CE) and Advanced Testcase Generator (Mode A/B/C + failure cases)."""
import unittest

from judge.generators.engine import TestcaseGeneratorEngine
from judge.worker.worker import JudgeEngine, TestcaseInput


class TestJudgeEngineAndGenerator(unittest.TestCase):
    def setUp(self) -> None:
        self.judge = JudgeEngine()
        self.gen = TestcaseGeneratorEngine()
        self.tcs = [
            TestcaseInput(1, "01", "2 3\n", "5\n"),
            TestcaseInput(2, "02", "100 -40\n", "60\n"),
        ]

    def test_cpp17_ac(self) -> None:
        code = """
#include <iostream>
using namespace std;
int main() { long long a, b; if (cin >> a >> b) cout << (a + b) << "\\n"; }
"""
        res = self.judge.judge_submission(code, "cpp17", self.tcs, time_limit_ms=1000, memory_limit_mb=128)
        self.assertEqual(res.verdict, "AC")
        self.assertEqual(res.score, 100)

    def test_cpp20_ac(self) -> None:
        code = """
#include <iostream>
int main() { long long a, b; std::cin >> a >> b; std::cout << a + b << '\\n'; }
"""
        res = self.judge.judge_submission(code, "cpp20", self.tcs, time_limit_ms=1000, memory_limit_mb=128)
        self.assertEqual(res.verdict, "AC")

    def test_python_wa(self) -> None:
        code = "a, b = map(int, input().split())\nprint(a - b)\n"
        res = self.judge.judge_submission(code, "python3", self.tcs, time_limit_ms=1000, memory_limit_mb=128)
        self.assertEqual(res.verdict, "WA")
        self.assertEqual(res.score, 0)

    def test_tle(self) -> None:
        code = "while True:\n    pass\n"
        res = self.judge.judge_submission(code, "python3", [self.tcs[0]], time_limit_ms=300, memory_limit_mb=128)
        self.assertEqual(res.verdict, "TLE")

    def test_mle(self) -> None:
        code = "x = bytearray(200 * 1024 * 1024)\nprint(len(x))\n"
        res = self.judge.judge_submission(code, "python3", [self.tcs[0]], time_limit_ms=1000, memory_limit_mb=48)
        self.assertIn(res.verdict, ("MLE", "RE"))  # Linux RLIMIT_AS raises MemoryError -> MLE
        self.assertEqual(res.verdict, "MLE")

    def test_re(self) -> None:
        code = "print(1 // 0)\n"
        res = self.judge.judge_submission(code, "python3", [self.tcs[0]], time_limit_ms=1000, memory_limit_mb=128)
        self.assertEqual(res.verdict, "RE")

    def test_ce(self) -> None:
        code = "int main() { syntax error here }\n"
        res = self.judge.judge_submission(code, "cpp17", self.tcs, time_limit_ms=1000, memory_limit_mb=128)
        self.assertEqual(res.verdict, "CE")
        self.assertTrue(len(res.compile_output) > 0)

    def test_generator_mode_a_success(self) -> None:
        ref_cpp = """
#include <iostream>
using namespace std;
int main() { long long a, b; cin >> a >> b; cout << a + b << "\\n"; }
"""
        gen_py = """
import random, sys
idx = int(sys.argv[1])
seed = int(sys.argv[2])
rng = random.Random(seed)
print(rng.randint(1, 100 * idx), rng.randint(1, 100 * idx))
"""
        rep = self.gen.generate(
            mode="custom_generator",
            reference_code=ref_cpp,
            reference_language="cpp17",
            generator_code=gen_py,
            generator_language="python3",
            num_tests=5,
            seed=12345,
        )
        self.assertEqual(rep.success_count, 5)
        self.assertEqual(rep.failed_count, 0)
        for item in rep.items:
            a, b = map(int, item.input_data.split())
            self.assertEqual(int(item.expected_output.strip()), a + b)

    def test_generator_mode_b_constraints(self) -> None:
        ref_py = "n = int(input())\narr = list(map(int, input().split()))\nprint(sum(arr))\n"
        schema = {
            "fields": [
                {"name": "n", "type": "int", "min": 3, "max": 10, "newline": True},
                {"name": "arr", "type": "array", "length_ref": "n", "min": 1, "max": 50},
            ]
        }
        rep = self.gen.generate(
            mode="constraints",
            reference_code=ref_py,
            reference_language="python3",
            constraint_schema=schema,
            num_tests=4,
            seed=99,
        )
        self.assertEqual(rep.success_count, 4)

    def test_generator_mode_c_builtin_template(self) -> None:
        ref_py = "n = int(input())\narr = list(map(int, input().split()))\nprint(max(arr))\n"
        rep = self.gen.generate(
            mode="builtin_template",
            reference_code=ref_py,
            reference_language="python3",
            template_id="random_array",
            template_params={"n_min": 5, "n_max": 20, "min_val": -100, "max_val": 100},
            profile_distribution={"min_constraints": 1, "max_constraints": 1, "sorted": 1, "duplicates": 1},
            num_tests=4,
            seed=777,
        )
        self.assertEqual(rep.success_count, 4)

    def test_generator_crash_and_timeout_and_ref_crash(self) -> None:
        ref_ok = "print(sum(map(int, input().split())))\n"
        gen_crash = "raise RuntimeError('gen crashed')\n"
        r1 = self.gen.generate(
            mode="custom_generator",
            reference_code=ref_ok,
            reference_language="python3",
            generator_code=gen_crash,
            generator_language="python3",
            num_tests=2,
        )
        self.assertEqual(r1.failed_count, 2)
        self.assertIn("Generator RE", r1.items[0].error)

        gen_tle = "while True:\n    pass\n"
        r2 = self.gen.generate(
            mode="custom_generator",
            reference_code=ref_ok,
            reference_language="python3",
            generator_code=gen_tle,
            generator_language="python3",
            num_tests=1,
            time_limit_ms=250,
        )
        self.assertEqual(r2.failed_count, 1)
        self.assertIn("Generator TLE", r2.items[0].error)

        ref_crash = "raise ValueError('ref crashed')\n"
        r3 = self.gen.generate(
            mode="builtin_template",
            reference_code=ref_crash,
            reference_language="python3",
            template_id="random_integer",
            num_tests=2,
        )
        self.assertEqual(r3.failed_count, 2)
        self.assertIn("Reference Solution RE", r3.items[0].error)


if __name__ == "__main__":
    unittest.main()
