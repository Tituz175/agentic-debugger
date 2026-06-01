"""
humaneval_loader.py

Loads openai/openai_humaneval, mutates each problem, executes against
the test harness, and captures ANY failure — runtime exceptions OR
AssertionError from wrong output — as a valid debugging case.

This gives ~120-150 cases from the full 164-problem dataset.
"""

import sys
import textwrap
import subprocess
import tempfile
import os

from datasets import load_dataset

from benchmark.mutator import mutate, MutationResult
from utils.logger import setup_logger

logger = setup_logger()


# ---------------------------------------------------------------------------
# Execution
# ---------------------------------------------------------------------------

def _execute_and_capture(code: str, timeout: int = 5) -> tuple[bool, str]:
    """
    Run code in a subprocess.
    Returns (failed, traceback_string).

    Captures:
    - Runtime exceptions (TypeError, NameError, IndexError, etc.)
    - AssertionError from the HumanEval test harness (wrong output)
    - Any non-zero exit code with useful stderr or stdout
    """
    temp_path = None
    try:
        with tempfile.NamedTemporaryFile(
            suffix=".py", delete=False, mode="w", encoding="utf-8"
        ) as f:
            f.write(code)
            temp_path = f.name

        result = subprocess.run(
            [sys.executable, temp_path],
            capture_output=True,
            text=True,
            timeout=timeout,
        )

        if result.returncode != 0:
            # Prefer stderr (runtime exceptions), fall back to stdout
            raw = result.stderr.strip() or result.stdout.strip()
            if not raw:
                return False, ""

            # Clean up: keep from first Traceback / Error / Assert line
            lines = raw.split("\n")
            for i, line in enumerate(lines):
                if (line.startswith("Traceback")
                        or "Error" in line
                        or "AssertionError" in line):
                    raw = "\n".join(lines[i:])
                    break

            return True, raw

        return False, ""

    except subprocess.TimeoutExpired:
        return False, "TimeoutExpired"
    except Exception as e:
        return False, str(e)
    finally:
        if temp_path and os.path.exists(temp_path):
            os.remove(temp_path)


def _build_executable(buggy_code: str, test_code: str, entry_point: str) -> str:
    """
    Run the buggy function through the full HumanEval test harness.
    AssertionErrors are now propagated (not silenced) so wrong-output
    mutations are also captured as valid failures.
    """
    return textwrap.dedent(f"""
{buggy_code}

# --- HumanEval test harness ---
{test_code}

# Run — let ALL exceptions propagate including AssertionError
check({entry_point})
""").strip()


def _try_all_strategies(
    task_id: str,
    prompt: str,
    canonical: str,
    test_code: str,
    entry_point: str,
    base_seed: int,
    bug_types: set | None,
) -> dict | None:
    """
    Try multiple seeds per problem so we find a crashable mutation
    even when the first seed picks a strategy that doesn't produce
    a runtime failure.
    """
    # Try up to 8 different seeds per problem before giving up
    for attempt in range(8):
        mutation = mutate(
            task_id=task_id,
            prompt=prompt,
            canonical_solution=canonical,
            test=test_code,
            entry_point=entry_point,
            seed=base_seed + attempt * 1000,
        )

        if mutation is None:
            continue

        if bug_types and mutation.bug_type not in bug_types:
            continue

        executable = _build_executable(
            mutation.buggy_code, test_code, entry_point
        )
        failed, traceback_str = _execute_and_capture(executable)

        if failed and traceback_str:
            # Determine the real bug type from the actual traceback
            actual_bug_type = mutation.bug_type
            for exc in ("AssertionError", "TypeError", "NameError",
                        "IndexError", "ValueError", "AttributeError",
                        "ZeroDivisionError", "KeyError", "RecursionError"):
                if exc in traceback_str:
                    actual_bug_type = exc
                    break

            return {
                "task_id":       task_id,
                "buggy_code":    mutation.buggy_code,
                "original_code": mutation.original_code,
                "traceback":     traceback_str,
                "bug_type":      actual_bug_type,
                "mutation_desc": mutation.mutation_desc,
                "test_code":     test_code,
                "entry_point":   entry_point,
            }

    return None


# ---------------------------------------------------------------------------
# Main loader
# ---------------------------------------------------------------------------

class HumanEvalLoader:
    """
    Parameters
    ----------
    max_cases  : max cases to return (None = all that are crashable)
    seed       : base random seed
    bug_types  : filter to specific exception types
    """

    DATASET_NAME = "openai/openai_humaneval"
    SPLIT        = "test"

    def __init__(
        self,
        max_cases:  int | None = None,
        seed:       int        = 42,
        bug_types:  list[str] | None = None,
    ):
        self.max_cases = max_cases
        self.seed      = seed
        self.bug_types = set(bug_types) if bug_types else None

    def load(self) -> list[dict]:
        logger.info(f"Loading {self.DATASET_NAME} ...")
        dataset = load_dataset(self.DATASET_NAME, split=self.SPLIT)
        logger.info(f"Loaded {len(dataset)} HumanEval problems")

        cases   = []
        skipped = 0

        for i, problem in enumerate(dataset):
            if self.max_cases and len(cases) >= self.max_cases:
                break

            task_id     = problem["task_id"]
            prompt      = problem["prompt"]
            canonical   = problem["canonical_solution"]
            test_code   = problem["test"]
            entry_point = problem["entry_point"]

            case = _try_all_strategies(
                task_id=task_id,
                prompt=prompt,
                canonical=canonical,
                test_code=test_code,
                entry_point=entry_point,
                base_seed=self.seed + i,
                bug_types=self.bug_types,
            )

            if case is None:
                logger.debug(f"[{task_id}] No crashable mutation found — skipping")
                skipped += 1
                continue

            cases.append(case)
            logger.info(
                f"[{task_id}] ✓ {case['bug_type']}: {case['mutation_desc']}"
            )

        logger.info(
            f"HumanEval loader done — {len(cases)} cases ready "
            f"| {skipped} skipped"
        )
        return cases
