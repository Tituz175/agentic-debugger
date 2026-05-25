from agents.base_agent import BaseAgent


class AnalyzerAgent(BaseAgent):

    def run(self, context: dict) -> dict:
        # Implement the logic to analyze the code and identify potential issues
        # For example, you can use static analysis tools or custom heuristics

        code = context.get("code", "")
        traceback = context.get("traceback", "")

        analysis = {
            "root_cause": "Possible division by zero.",
            "suspected_lines": [3],
            "reasoning": traceback
        }

        return analysis
