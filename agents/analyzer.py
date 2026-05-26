import json
import re
import time

from agents.base_agent import BaseAgent
from utils.logger import setup_logger


logger = setup_logger()


class AnalyzerAgent(BaseAgent):

    def __init__(self, llm):

        self.llm = llm

        self.max_retries = 2

    def extract_json(self, text: str) -> dict:

        """
        Extract JSON content wrapped inside <json> tags.
        """

        match = re.search(
            r"<json>(.*?)</json>",
            text,
            re.DOTALL
        )

        if not match:
            raise ValueError("No JSON block found")

        json_text = match.group(1).strip()

        return json.loads(json_text)
    
    def add_line_numbers(self, code: str) -> str:

        lines = code.strip().split("\n")

        numbered_lines = [
            f"{idx + 1}: {line}"
            for idx, line in enumerate(lines)
        ]

        return "\n".join(numbered_lines)
    

    def build_prompt(self, context: dict) -> str:

        return f"""
You are an expert software debugging agent.

Analyze the following Python code and traceback.

Return ONLY valid JSON wrapped inside <json> tags.

Format:

<json>
{{
    "root_cause": "...",
    "error_line": integer,
    "reasoning": "..."
}}
</json>

Rules:
- Do not include explanations outside the tags
- Do not include markdown
- suspected_lines must contain integers
- Return valid JSON only

Code:
{context["formatted_code"]}

Traceback:
{context["traceback"]}
"""

    def run(self, context: dict) -> dict:

        run_id = context.get("run_id", "unknown")

        logger.info(
            f"[Run {run_id}] AnalyzerAgent started"
        )

        context["formatted_code"] = self.add_line_numbers(
            context["code"]
        )

        system_prompt = "You are a helpful assistant that helps debug code."
        user_prompt = self.build_prompt(context)

        last_error = None

        for attempt in range(self.max_retries):

            try:

                logger.info(
                    f"[Run {run_id}] Analyzer attempt {attempt + 1}"
                )

                start_time = time.perf_counter()

                output = self.llm.generate(system_prompt, user_prompt)

                latency = (
                    time.perf_counter() - start_time
                )

                logger.info(
                    f"[Run {run_id}] Analysis latency: "
                    f"{latency:.4f}s"
                )

                logger.info(
                    f"[Run {run_id}] Raw LLM output:\n{output}"
                )

                parsed_output = self.extract_json(output)

                parsed_output["analyzer_latency"] = (
                    f"{latency:.4f}s"
                )

                parsed_output["parse_success"] = True

                logger.info(
                    f"[Run {run_id}] JSON extraction successful"
                )

                return parsed_output

            except Exception as e:

                last_error = str(e)

                logger.error(
                    f"[Run {run_id}] "
                    f"Analyzer attempt failed: {e}"
                )

                user_prompt += """

Your previous response failed validation.

IMPORTANT:
- Return ONLY valid JSON
- Wrap JSON in <json> tags
- Do not include markdown
- Do not include explanations
"""

        logger.error(
            f"[Run {run_id}] "
            f"AnalyzerAgent failed after retries"
        )

        return {
            "root_cause": "Analysis failed",
            "suspected_lines": [],
            "reasoning": last_error,
            "parse_success": False
        }
