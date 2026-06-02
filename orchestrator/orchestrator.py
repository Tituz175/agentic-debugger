import re
import time
import uuid

from models.llm import LLMModel
from utils.logger import setup_logger
from sandbox.runner import SandboxRunner

from agents.fixer import FixerAgent
from agents.critique import CritiqueAgent
from agents.analyzer import AnalyzerAgent
from agents.evaluator import EvaluatorAgent

logger = setup_logger()


def _strip_docstring(code: str) -> str:
    """Remove triple-quoted docstrings to shorten fixer prompt."""
    return re.sub(
        r'(def\s+\w+[^:]*:)\s*""".*?"""',
        r'\1',
        code,
        flags=re.DOTALL,
    )


class DebugOrchestrator:
    """
    Coordinates the full agentic debugging pipeline.

    Pipeline:
        Analyzer
            ↓
        Iterative Repair Loop:
            Fixer
            ↓
            SandboxRunner
            ↓
            Evaluator
            ↓
            CritiqueAgent
            ↓
            Retry (optional)

    Each stage appends results into a shared `context`
    dictionary so downstream agents can access the full
    repair history.
    """

    def __init__(
        self,
        model_name: str = "Qwen/Qwen2.5-Coder-32B-Instruct-AWQ"
    ):

        logger.info("Initialising DebugOrchestrator")

        self.max_fix_attempts = 3

        self.llm        = LLMModel(model_name)

        self.analyzer   = AnalyzerAgent(self.llm)
        self.fixer      = FixerAgent(self.llm)
        self.evaluator  = EvaluatorAgent(self.llm)
        self.critique   = CritiqueAgent(self.llm)

        self.runner     = SandboxRunner()

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _timed(fn, *args, **kwargs):
        """
        Call fn(*args, **kwargs) and return:
            (result, elapsed_seconds)
        """

        start = time.perf_counter()

        result = fn(*args, **kwargs)

        elapsed = time.perf_counter() - start

        return result, elapsed

    # ------------------------------------------------------------------
    # Entry point
    # ------------------------------------------------------------------

    def run(self, code: str, traceback: str) -> dict:

        run_id = str(uuid.uuid4())[:8]

        logger.info(f"[Run {run_id}] Orchestration started")

        context = {
            "run_id": run_id,
            "code": code,
            "traceback": traceback,
        }

        # ==============================================================
        # Stage 1: Analyze
        # ==============================================================

        analysis, analysis_latency = self._timed(
            self.analyzer.run,
            context
        )

        context["analysis"] = analysis

        if not analysis.get("parse_success"):

            logger.error(
                f"[Run {run_id}] Analysis failed — aborting pipeline"
            )

            return self._failure_result(
                context=context,
                analysis_latency=analysis_latency,
                failed_at="analysis",
            )

        # ==============================================================
        # Iterative Repair Loop
        # ==============================================================

        context["repair_history"] = []

        critique_latency = 0.0
        fix_latency = 0.0
        execution_latency = 0.0
        eval_latency = 0.0

        for attempt in range(self.max_fix_attempts):

            # ----------------------------------------------------------
            # Clear stale critique/evaluation state before new repair
            # ----------------------------------------------------------
            context.pop("critique", None)
            context.pop("evaluation", None)
            context.pop("execution_result", None)

            logger.info(
                f"[Run {run_id}] Repair attempt "
                f"{attempt + 1}/{self.max_fix_attempts}"
            )

            # ----------------------------------------------------------
            # Stage 2: Fix
            # ----------------------------------------------------------

            fix, fix_latency = self._timed(
                self.fixer.run,
                context
            )

            context["fix"] = fix

            if (
                not fix.get("parse_success")
                or not fix.get("patched_code")
            ):
                logger.error(
                    f"[Run {run_id}] Fix generation failed on attempt {attempt + 1}"
                )
                if attempt == 0:
                    # Strip docstring to shorten prompt and retry
                    logger.info(f"[Run {run_id}] Retrying with stripped docstring")
                    context["code"] = re.sub(
                        r'(def\s+\w+[^:]*:)\s*""".*?"""',
                        r'\1',
                        context["code"],
                        flags=re.DOTALL,
                    )
                    continue
                break

            # ----------------------------------------------------------
            # Stage 3: Execute
            # ----------------------------------------------------------

            execution, execution_latency = self._timed(
                self.runner.execute,
                run_id,
                fix["patched_code"]
            )

            context["execution_result"] = execution

            context["execution_success"] = execution["success"]

            # ----------------------------------------------------------
            # Stage 4: Evaluate
            # ----------------------------------------------------------

            evaluation, eval_latency = self._timed(
                self.evaluator.run,
                context
            )

            context["evaluation"] = evaluation

            # ----------------------------------------------------------
            # Success Exit
            # ----------------------------------------------------------

            if evaluation.get("passed"):

                logger.info(
                    f"[Run {run_id}] Successful repair "
                    f"on attempt {attempt + 1}"
                )

                break

            # ----------------------------------------------------------
            # Stage 5: Critique
            # ----------------------------------------------------------

            logger.info(
                f"[Run {run_id}] Patch failed evaluation — "
                f"running critique"
            )

            critique, critique_latency = self._timed(
                self.critique.run,
                context
            )

            context["critique"] = critique

            # ----------------------------------------------------------
            # Store repair history
            # ----------------------------------------------------------

            context["repair_history"].append({
                "attempt": attempt + 1,
                "patch": fix["patched_code"],
                "evaluation": evaluation,
                "critique": critique,
            })

            # ----------------------------------------------------------
            # Stall Detection
            # ----------------------------------------------------------

            if len(context["repair_history"]) >= 2:
                prev_score = context["repair_history"][-2]["evaluation"]["score"]
                curr_score = context["repair_history"][-1]["evaluation"]["score"]
                if curr_score == prev_score:
                    logger.info(
                        f"[Run {run_id}] Score stalled at "
                        f"{curr_score:.3f} after "
                        f"{len(context['repair_history'])} attempts "
                        f"— stopping retries"
                    )
                    break

            # ----------------------------------------------------------
            # Retry Decision
            # ----------------------------------------------------------

            if not critique.get("should_retry"):

                logger.info(
                    f"[Run {run_id}] Critique advised "
                    f"stopping retries"
                )

                break


        # Guarantee evaluation key always exists even if repair loop
        # exited early due to fix generation failure
        if "evaluation" not in context:
            context["evaluation"] = {
                "passed": False,
                "score":  0.0,
                "reasoning": "Pipeline exited before evaluation — fix generation failed.",
            }

        if "execution_result" not in context:
            context["execution_result"] = {
                "success": False,
                "stdout":  "",
                "stderr":  "Fix generation failed — execution never ran.",
            }
            context["execution_success"] = False

        # ==============================================================
        # Metrics
        # ==============================================================

        total_latency = (
            analysis_latency
            + fix_latency
            + execution_latency
            + eval_latency
            + critique_latency
        )

        context["metrics"] = {
            "analysis_latency":  f"{analysis_latency:.4f}s",
            "fix_latency":       f"{fix_latency:.4f}s",
            "execution_latency": f"{execution_latency:.4f}s",
            "eval_latency":      f"{eval_latency:.4f}s",
            "critique_latency":  f"{critique_latency:.4f}s",
            "total_latency":     f"{total_latency:.4f}s",
        }

        logger.info(
            f"[Run {run_id}] Orchestration completed — "
            f"passed={context.get('evaluation', {}).get('passed')}"
        )

        return context

    # ------------------------------------------------------------------
    # Failure path
    # ------------------------------------------------------------------

    @staticmethod
    def _failure_result(
        context: dict,
        analysis_latency: float,
        failed_at: str,
        fix_latency: float = 0.0,
    ) -> dict:

        context["execution_result"] = {
            "success": False,
            "stdout": "",
            "stderr": "",
        }

        context["execution_success"] = False

        context["evaluation"] = {
            "passed": False,
            "score": 0.0,
            "reasoning": (
                f"Pipeline aborted at {failed_at} stage."
            ),
        }

        context["metrics"] = {
            "analysis_latency":  f"{analysis_latency:.4f}s",
            "fix_latency":       f"{fix_latency:.4f}s",
            "execution_latency": "0.0000s",
            "eval_latency":      "0.0000s",
            "critique_latency":  "0.0000s",
            "total_latency": (
                f"{analysis_latency + fix_latency:.4f}s"
            ),
        }

        return context
