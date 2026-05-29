"""
main_humaneval.py

Entry point for running your agentic debugger against the
openai/openai_humaneval benchmark.

Usage
-----
    # Run 20 cases of any bug type
    python main_humaneval.py

    # Run 50 TypeError cases only
    python main_humaneval.py --max 50 --bug-types TypeError

    # Run full benchmark (164 problems, fewer will have crashable mutations)
    python main_humaneval.py --max 164

    # Reproduce a specific run
    python main_humaneval.py --seed 123
"""

import argparse
from pprint import pprint

from orchestrator.orchestrator import DebugOrchestrator
from benchmark.humaneval_loader import HumanEvalLoader
from benchmark.humaneval_reporter import report
from utils.logger import setup_logger

logger = setup_logger()


def parse_args():
    parser = argparse.ArgumentParser(description="Run agentic debugger on HumanEval")
    parser.add_argument(
        "--max", type=int, default=20,
        help="Maximum number of benchmark cases to run (default: 20)"
    )
    parser.add_argument(
        "--seed", type=int, default=42,
        help="Random seed for mutation reproducibility (default: 42)"
    )
    parser.add_argument(
        "--bug-types", nargs="+", default=None,
        metavar="TYPE",
        help="Filter to specific bug types e.g. TypeError NameError LogicError"
    )
    parser.add_argument(
        "--verbose", action="store_true",
        help="Print full result dict for each case"
    )
    return parser.parse_args()


def main():
    args = parse_args()

    # --- Load benchmark cases ---
    loader = HumanEvalLoader(
        max_cases=args.max,
        seed=args.seed,
        bug_types=args.bug_types,
    )
    cases = loader.load()

    if not cases:
        logger.error("No benchmark cases loaded — exiting")
        return

    logger.info(f"Running {len(cases)} benchmark cases")

    # --- Run debugger ---
    orchestrator = DebugOrchestrator()
    results = []

    for i, case in enumerate(cases, start=1):
        logger.info(
            f"\n--- Case {i}/{len(cases)} | "
            f"{case['task_id']} | "
            f"{case['bug_type']} ---"
        )
        logger.info(f"Mutation: {case['mutation_desc']}")

        result = orchestrator.run(
            code=case["buggy_code"],
            traceback=case["traceback"],
        )
        results.append(result)

        if args.verbose:
            pprint(result)

    # --- Report ---
    report(results, cases)


if __name__ == "__main__":
    main()
