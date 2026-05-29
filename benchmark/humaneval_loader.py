"""
humaneval_loader.py

Loads the openai/openai_humaneval dataset, introduces bugs via the mutator,
executes the buggy code to capture real tracebacks, and yields benchmark
cases in the format your DebugOrchestrator expects.

Each yielded case has:
    task_id         : str   — "HumanEval/N"
    buggy_code      : str   — full executable Python with one bug
    original_code   : str   — correct version (for reference / future eval)
    traceback       : str   — real traceback from running the buggy code
    bug_type        : str   — exception class the mutation targets
    mutation_desc   : str   — what was changed
    test_code       : str   — HumanEval assert block (for pass@k eval later)
    entry_point     : str   — function name

Usage
-----
    from benchmark.humaneval_loader import HumanEvalLoader

    loader = HumanEvalLoader(max_cases=20, seed=42)
    for case in loader.load():
        result = orchestrator.run(case["buggy_code"], case["traceback"])
"""

import sys
import textwrap
import traceback as tb
import subprocess
import tempfile
import os

from datasets import load_dataset

from benchmark.mutator import mutate, MutationResult
from utils.logger import setup_logger

logger = setup_logger()


# ---------------------------------------------------------------------------
# Execution helper (reuses your SandboxRunner logic inline so this module
# has no circular import on SandboxRunner)
# ---------------------------------------------------------------------------

def _execute_and_capture(code: str, timeout: int = 5) -> tuple[bool, str]:
    """
    Run code in a subprocess.  Returns (crashed, traceback_string).
    crashed=True means the code raised an exception we can use.
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

        if result.returncode != 0 and result.stderr.strip():
            # Extract just the exception line(s) — drop internal path noise
            stderr = result.stderr.strip()
            lines  = stderr.split('\n')
            # Keep from the first 'Traceback' line onward
            for i, line in enumerate(lines):
                if line.startswith('Traceback') or 'Error' in line:
                    stderr = '\n'.join(lines[i:])
                    break
            return True, stderr

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
    Combine the buggy function with a minimal call so it actually executes
    and raises the bug.  HumanEval functions are usually pure — we call them
    with trivial arguments derived from the test harness.
    """
    # The HumanEval test block uses check(candidate) where candidate is the fn.
    # We run check(entry_point) to trigger the bug under realistic conditions.
    runner = textwrap.dedent(f"""
{buggy_code}

# --- HumanEval test harness ---
{test_code}

try:
    check({entry_point})
except AssertionError:
    pass  # wrong output, not a crash — we only want exception tracebacks
""")
    return runner


# ---------------------------------------------------------------------------
# Main loader
# ---------------------------------------------------------------------------

class HumanEvalLoader:
    """
    Loads HumanEval problems, mutates them, and filters to cases that
    produce real tracebacks when executed.

    Parameters
    ----------
    max_cases   : maximum number of valid cases to yield (None = all)
    seed        : random seed for mutation reproducibility
    bug_types   : if set, only yield cases with these bug types
                  e.g. ["TypeError", "NameError"]
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
        """
        Returns a list of benchmark case dicts ready for DebugOrchestrator.
        Logs a summary at the end.
        """
        logger.info(f"Loading {self.DATASET_NAME} ...")
        dataset = load_dataset(self.DATASET_NAME, split=self.SPLIT)
        logger.info(f"Loaded {len(dataset)} HumanEval problems")

        cases    = []
        skipped  = {"no_mutation": 0, "no_crash": 0, "wrong_type": 0}

        for i, problem in enumerate(dataset):
            if self.max_cases and len(cases) >= self.max_cases:
                break

            task_id        = problem["task_id"]
            prompt         = problem["prompt"]
            canonical      = problem["canonical_solution"]
            test_code      = problem["test"]
            entry_point    = problem["entry_point"]

            # --- Mutate ---
            mutation = mutate(
                task_id=task_id,
                prompt=prompt,
                canonical_solution=canonical,
                test=test_code,
                entry_point=entry_point,
                seed=self.seed + i,
            )

            if mutation is None:
                logger.debug(f"[{task_id}] No mutation found — skipping")
                skipped["no_mutation"] += 1
                continue

            # --- Filter by bug type if requested ---
            if self.bug_types and mutation.bug_type not in self.bug_types:
                skipped["wrong_type"] += 1
                continue

            # --- Execute to get a real traceback ---
            executable = _build_executable(
                mutation.buggy_code, test_code, entry_point
            )
            crashed, traceback_str = _execute_and_capture(executable)

            if not crashed or not traceback_str:
                logger.debug(
                    f"[{task_id}] Mutation '{mutation.mutation_desc}' "
                    f"did not raise — skipping"
                )
                skipped["no_crash"] += 1
                continue

            case = {
                "task_id":       task_id,
                "buggy_code":    mutation.buggy_code,
                "original_code": mutation.original_code,
                "traceback":     traceback_str,
                "bug_type":      mutation.bug_type,
                "mutation_desc": mutation.mutation_desc,
                "test_code":     test_code,
                "entry_point":   entry_point,
            }
            cases.append(case)
            logger.info(
                f"[{task_id}] ✓ {mutation.bug_type}: {mutation.mutation_desc}"
            )

        logger.info(
            f"HumanEval loader done — "
            f"{len(cases)} cases ready | "
            f"skipped: {skipped}"
        )
        return cases
