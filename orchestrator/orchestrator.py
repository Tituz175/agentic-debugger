import time
import uuid
from utils.logger import setup_logger

from agents.fixer import FixerAgent
from agents.analyzer import AnalyzerAgent
from agents.evaluator import EvaluatorAgent

from sandbox.runner import SandboxRunner

logger = setup_logger()
run_id = str(uuid.uuid4())[:8]


class DebugOrchestrator:

    def __init__(self):
        self.analyzer = AnalyzerAgent()
        self.fixer = FixerAgent()
        self.evaluator = EvaluatorAgent()
        self.runner = SandboxRunner()

    def run(self, code: str, traceback: str):

        logger.info(f"[Run {run_id}] Debug orchestration started")

        context = {
            "run_id": run_id,
            "code": code,
            "traceback": traceback
        }

        start_time = time.perf_counter()
        analysis = self.analyzer.run(context)
        analysis_time = time.perf_counter() - start_time
        context["analysis"] = analysis

        start_time = time.perf_counter()
        fix = self.fixer.run(context)
        fix_time = time.perf_counter() - start_time
        context["fix"] = fix

        print(context)

        start_time = time.perf_counter()
        execution = self.runner.execute(
            run_id,
            fix["patched_code"]
        )
        execution_time = time.perf_counter() - start_time
        context["execution_success"] = execution["success"]
        context["execution_result"] = execution
        context["metrics"] = {
            "analysis_latency": f"{analysis_time:.4f}s",
            "fix_latency": f"{fix_time:.4f}s",
            "execution_latency": f"{execution_time:.4f}s"
        }
        evaluation = self.evaluator.run(context)
        context["evaluation"] = evaluation

        logger.info(f"[Run {run_id}] Debug orchestration completed\n\n\n")

        return context
