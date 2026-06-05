import os
import sys
import tempfile
import subprocess

from computation.logger import setup_logger

logger = setup_logger()


class SandboxRunner:
    """
    Executes a Python code string in an isolated subprocess.

    Safety notes
    ------------
    - Uses sys.executable so the sandbox runs under the same Python
      environment as the orchestrator (not whatever `python` resolves to
      on PATH, which may be Python 2 or a different venv).
    - Writes to a NamedTemporaryFile, always cleans up in finally.
    - Caps stdout/stderr to avoid memory issues with runaway output.
    """

    MAX_OUTPUT_CHARS = 4_000
    DEFAULT_TIMEOUT  = 5     # seconds

    def execute(
        self,
        run_id: str,
        code: str,
        timeout: int = DEFAULT_TIMEOUT,
    ) -> dict:

        if not code or not code.strip():
            logger.warning(f"[Run {run_id}] Sandbox received empty code — skipping")
            return {
                "success": False,
                "stdout":  "",
                "stderr":  "No code to execute.",
            }

        logger.info(f"[Run {run_id}] Sandbox execution started")

        temp_path = None
        try:
            with tempfile.NamedTemporaryFile(
                suffix=".py",
                delete=False,
                mode="w",
                encoding="utf-8",
            ) as tmp:
                tmp.write(code)
                temp_path = tmp.name

            result = subprocess.run(
                [sys.executable, temp_path],   # was: ["python", ...] — wrong env
                capture_output=True,
                text=True,
                timeout=timeout,
            )

            stdout = result.stdout[: self.MAX_OUTPUT_CHARS]
            stderr = result.stderr[: self.MAX_OUTPUT_CHARS]
            success = result.returncode == 0

            logger.info(f"[Run {run_id}] Sandbox finished — returncode={result.returncode}")
            if stderr:
                logger.warning(f"[Run {run_id}] Sandbox stderr:\n{stderr}")

            return {
                "success": success,
                "stdout":  stdout,
                "stderr":  stderr,
            }

        except subprocess.TimeoutExpired:
            logger.error(f"[Run {run_id}] Sandbox timed out after {timeout}s")
            return {
                "success": False,
                "stdout":  "",
                "stderr":  f"Execution timed out after {timeout}s.",
            }

        except Exception as e:
            logger.error(f"[Run {run_id}] Sandbox unexpected error: {e}")
            return {
                "success": False,
                "stdout":  "",
                "stderr":  str(e),
            }

        finally:
            if temp_path and os.path.exists(temp_path):
                os.remove(temp_path)
