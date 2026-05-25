from agents.analyzer import AnalyzerAgent
from agents.fixer import FixerAgent
from agents.evaluator import EvaluatorAgent

from sandbox.runner import Sandbox


class DebugOrchestrator:

    def __init__(self):
        self.analyzer = AnalyzerAgent()
        self.fixer = FixerAgent()
        self.evaluator = EvaluatorAgent()
        self.runner = Sandbox()

    def run(self, code: str, traceback: str):

        context = {
            "code": code,
            "traceback": traceback
        }

        analysis = self.analyzer.run(context)

        context.update(analysis)

        fix = self.fixer.run(context)

        context.update(fix)

        execution = self.runner.execute(
            fix["patched_code"]
        )

        context["execution_success"] = execution["success"]
        context["execution_result"] = execution

        evaluation = self.evaluator.run(context)

        context.update(evaluation)

        return context
