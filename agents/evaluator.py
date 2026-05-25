from agents.base_agent import BaseAgent


class EvaluatorAgent(BaseAgent):

    def run(self, context: dict) -> dict:
        # Implement the logic to evaluate the effectiveness of the fixes
        # For example, you can run tests or compare outputs before and after the fix

        success = context.get("execution_success", False)

        evaluation = {
            "passed": success,
            "score": 1.0 if success else 0.0
        }

        return evaluation
