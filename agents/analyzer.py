from agents.base_agent import BaseAgent
from computation.logger import setup_logger

logger = setup_logger()


class AnalyzerAgent(BaseAgent):
    """
    Analyzes a Python traceback and identifies:
    - The exception type (root_cause)
    - The failing line number (error_line)
    - A concise explanation (reasoning)
    """

    max_retries = 2

    _SYSTEM_PROMPT = (
        "You are an expert Python static analysis engine. "
        "Your only job is to identify the root cause of a Python error. "
        "Never suggest fixes."
    )

    def __init__(self, llm):
        super().__init__(llm)

    # ------------------------------------------------------------------
    # Prompt construction
    # ------------------------------------------------------------------

    @staticmethod
    def _add_line_numbers(code: str) -> str:
        lines = code.strip().split("\n")
        return "\n".join(f"{i + 1}: {line}" for i, line in enumerate(lines))

    def _build_prompt(self, formatted_code: str, traceback: str) -> str:
        return f"""
You are a Python static analysis engine.

Analyze the code and traceback below.

Your task:
1. Identify the root cause (use the actual exception class name).
2. Identify the exact failing line number as an integer.
3. Explain the bug in one or two sentences.

Return ONLY this structure — nothing before, nothing after:

<json>
{{
    "root_cause": "<ExceptionType>",
    "error_line": <integer>,
    "reasoning": "<concise explanation>"
}}
</json>

STRICT RULES:
- Output ONLY the <json> block.
- No markdown, no code fences, no extra text.
- error_line must be an integer matching a line in the numbered code.
- reasoning must be concise (≤2 sentences).
- root_cause must be the exception class name (e.g. TypeError, NameError).
- Do NOT suggest fixes.

Code:
{formatted_code}

Traceback:
{traceback}
"""

    # ------------------------------------------------------------------
    # parse_and_validate callback for the retry loop
    # ------------------------------------------------------------------

    def _parse(self, raw: str, latency: float) -> dict:
        parsed = self.extract_json(raw)

        # Schema validation
        required = {"root_cause", "error_line", "reasoning"}
        missing = required - parsed.keys()
        if missing:
            raise ValueError(f"Missing keys in analyzer output: {missing}")

        if not isinstance(parsed["error_line"], int):
            raise ValueError(
                f"error_line must be int, got {type(parsed['error_line'])}"
            )

        parsed["analyzer_latency"] = f"{latency:.4f}s"
        parsed["parse_success"] = True
        return parsed

    # ------------------------------------------------------------------
    # Entry point
    # ------------------------------------------------------------------

    def run(self, context: dict) -> dict:
        run_id = context.get("run_id", "unknown")
        logger.info(f"[Run {run_id}] AnalyzerAgent started")

        formatted_code = self._add_line_numbers(context["code"])
        context["formatted_code"] = formatted_code

        result = self._run_with_retries(
            run_id=run_id,
            label="Analyzer",
            system_prompt=self._SYSTEM_PROMPT,
            user_prompt=self._build_prompt(formatted_code, context["traceback"]),
            parse_and_validate=self._parse,
        )

        if result is None:
            logger.error(f"[Run {run_id}] AnalyzerAgent returning failure sentinel")
            return {
                "root_cause": "Analysis failed",
                "error_line": -1,
                "reasoning": "All retry attempts failed.",
                "parse_success": False,
            }

        logger.info(f"[Run {run_id}] AnalyzerAgent completed: {result['root_cause']}")
        return result
