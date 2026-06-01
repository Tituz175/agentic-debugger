from agents.base_agent import BaseAgent
from utils.logger import setup_logger

logger = setup_logger()


class FixerAgent(BaseAgent):
    """
    Generates a minimal patch for a Python bug identified by the AnalyzerAgent.

    Contract
    --------
    - Returns the smallest possible change to make the code run correctly.
    - Never adds try/except, defensive checks, or arbitrary fallback values.
    - Validates the patch compiles before returning it.
    """

    max_retries = 2

    _SYSTEM_PROMPT = """
You are an advanced autonomous Python debugging agent.

Your goal is to minimally repair buggy Python programs.

Preserve original intent whenever possible.

Avoid:
- arbitrary values
- unnecessary rewrites
- defensive programming
- try/except blocks
- fallback logic
""".strip()
    
    def __init__(self, llm):
        super().__init__(llm)

    # ------------------------------------------------------------------
    # Prompt construction
    # ------------------------------------------------------------------

    def _build_prompt(self, context: dict) -> str:
        retry_section = ""

        # ----------------------------------------------------------
        # If a previous repair failed evaluation,
        # inject critique-aware retry guidance
        # ----------------------------------------------------------
        if "critique" in context:

            retry_section = f"""

==================================================
PREVIOUS PATCH FAILED EVALUATION
==================================================

Failed patch:
{context["fix"]["patched_code"]}

Evaluator reasoning:
{context["evaluation"]["reasoning"]}

Failure type:     {context["critique"]["failure_type"]}
Critique:         {context["critique"]["critique"]}
Retry guidance:   {context["critique"]["retry_guidance"]}

You MUST generate a DIFFERENT repair strategy.
DO NOT repeat the failed patch above.

Forbidden behaviors:
- inventing arbitrary values
- bypassing execution with guards  
- changing indices to unrelated valid values
- suppressing the error with try/except
"""
        
        
        return f"""
Fix the Python program below.

Return ONLY:

<json>
{{
  "patched_code": "...",
  "explanation": "..."
}}
</json>

RULES:
- patched_code must contain the FULL corrected program.
- Make the SMALLEST possible change.
- Preserve original intent.
- Do not add try/except.
- Do not invent arbitrary values.
- Do not add fallback behavior.
- Do not refactor unrelated code.

IMPORTANT:
- Output valid JSON only.
- Do not use markdown.
- Do not include commentary outside the JSON block.

Bug Type:
{context["analysis"]["root_cause"]}

Reason:
{context["analysis"]["reasoning"]}

Failing Line:
{context["analysis"]["error_line"]}

Original Code:
{context["code"]}

{retry_section}
""".strip()

    # ------------------------------------------------------------------
    # parse_and_validate callback
    # ------------------------------------------------------------------

    def _parse(self, raw: str, latency: float) -> dict:
        parsed = self.extract_json(raw)

        required = {"patched_code", "explanation"}
        missing = required - parsed.keys()
        if missing:
            raise ValueError(f"Missing keys in fixer output: {missing}")

        patched_code = parsed["patched_code"]
        if not patched_code or not patched_code.strip():
            raise ValueError("patched_code is empty")

        # Compile-check before accepting the patch
        try:
            compile(patched_code, "<patch>", "exec")
        except SyntaxError as e:
            raise ValueError(f"Patch failed compile check: {e}")

        parsed["fixer_latency"] = f"{latency:.4f}s"
        parsed["parse_success"] = True
        return parsed

    # ------------------------------------------------------------------
    # Entry point
    # ------------------------------------------------------------------

    def run(self, context: dict) -> dict:
        run_id = context.get("run_id", "unknown")
        logger.info(f"[Run {run_id}] FixerAgent started")

        result = self._run_with_retries(
            run_id=run_id,
            label="Fixer",
            system_prompt=self._SYSTEM_PROMPT,
            user_prompt=self._build_prompt(context),
            parse_and_validate=self._parse,
        )

        if result is None:
            logger.error(f"[Run {run_id}] FixerAgent returning failure sentinel")
            return {
                "patched_code": "",
                "explanation": "All retry attempts failed.",
                "parse_success": False,
            }

        logger.info(f"[Run {run_id}] FixerAgent completed")
        return result
