"""
humaneval_reporter.py

Aggregates DebugOrchestrator results from a HumanEval benchmark run
and prints a structured report.

Metrics
-------
- Overall pass rate and average blended score
- Per bug-type breakdown (TypeError, NameError, LogicError, ...)
- pass@1 — since we run one fix attempt per problem, pass@1 = pass rate
- Latency summary (avg total, avg per stage)
- Failure analysis: which tasks failed and why
"""

from collections import defaultdict


def _fmt(seconds_str: str) -> float:
    """Parse '3.1234s' → 3.1234."""
    return float(seconds_str.rstrip("s"))


def report(results: list[dict], cases: list[dict]) -> None:
    """
    Print a full benchmark report.

    Parameters
    ----------
    results : list of context dicts returned by DebugOrchestrator.run()
    cases   : the original benchmark cases (for task_id, bug_type, mutation_desc)
    """
    assert len(results) == len(cases), "results and cases must be same length"

    total   = len(results)
    passed  = [r for r in results if r.get("evaluation", {}).get("passed")]
    failed  = [r for r in results if not r.get("evaluation", {}).get("passed")]

    scores  = [r.get("evaluation", {}).get("score", 0.0) for r in results]
    avg_score = sum(scores) / total if total else 0.0

    # Per bug-type aggregation
    by_type: dict[str, dict] = defaultdict(lambda: {"total": 0, "passed": 0, "scores": []})
    for result, case in zip(results, cases):
        bt = case.get("bug_type", "unknown")
        ev = result.get("evaluation", {})
        by_type[bt]["total"]  += 1
        by_type[bt]["passed"] += int(ev.get("passed", False))
        by_type[bt]["scores"].append(ev.get("score", 0.0))

    # Latency
    def _avg_latency(key: str) -> float:
        vals = []
        for r in results:
            m = r.get("metrics", {})
            if key in m:
                vals.append(_fmt(m[key]))
        return sum(vals) / len(vals) if vals else 0.0

    print("\n" + "=" * 60)
    print("  HUMANEVAL DEBUGGER BENCHMARK REPORT")
    print("=" * 60)

    print(f"\n  Total cases   : {total}")
    print(f"  Passed        : {len(passed)}  ({100*len(passed)/total:.1f}%)")
    print(f"  Failed        : {len(failed)}  ({100*len(failed)/total:.1f}%)")
    print(f"  pass@1        : {len(passed)/total:.3f}")
    print(f"  Avg score     : {avg_score:.3f}")

    print("\n  --- Latency (avg per run) ---")
    print(f"  Analysis      : {_avg_latency('analysis_latency'):.2f}s")
    print(f"  Fix           : {_avg_latency('fix_latency'):.2f}s")
    print(f"  Execution     : {_avg_latency('execution_latency'):.2f}s")
    print(f"  Evaluation    : {_avg_latency('eval_latency'):.2f}s")
    print(f"  Total         : {_avg_latency('total_latency'):.2f}s")

    print("\n  --- Per bug type ---")
    print(f"  {'Bug type':<20} {'Pass':>6} {'Total':>6} {'Rate':>7} {'Avg score':>10}")
    print(f"  {'-'*20} {'-'*6} {'-'*6} {'-'*7} {'-'*10}")
    for bt, data in sorted(by_type.items()):
        rate      = data["passed"] / data["total"] if data["total"] else 0
        avg_bt    = sum(data["scores"]) / len(data["scores"]) if data["scores"] else 0
        print(f"  {bt:<20} {data['passed']:>6} {data['total']:>6} {rate:>7.1%} {avg_bt:>10.3f}")

    if failed:
        print(f"\n  --- Failed cases ({len(failed)}) ---")
        for result, case in zip(results, cases):
            ev = result.get("evaluation", {})
            if ev.get("passed"):
                continue
            task_id  = case.get("task_id", result.get("run_id", "?"))
            bt       = case.get("bug_type", "?")
            mutation = case.get("mutation_desc", "?")
            reason   = ev.get("reasoning", "no reasoning")
            score    = ev.get("score", 0.0)
            print(f"\n  [{task_id}] {bt}")
            print(f"    Mutation : {mutation}")
            print(f"    Score    : {score:.3f}")
            print(f"    Reason   : {reason}")

    print("\n" + "=" * 60 + "\n")
