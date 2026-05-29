import time
import uuid

from agents.analyzer import AnalyzerAgent
from agents.fixer import FixerAgent
from agents.evaluator import EvaluatorAgent
from models.llm import LLMModel
from sandbox.runner import SandboxRunner
from utils.logger import setup_logger

logger = setup_logger()


class DebugOrchestrator:
    """
    Coordinates the full debug pipeline:
        Analyzer → Fixer → SandboxRunner → Evaluator

    Each stage adds its output to a shared `context` dict that is
    passed forward, so every agent has full visibility into prior results.
    """

    def __init__(self, model_name: str = "Qwen/Qwen2.5-Coder-32B-Instruct-AWQ"):
        logger.info("Initialising DebugOrchestrator")
        self.llm       = LLMModel(model_name)
        self.analyzer  = AnalyzerAgent(self.llm)
        self.fixer     = FixerAgent(self.llm)
        self.evaluator = EvaluatorAgent(self.llm)
        self.runner    = SandboxRunner()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _timed(fn, *args, **kwargs):
        """Call fn(*args, **kwargs) and return (result, elapsed_seconds)."""
        t0 = time.perf_counter()
        result = fn(*args, **kwargs)
        return result, time.perf_counter() - t0

    # ------------------------------------------------------------------
    # Entry point
    # ------------------------------------------------------------------

    def run(self, code: str, traceback: str) -> dict:
        run_id = str(uuid.uuid4())[:8]
        logger.info(f"[Run {run_id}] Orchestration started")

        context = {
            "run_id":    run_id,
            "code":      code,
            "traceback": traceback,
        }

        # --- Stage 1: Analyze -------------------------------------------
        analysis, analysis_latency = self._timed(self.analyzer.run, context)
        context["analysis"] = analysis

        if not analysis.get("parse_success"):
            logger.error(f"[Run {run_id}] Analysis failed — aborting pipeline")
            return self._failure_result(context, analysis_latency, "analysis")

        # --- Stage 2: Fix -----------------------------------------------
        fix, fix_latency = self._timed(self.fixer.run, context)
        context["fix"] = fix

        if not fix.get("parse_success") or not fix.get("patched_code"):
            logger.error(f"[Run {run_id}] Fix failed — aborting pipeline")
            return self._failure_result(
                context, analysis_latency, "fix", fix_latency=fix_latency
            )

        # --- Stage 3: Execute -------------------------------------------
        execution, execution_latency = self._timed(
            self.runner.execute, run_id, fix["patched_code"]
        )
        context["execution_result"]  = execution
        context["execution_success"] = execution["success"]

        # --- Stage 4: Evaluate ------------------------------------------
        evaluation, eval_latency = self._timed(self.evaluator.run, context)
        context["evaluation"] = evaluation

        # --- Metrics ----------------------------------------------------
        context["metrics"] = {
            "analysis_latency":  f"{analysis_latency:.4f}s",
            "fix_latency":       f"{fix_latency:.4f}s",
            "execution_latency": f"{execution_latency:.4f}s",
            "eval_latency":      f"{eval_latency:.4f}s",
            "total_latency":     f"{analysis_latency + fix_latency + execution_latency + eval_latency:.4f}s",
        }

        logger.info(f"[Run {run_id}] Orchestration completed — passed={evaluation.get('passed')}")
        return context

    # ------------------------------------------------------------------
    # Failure path
    # ------------------------------------------------------------------

    @staticmethod
    def _failure_result(context: dict, analysis_latency: float, failed_at: str, fix_latency: float = 0.0) -> dict:
        context["execution_result"]  = {"success": False, "stdout": "", "stderr": ""}
        context["execution_success"] = False
        context["evaluation"]        = {
            "passed": False,
            "score":  0.0,
            "reasoning": f"Pipeline aborted at {failed_at} stage.",
        }
        context["metrics"] = {
            "analysis_latency":  f"{analysis_latency:.4f}s",
            "fix_latency":       f"{fix_latency:.4f}s",
            "execution_latency": "0.0000s",
            "eval_latency":      "0.0000s",
            "total_latency":     f"{analysis_latency + fix_latency:.4f}s",
        }
        return context
