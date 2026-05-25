from pprint import pprint
from orchestrator.orchestrator import DebugOrchestrator

buggy_code = """
x = 10
y = 0
print(x / y)
"""

traceback = "ZeroDivisionError: division by zero"


orchestrator = DebugOrchestrator()

result = orchestrator.run(
    code=buggy_code,
    traceback=traceback
)

pprint(result)
