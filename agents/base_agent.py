import re
import json 
from abc import ABC, abstractmethod


class BaseAgent(ABC):

    @abstractmethod
    def run(self, context: dict) -> dict:
        pass

class BaseAgent:
    def extract_json(self, text: str) -> dict:
        match = re.search(r"<json>(.*?)</json>", text, re.DOTALL)
        if not match:
            raise ValueError("No JSON block found")
        return json.loads(match.group(1).strip())

