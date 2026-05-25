import os
import tempfile
import subprocess
from utils.logger import setup_logger

logger = setup_logger()

class SandboxRunner:

    def execute(self, run_id: str, code:str):

        logger.info(f"[Run {run_id}] Sandbox execution started")

        with tempfile.NamedTemporaryFile(
            suffix=".py",
            delete=False,
            mode='w'
        ) as temp_file:
            
            temp_file.write(code)
            temp_path = temp_file.name

        try:
            result = subprocess.run(
                ["python", temp_path],
                capture_output=True,
                text=True,
                timeout=5
            )

            logger.info(f"[Run {run_id}] Sandbox execution completed")
            logger.info(f"[Run {run_id}] Execution result: {result}")

            return {
                "success": result.returncode == 0,
                "stdout": result.stdout,
                "stderr": result.stderr,
            }
        
        
        except Exception as e:
            logger.error(f"[Run {run_id}] Execution failed in sandbox: {e}")
            return {
                "success": False,
                "stdout": "",
                "stderr": str(e),
            }
        
        finally:
            os.remove(temp_path)
