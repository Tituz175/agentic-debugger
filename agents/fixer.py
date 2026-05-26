import json
import re
import time

from agents.base_agent import BaseAgent
from models.llm import LLMModel
from utils.logger import setup_logger


logger = setup_logger()


class FixerAgent(BaseAgent):

    def __init__(self):

        self.llm = LLMModel(
            "meta-llama/Llama-3.2-3B-Instruct"
        )

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

        code = context["code"].strip()

        analysis = context["analysis"]

        return f"""
You are an expert software repair agent.

Your task is to fix the provided Python code.

Return ONLY valid JSON wrapped inside <json> tags.

Format:

<json>
{{
    "patched_code": "...",
    "explanation": "..."
}}
</json>

Rules:
- Preserve original behavior when possible
- Fix only the identified issue
- Make the smallest possible code change
- Return executable Python code
- Return ONLY valid JSON
- Do not include markdown
- Do not include explanations outside JSON

Original Code:
{code}

Analysis:
- Root Cause: {analysis["root_cause"]}
- Error Line: {analysis["error_line"]}
- Reasoning: {analysis["reasoning"]}

Traceback:
{context["traceback"]}
"""

    def run(self, context: dict) -> dict:

        run_id = context.get("run_id", "unknown")

        logger.info(
            f"[Run {run_id}] FixerAgent started"
        )

        prompt = self.build_prompt(context)

        last_error = None

        for attempt in range(self.max_retries):

            try:

                logger.info(
                    f"[Run {run_id}] "
                    f"Fixer attempt {attempt + 1}"
                )

                start_time = time.perf_counter()

                output = self.llm.generate(prompt)

                latency = (
                    time.perf_counter() - start_time
                )

                print(f"[Run {run_id}] LLM output:\n{output}")

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

                prompt += """

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