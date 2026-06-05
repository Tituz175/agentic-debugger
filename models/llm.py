import torch
from transformers import AutoTokenizer, AutoModelForCausalLM

from computation.logger import setup_logger

logger = setup_logger()


class LLMModel:
    """
    Thin wrapper around a HuggingFace causal LM.

    Notes
    -----
    - Uses torch_dtype (not dtype) for from_pretrained.
    - Unpacks tokenizer output correctly so attention_mask is passed to generate.
    - max_new_tokens is generous for fixer (full program); tighter for analyzer/evaluator.
    - Caller can override any generate kwarg via **kwargs.
    """

    DEFAULT_MAX_NEW_TOKENS = 4096

    def __init__(self, model_name: str):
        logger.info(f"Loading model: {model_name}")

        self.tokenizer = AutoTokenizer.from_pretrained(model_name)

        self.model = AutoModelForCausalLM.from_pretrained(
            model_name,
            torch_dtype=torch.float16,   # was: dtype= (not a valid kwarg)
            device_map="auto",
        )

        self.model.eval()
        logger.info("Model loaded and set to eval mode")

    def generate(
        self,
        system_prompt: str,
        user_prompt: str,
        do_sample: bool = True,
        temperature: float = 0.1,
        top_p: float = 0.9,
        max_new_tokens: int = DEFAULT_MAX_NEW_TOKENS,
        **kwargs,                         # forward any extra args (e.g. repetition_penalty)
    ) -> str:
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user",   "content": user_prompt},
        ]

        # apply_chat_template with return_dict=True gives us input_ids + attention_mask
        inputs = self.tokenizer.apply_chat_template(
            messages,
            add_generation_prompt=True,
            return_tensors="pt",
            return_dict=True,            # was: bare tensor — attention_mask was dropped
        ).to(self.model.device)

        # When do_sample=False, temperature/top_p must not be passed —
        # HuggingFace warns and may error depending on version.
        sample_kwargs = {}
        if do_sample:
            sample_kwargs["temperature"] = temperature
            sample_kwargs["top_p"]       = top_p

        with torch.inference_mode():
            outputs = self.model.generate(
                **inputs,                # unpacks input_ids + attention_mask
                max_new_tokens=max_new_tokens,
                do_sample=do_sample,
                pad_token_id=self.tokenizer.eos_token_id,
                **sample_kwargs,
                **kwargs,
            )

        # Slice off the prompt tokens — decode only the generated portion
        prompt_len = inputs["input_ids"].shape[1]
        generated_ids = outputs[0][prompt_len:]

        response = self.tokenizer.decode(
            generated_ids,
            skip_special_tokens=True,
            clean_up_tokenization_spaces=False,
        )

        return response.strip()
