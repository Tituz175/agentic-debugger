import re
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
You are an expert Python program repair agent.

Your goal is to minimally repair buggy Python programs.

Requirements:
- Preserve original intent.
- Make the smallest possible change.
- Return ONLY valid JSON.

Never:
- add try/except blocks
- invent values
- add defensive programming
- introduce fallback logic
- perform unnecessary refactors
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

CRITICAL RULE:
When the error is caused by a wrong operator, wrong variable name, or
wrong boolean/comparison value, the ONLY correct fix is to restore the
original operator/name/value. Do NOT change surrounding code to work
around the bad value. Do NOT change loop ranges, conditions, or logic
to avoid the error — find the one character/token that is wrong and
fix ONLY that.

Forbidden behaviors:
- inventing arbitrary values
- bypassing execution with guards  
- changing indices to unrelated valid values
- suppressing the error with try/except
"""
        
        
        return f"""
You are repairing a buggy Python program.

Your task is to generate the SMALLEST possible fix that resolves the bug
while preserving the original program intent.

Return ONLY valid JSON.

Required format:

{{
  "patched_code": "<FULL corrected Python program>",
  "explanation": "<brief explanation>"
}}

Example:

{{
  "patched_code": "def add(a, b):\\n    return a + b",
  "explanation": "Replaced subtraction with addition."
}}

STRICT OUTPUT RULES:

- Output ONLY a JSON object.
- Do NOT use markdown.
- Do NOT use code fences.
- Do NOT wrap JSON in <json> tags.
- Do NOT include commentary before or after the JSON.
- patched_code must contain the ENTIRE corrected program.
- explanation must be a single concise sentence.

REPAIR RULES:

- Make the smallest possible change.
- Preserve original intent.
- Do not invent arbitrary values.
- Do not add try/except.
- Do not add fallback logic.
- Do not suppress the error.
- Do not refactor unrelated code.
- Do not rewrite the entire solution.

==================================================
BUG INFORMATION
==================================================

Bug Type:       {context["analysis"]["root_cause"]}
Reason:         {context["analysis"]["reasoning"]}
Failing Line:   {context["analysis"]["error_line"]}

Original Code:
{context["code"]}

{retry_section}
""".strip()

    # ------------------------------------------------------------------
    # parse_and_validate callback
    # ------------------------------------------------------------------

    def _parse(self, raw: str, latency: float) -> dict:
        """
        Parse fixer output.

        Expected format:

        {
            "patched_code": "...",
            "explanation": "..."
        }
        """


        if not raw.strip().endswith("}"):
            raise ValueError(
                "Output appears truncated before JSON completed."
            )

        try:
            parsed = self.extract_json(raw)
        except Exception:

            json_match = re.search(
                r"\{.*\}",
                raw,
                re.DOTALL,
            )

            if not json_match:
                raise

            parsed = self.extract_json(
                json_match.group(0)
            )

        if "patched_code" not in parsed:
            raise ValueError("Missing 'patched_code' key")

        if "explanation" not in parsed:
            raise ValueError("Missing 'explanation' key")

        patched_code = parsed["patched_code"]

        if not isinstance(patched_code, str):
            raise ValueError("patched_code must be a string")

        patched_code = patched_code.strip()

        if not patched_code:
            raise ValueError("patched_code is empty")

        try:
            compile(patched_code, "<patch>", "exec")
        except SyntaxError as e:
            raise ValueError(
                f"Patch failed compile check: {e}"
            )

        return {
            "patched_code": patched_code,
            "explanation": parsed["explanation"],
            "fixer_latency": f"{latency:.4f}s",
            "parse_success": True,
        }

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
            generate_kwargs={"max_new_tokens": 8192},  # allow longer output for the patch
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
