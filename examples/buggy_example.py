from datasets import load_dataset

dataset = load_dataset("openai/openai_humaneval", split="test")
print(dataset[0])

sample = dataset[0]

# 1. Create buggy version
buggy_code = sample["prompt"] + sample["canonical_solution"].replace("<", "<=", 1)

# 2. Feed to your debugger agent
# fixed_code = your_agent(buggy_code)

# 3. Verify with tests
print("Prompt:\n", sample["prompt"])
print("Buggy code:\n", buggy_code)
print("Tests:\n", sample["test"])
