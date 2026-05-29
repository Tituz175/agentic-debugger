import re
import json

from utils.logger import setup_logger
from agents.base_agent import BaseAgent
from utils.scoring import compute_heuristic_score


logger = setup_logger()


class EvaluatorAgent(BaseAgent):

    def __init__(self, llm):

        self.llm = llm

        self.max_retries = 2


    def build_prompt(self, context, heuristics):

        return f"""
You are a strict software repair evaluator.

Your task is to determine whether the
patched code correctly fixes the bug
while preserving the original intent.

Return ONLY valid JSON wrapped inside
<json> tags.

Format:

<json>
{{
    "intent_preserved": true,
    "minimal_fix": true,
    "root_cause_fixed": true,
    "introduced_regression": false,
    "reasoning": "..."
}}
</json>

STRICT EVALUATION RULES:

Reject fixes that:
- change arithmetic into string concatenation
- hardcode arbitrary values
- bypass execution without fixing logic
- remove functionality
- introduce unnecessary control flow

Prefer fixes that:
- preserve semantics
- minimally modify code
- directly repair the bug

Original Code:
{context["code"]}

Patched Code:
{context["fix"]["patched_code"]}

Traceback:
{context["traceback"]}

Execution Output:
{context["execution_result"]["stdout"]}

Heuristic Score:
{heuristics["score"]}

Penalties:
{heuristics["penalties"]}

Structural Change Ratio:
{heuristics["structural_ratio"]}
"""

    def run(self, context):

        run_id = context.get("run_id", "unknown")

        logger.info(
            f"[Run {run_id}] "
            f"EvaluatorAgent started"
        )

        original_code = context["code"]

        patched_code = (context["fix"]["patched_code"])

        execution_success = (context["execution_success"])

        heuristics = compute_heuristic_score(original_code, patched_code, execution_success)


        logger.info(
            f"[Run {run_id}] "
            f"Heuristic result: {heuristics}"
        )

        system_prompt = """
You are a strict software repair evaluator.
"""

        user_prompt = self.build_prompt(context, heuristics)

        llm_output = self.llm.generate(
            system_prompt,
            user_prompt,
            do_sample=False,
            temperature=0.0
        )

        logger.info(
            f"[Run {run_id}] "
            f"Raw evaluator output:\n"
            f"{llm_output}"
        )

        parsed = self.extract_json(llm_output)

        passed = (
            execution_success
            and heuristics["score"] >= 0.7
            and parsed[
                "intent_preserved"
            ]
            and parsed[
                "root_cause_fixed"
            ]
            and not parsed[
                "introduced_regression"
            ]
        )

        evaluation = {
            "passed": passed,
            "score": heuristics["score"],
            "heuristics": heuristics,
            **parsed
        }

        logger.info(
            f"[Run {run_id}] "
            f"Evaluation completed"
        )

        logger.info(
            f"[Run {run_id}] "
            f"Evaluation result: "
            f"{evaluation}"
        )

        return evaluation
    