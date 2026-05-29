# run from your project root
from benchmark.humaneval_loader import HumanEvalLoader
loader = HumanEvalLoader(max_cases=3)
cases = loader.load()
for c in cases:
    print(c["task_id"], c["bug_type"], c["traceback"][:80])