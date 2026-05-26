from pprint import pprint
from orchestrator.orchestrator import DebugOrchestrator
from utils.benchmark_loader import BenchmarkLoader

benchmark_loader = BenchmarkLoader()
benchmark_cases = benchmark_loader.load_all_cases()

orchestrator = DebugOrchestrator()

for case in benchmark_cases:

    result = orchestrator.run(
        code = case["buggy_code"],
        traceback = case["traceback"]
    )

    pprint(result)
