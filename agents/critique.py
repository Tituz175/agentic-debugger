from agents.base_agent import BaseAgent
from utils.logger import setup_logger

logger = setup_logger()


class CritiqueAgent(BaseAgent):
    """
    Generates strategic feedback for failed repair attempts.

    The critique agent does NOT fix code directly.
    It explains WHY a patch failed evaluation and
    guides the next repair attempt.
    """

    max_retries = 2

    _SYSTEM_PROMPT = """
You are a software repair critique agent.

Your task is to analyze why a proposed bug fix failed evaluation.

You must:
- identify the precise repair mistake
- explain why the patch violated intent preservation
- provide actionable retry guidance
- avoid vague criticism

You are NOT repairing the code yourself.
You are generating strategic feedback for another repair agent.
""".strip()

    def __init__(self, llm):
        super().__init__(llm)

    # ------------------------------------------------------------------
    # Prompt construction
    # ------------------------------------------------------------------

    def _build_prompt(self, context: dict) -> str:

        return f"""
Analyze why the attempted patch failed evaluation.

Return ONLY this structure:

<json>
{{
    "failure_type": "<short failure category>",
    "critique": "<concise explanation>",
    "retry_guidance": [
        "<instruction 1>",
        "<instruction 2>"
    ],
    "should_retry": <true|false>
}}
</json>

==================================================
CRITIQUE RULES
==================================================

Your job is NOT to fix the code.

Your job IS to:
- explain why the attempted patch is semantically invalid
- identify intent violations
- identify bypass fixes
- identify fabricated values
- identify unnecessary logic additions
- guide a future repair attempt

Avoid generic criticism.

GOOD critique:
- "The patch invents a value for an undefined variable."
- "The patch bypasses division by zero instead of tracing why the divisor became zero."
- "The patch changes the accessed index instead of addressing the missing data."

BAD critique:
- "The patch is incorrect."
- "The fix did not work."

==================================================
RETRY POLICY
==================================================

Set should_retry=false if:
- the correct value cannot be inferred safely
- the program intent is fundamentally ambiguous
- additional context would be required for a valid repair

Set should_retry=true if:
- a better semantic repair strategy may still exist
- the previous attempt used an obviously invalid strategy
- the repair failed due to over-aggressive modification

==================================================
FAILURE CATEGORY EXAMPLES
==================================================

Use short snake_case categories like:
- invented_value
- bypass_fix
- semantic_change
- invalid_index_repair
- unsupported_assumption
- unnecessary_logic
- ambiguous_program_intent

==================================================
CONTEXT
==================================================

Root cause:
{context["analysis"]["root_cause"]}

Analyzer reasoning:
{context["analysis"]["reasoning"]}

Original code:
{context["code"]}

Patched code:
{context["fix"]["patched_code"]}

Traceback:
{context["traceback"]}

Execution stdout:
{context["execution_result"]["stdout"]}

Execution success:
{context["execution_success"]}

Evaluator reasoning:
{context["evaluation"]["reasoning"]}

Intent preserved:
{context["evaluation"]["intent_preserved"]}

Root cause fixed:
{context["evaluation"]["root_cause_fixed"]}

Minimal fix:
{context["evaluation"]["minimal_fix"]}

Introduced regression:
{context["evaluation"]["introduced_regression"]}
""".strip()

    # ------------------------------------------------------------------
    # Parse + validate
    # ------------------------------------------------------------------

    def _parse(self, raw: str, latency: float) -> dict:

        parsed = self.extract_json(raw)

        required = {
            "failure_type",
            "critique",
            "retry_guidance",
            "should_retry",
        }

        missing = required - parsed.keys()

        if missing:
            raise ValueError(
                f"Missing critique keys: {missing}"
            )

        if not isinstance(parsed["failure_type"], str):
            raise ValueError("failure_type must be a string")

        if not isinstance(parsed["critique"], str):
            raise ValueError("critique must be a string")

        if not isinstance(parsed["retry_guidance"], list):
            raise ValueError("retry_guidance must be a list")

        if not isinstance(parsed["should_retry"], bool):
            raise ValueError("should_retry must be boolean")

        return parsed

    # ------------------------------------------------------------------
    # Entry point
    # ------------------------------------------------------------------

    def run(self, context: dict) -> dict:

        run_id = context.get("run_id", "unknown")

        logger.info(f"[Run {run_id}] CritiqueAgent started")

        critique = self._run_with_retries(
            run_id=run_id,
            label="Critique",
            system_prompt=self._SYSTEM_PROMPT,
            user_prompt=self._build_prompt(context),
            parse_and_validate=self._parse,
            generate_kwargs={
                "do_sample": False,
                "temperature": 0.0,
            },
        )

        if critique is None:

            logger.error(
                f"[Run {run_id}] CritiqueAgent failed after retries"
            )

            return {
                "failure_type": "critique_generation_failed",
                "critique": (
                    "The critique agent failed to generate "
                    "valid feedback."
                ),
                "retry_guidance": [],
                "should_retry": False,
            }

        logger.info(
            f"[Run {run_id}] Critique result: {critique}"
        )

        return critique
