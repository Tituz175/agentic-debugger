import json
from pathlib import Path


class BenchmarkLoader:

    def __init__(self, benchmark_dir="benchmarks"):

        self.benchmark_dir = Path(benchmark_dir)

    def load_all_cases(self):

        benchmark_cases = []

        for file in self.benchmark_dir.rglob("*.json"):

            with open(file, "r") as f:

                benchmark_cases.append(
                    json.load(f)
                )

        return benchmark_cases
