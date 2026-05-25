from agents.base_agent import BaseAgent
from utils.logger import setup_logger

logger = setup_logger() 


class EvaluatorAgent(BaseAgent):

    def run(self, context: dict) -> dict:
        # Implement the logic to evaluate the effectiveness of the fixes
        # For example, you can run tests or compare outputs before and after the fix

        run_id = context.get("run_id", "unknown")

        logger.info(f"[Run {run_id}] EvaluatorAgent started")

        success = context.get("execution_success", False)

        evaluation = {
            "passed": success,
            "score": 1.0 if success else 0.0
        }

        logger.info(f"[Run {run_id}] Evaluation completed")
        logger.info(f"[Run {run_id}] Evaluation result: {evaluation}")

        return evaluation
