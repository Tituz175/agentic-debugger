import torch
from transformers import AutoTokenizer, AutoModelForCausalLM

class LLMModel:
    def __init__(self, model_name):
        self.tokenizer = AutoTokenizer.from_pretrained(model_name)

        self.model = AutoModelForCausalLM.from_pretrained(
            model_name,
            dtype=torch.float16,
            device_map="auto"
        )


    def generate(self, prompt):
        messages = [
            {"role": "system", "content": "You are a helpful assistant that helps debug code."},
            {"role": "user", "content": prompt}
        ]

        inputs = self.tokenizer.apply_chat_template(
            messages,
            add_generation_prompt=True,
            return_tensors="pt"
        ).to(self.model.device)

        outputs = self.model.generate(
            **inputs,
            max_new_tokens=512,
            do_sample=True,
            temperature=0.1,
            top_p=0.9
        )

        response = self.tokenizer.decode(
            outputs[0][inputs.input_ids.shape[1]:], 
            skip_special_tokens=True
        )

        return response.strip()
