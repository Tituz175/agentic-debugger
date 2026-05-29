"""
main_humaneval.py

Entry point for running your agentic debugger against the
openai/openai_humaneval benchmark.

Usage
-----
    python main_humaneval.py                        # 20 cases, any bug type
    python main_humaneval.py --max 50               # 50 cases
    python main_humaneval.py --bug-types TypeError  # TypeErrors only
    python main_humaneval.py --max 164 --seed 123   # full run, fixed seed
    python main_humaneval.py --no-color             # plain text output
"""

import argparse

from orchestrator.orchestrator import DebugOrchestrator
from benchmark.humaneval_loader import HumanEvalLoader
from benchmark.humaneval_reporter import report
from utils.display import print_banner, print_case_result, print_final_report
from utils.logger import setup_logger

logger = setup_logger()


def parse_args():
    parser = argparse.ArgumentParser(description="Run agentic debugger on HumanEval")
    parser.add_argument("--max",       type=int,   default=20,   help="Max cases (default: 20)")
    parser.add_argument("--seed",      type=int,   default=42,   help="Mutation seed (default: 42)")
    parser.add_argument("--bug-types", nargs="+",  default=None, metavar="TYPE",
                        help="Filter bug types e.g. TypeError NameError")
    parser.add_argument("--no-color",  action="store_true",      help="Disable ANSI colour output")
    return parser.parse_args()


def main():
    args = parse_args()

    # Strip all ANSI if --no-color
    if args.no_color:
        import utils.display as _d
        for attr in dir(_d):
            if attr.isupper() and isinstance(getattr(_d, attr), str):
                setattr(_d, attr, "")

    print_banner()

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

    # --- Run debugger ---
    orchestrator = DebugOrchestrator()
    results      = []
    total        = len(cases)

    for i, case in enumerate(cases, start=1):
        logger.info(
            f"[{case['task_id']}] {case['bug_type']} — {case['mutation_desc']}"
        )

        result = orchestrator.run(
            code=case["buggy_code"],
            traceback=case["traceback"],
        )
        results.append(result)

        print_case_result(result, case, i, total)

    # --- Final report ---
    print_final_report(results, cases)


if __name__ == "__main__":
    main()
