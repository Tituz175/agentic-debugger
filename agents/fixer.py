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

        self.system_prompt = """
You are an advanced autonomous Python debugging agent.

You specialize in:
- traceback analysis
- minimal code repair
- semantic preservation
- defensive programming
- generating executable fixes

You must preserve original program intent whenever possible.
Avoid unnecessary rewrites and unrelated behavioral changes.
"""

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
You are an expert Python repair engine.

Your task is to minimally repair the provided Python program.

You MUST respond ONLY with valid XML-style JSON tags in this exact structure:

ABSOLUTE OUTPUT RULES:

- Output NOTHING before
- Output NOTHING after
- Do NOT use markdown
- Do NOT use code fences
- Response must be valid JSON inside the tags
- patched_code must contain executable Python code
- Escape newlines as \n
- Escape quotes correctly

REPAIR RULES:

- Make the SMALLEST possible fix
- Preserve the original intent exactly
- Modify as few tokens as possible
- Prefer changing literals/indices/operators over adding logic
- Do NOT add defensive programming
- Do NOT add try/except
- Do NOT add conditionals unless absolutely required
- Do NOT add fallback behaviors
- Do NOT invent arbitrary values
- Do NOT refactor
- Do NOT rename variables
- Do NOT change formatting unnecessarily

GOOD FIX EXAMPLES:

Example 1:
Buggy:
x = "5"
y = 2
print(x + y)

Good Fix:
print(x + str(y))

Bad Fix:
if isinstance(y, int):
print(x + str(y))

Example 2:
Buggy:
numbers = [1,2,3]
print(numbers[5])

Good Fix:
print(numbers[2])

Bad Fix:
if len(numbers) > 5:
print(numbers[5])
else:
print("Index out of range")

Example 3:
Buggy:
for i in range(5)
print(i)

Good Fix:
for i in range(5):
print(i)

Bug Type:
{context["analysis"]["root_cause"]}

Reason:
{context["analysis"]["reasoning"]}

Failing Line:
{context["analysis"]["error_line"]}

Original Code:
{context["code"]}
"""

    def run(self, context: dict) -> dict:

        run_id = context.get("run_id", "unknown")

        logger.info(
            f"[Run {run_id}] FixerAgent started"
        )

        system_prompt = self.system_prompt
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
