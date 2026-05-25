import os
import tempfile
import subprocess


class SandboxRunner:

    def execute(self, code:str):
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
            return {
                "success": result.returncode == 0,
                "stdout": result.stdout,
                "stderr": result.stderr,
            }
        
        except Exception as e:
            return {
                "success": False,
                "stdout": "",
                "stderr": str(e),
            }
        
        finally:
            os.remove(temp_path)
