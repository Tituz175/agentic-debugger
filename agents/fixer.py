import json
import re
import time

from agents.base_agent import BaseAgent
from utils.logger import setup_logger


logger = setup_logger()


class FixerAgent(BaseAgent):

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

    def validate_patch(self, patched_code: str):

        """
        Validate generated Python code before execution.
        """

        compile(
            patched_code,
            "<string>",
            "exec"
        )

    def build_prompt(self, context: dict) -> str:

        return f"""
You are an expert software repair agent.

Your task is to fix the provided Python code.

Return ONLY valid JSON wrapped inside <json> tags.

Rules:
- Do NOT use markdown
- Do NOT use triple backticks
- Do NOT use triple quotes
- patched_code must be a single JSON string
- Escape newlines using \n

Format:

<json>
{{
    "patched_code": "...",
    "explanation": "..."
}}
</json>

Rules:
- Return the COMPLETE corrected program
- Preserve all existing code unless necessary to modify
- Do not omit variable definitions
- Do not return partial snippets
- Fix only the identified issue
- Return executable Python code
- Do not include markdown formatting

Original Code:
{context["code"]}

Code With Line Numbers:
{context["formatted_code"]}

Detected Error:
{context["analysis"]["root_cause"]}

Error Line:
{context["analysis"]["error_line"]}

Reasoning:
{context["analysis"]["reasoning"]}
"""

    def run(self, context: dict) -> dict:

        run_id = context.get("run_id", "unknown")

        logger.info(
            f"[Run {run_id}] FixerAgent started"
        )

        system_prompt = "You are an expert software repair agent."
        user_prompt = self.build_prompt(context)

        last_error = None

        for attempt in range(self.max_retries):

            try:

                logger.info(
                    f"[Run {run_id}] "
                    f"Fixer attempt {attempt + 1}"
                )

                start_time = time.perf_counter()

                output = self.llm.generate(system_prompt, user_prompt)

                latency = (
                    time.perf_counter() - start_time
                )

                logger.info(
                    f"[Run {run_id}] "
                    f"Fixer latency: {latency:.4f}s"
                )

                logger.info(
                    f"[Run {run_id}] "
                    f"Raw LLM output:\n{output}"
                )

                parsed_output = self.extract_json(output)

                self.validate_patch(
                    parsed_output["patched_code"]
                )

                parsed_output["fixer_latency"] = (
                    f"{latency:.4f}s"
                )

                parsed_output["parse_success"] = True

                logger.info(
                    f"[Run {run_id}] "
                    f"Patch validation successful"
                )

                logger.info(
                    f"[Run {run_id}] "
                    f"JSON extraction successful"
                )

                return parsed_output

            except Exception as e:

                last_error = str(e)

                logger.error(
                    f"[Run {run_id}] "
                    f"Fixer attempt failed: {e}"
                )

                user_prompt += """

Your previous response failed validation.

IMPORTANT:
- Return ONLY valid JSON
- Wrap JSON inside <json> tags
- Return executable Python code
- Do not include markdown
- Do not include explanations outside JSON
"""

        logger.error(
            f"[Run {run_id}] "
            f"FixerAgent failed after retries"
        )

        return {
            "patched_code": "",
            "explanation": last_error,
            "parse_success": False
        }
