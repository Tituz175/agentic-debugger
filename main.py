from pprint import pprint

from orchestrator.orchestrator import DebugOrchestrator
from utils.benchmark_loader import BenchmarkLoader
from utils.logger import setup_logger

logger = setup_logger()


def main():
    benchmark_loader = BenchmarkLoader()
    benchmark_cases  = benchmark_loader.load_all_cases()

    orchestrator = DebugOrchestrator()

    results = []

    for i, case in enumerate(benchmark_cases, start=1):
        logger.info(f"--- Benchmark case {i}/{len(benchmark_cases)} ---")

        result = orchestrator.run(
            code      = case["buggy_code"],
            traceback = case["traceback"],
        )

        pprint(result)
        results.append(result)

    # ------------------------------------------------------------------
    # Summary
    # ------------------------------------------------------------------
    total   = len(results)
    passed  = sum(1 for r in results if r.get("evaluation", {}).get("passed"))
    avg_score = (
        sum(r.get("evaluation", {}).get("score", 0.0) for r in results) / total
        if total else 0.0
    )

    print("\n" + "=" * 50)
    print(f"Benchmark complete: {passed}/{total} passed  |  avg score: {avg_score:.3f}")
    print("=" * 50)


if __name__ == "__main__":
    main()
