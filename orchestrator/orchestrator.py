import time
from agents.analyzer import AnalyzerAgent
from agents.fixer import FixerAgent
from agents.evaluator import EvaluatorAgent

from sandbox.runner import SandboxRunner


class DebugOrchestrator:

    def __init__(self):
        self.analyzer = AnalyzerAgent()
        self.fixer = FixerAgent()
        self.evaluator = EvaluatorAgent()
        self.runner = SandboxRunner()

    def run(self, code: str, traceback: str):

        context = {
            "code": code,
            "traceback": traceback
        }

        start_time = time.perf_counter()

        analysis = self.analyzer.run(context)

        analysis_time = time.perf_counter() - start_time

        context.update(analysis)

        start_time = time.perf_counter()

        fix = self.fixer.run(context)

        fix_time = time.perf_counter() - start_time

        context.update(fix)

        start_time = time.perf_counter()

        execution = self.runner.execute(
            fix["patched_code"]
        )

        execution_time = time.perf_counter() - start_time

        context["execution_success"] = execution["success"]
        context["execution_result"] = execution
        context["metrics"] = {
            "analysis_latency": analysis_time,
            "fix_latency": fix_time,
            "execution_latency": execution_time
        }


        evaluation = self.evaluator.run(context)

        context.update(evaluation)

        return context
