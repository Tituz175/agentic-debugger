import json
import re
import time

from utils.logger import setup_logger

logger = setup_logger()


class BaseAgent:
    """
    Shared foundation for all debugger agents.

    Provides:
    - JSON extraction from <json> tags
    - A retry loop that rebuilds the prompt on failure
    - Consistent latency measurement
    """

    max_retries: int = 2

    # Subclasses override this to append to user_prompt on retry.
    _retry_suffix = """

Your previous response failed validation.

IMPORTANT:
- Return ONLY valid JSON inside <json> tags
- No markdown, no code fences, no extra text
- All string values must have properly escaped newlines (\\n) and quotes
"""

    def __init__(self, llm):
        self.llm = llm

    # ------------------------------------------------------------------
    # Shared utilities
    # ------------------------------------------------------------------

    def extract_json(self, text: str) -> dict:
        """
        Extract and parse JSON wrapped in <json>...</json> tags.
        Raises ValueError if the block is missing or malformed.
        """
        text = text.strip()

        # Raw JSON
        if text.startswith("{"):
            return json.loads(text)

        # Legacy <json> wrapper
        match = re.search(
            r"<json>(.*?)</json>",
            text,
            re.DOTALL
        )

        if not match:
            raise ValueError(
                f"No JSON object found in output:\n{text[:300]}"
            )

        return json.loads(match.group(1).strip())

    def _timed_generate(self, run_id: str, label: str, **kwargs) -> tuple[str, float]:
        """
        Call self.llm.generate, return (output, latency_seconds).
        kwargs are passed through to llm.generate.
        """
        start = time.perf_counter()
        output = self.llm.generate(**kwargs)
        latency = time.perf_counter() - start
        logger.info(f"[Run {run_id}] {label} latency: {latency:.4f}s")
        logger.debug(f"[Run {run_id}] {label} raw output:\n{output}")
        return output, latency

    def _run_with_retries(
        self,
        run_id: str,
        label: str,
        system_prompt: str,
        user_prompt: str,
        parse_and_validate,   # callable(raw_output) -> dict, raises on failure
        generate_kwargs: dict | None = None,
    ) -> dict | None:
        """
        Generic retry loop used by all agents.

        - Calls llm.generate up to self.max_retries times.
        - On each failure, appends _retry_suffix to user_prompt (only once).
        - Returns the parsed result dict, or None if all attempts fail.

        parse_and_validate must raise an exception on bad output;
        it should return the final result dict on success.
        """
        generate_kwargs = generate_kwargs or {}
        last_error = None
        retry_prompt = user_prompt  # starts clean, suffix added after first failure

        for attempt in range(self.max_retries):
            logger.info(f"[Run {run_id}] {label} attempt {attempt + 1}/{self.max_retries}")
            try:
                raw, latency = self._timed_generate(
                    run_id,
                    label,
                    system_prompt=system_prompt,
                    user_prompt=retry_prompt,
                    **generate_kwargs,
                )
                result = parse_and_validate(raw, latency)
                logger.info(f"[Run {run_id}] {label} succeeded on attempt {attempt + 1}")
                return result

            except Exception as e:
                last_error = str(e)
                logger.error(f"[Run {run_id}] {label} attempt {attempt + 1} failed: {e}")

                # Append suffix only once (on the first failure)
                if attempt == 0:
                    retry_prompt = user_prompt + self._retry_suffix

        logger.error(f"[Run {run_id}] {label} failed after {self.max_retries} attempts")
        return None