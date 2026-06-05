# Agentic Debugger

> Automated Program Repair through collaborative AI agents — Analyze, Fix, Execute, Evaluate, Critique, Retry.

**156/164 benchmark tasks repaired · 95.1% PASS@1 · avg score 0.940**

---

## Overview

Most AI coding systems stop at *"here's a patch."* But software debugging is rarely that simple.

Human developers don't immediately jump to the correct fix. They investigate the problem, formulate hypotheses, test those hypotheses, evaluate outcomes, revise their reasoning, and iterate until they arrive at a solution that not only removes the error but preserves the intended behavior of the software.

**Agentic Debugger** is an experimental framework for Automated Program Repair that decomposes debugging into a collection of specialized, collaborating AI agents. Rather than relying on a single prompt-to-patch pipeline, the system mimics the iterative reasoning workflow a developer naturally performs during debugging.

The system is powered by **Qwen2.5-Coder-32B-AWQ** running locally and evaluated against a mutation-based benchmark built on top of the **HumanEval** dataset.

---

## Architecture

The pipeline consists of five specialized agents coordinated by a central orchestrator:

```
┌─────────────┐
│   Analyzer  │  Identifies root cause from traceback + source
└──────┬──────┘
       │
┌──────▼──────┐
│    Fixer    │  Generates minimal patch preserving original intent
└──────┬──────┘
       │
┌──────▼──────┐
│   Sandbox   │  Executes patch in isolated subprocess
│   Executor  │
└──────┬──────┘
       │
┌──────▼──────┐
│  Evaluator  │  Scores repair: execution + heuristics + LLM signals
└──────┬──────┘
       │ fail
┌──────▼──────┐
│   Critique  │  Analyzes failure, generates targeted retry guidance
└──────┬──────┘
       │ retry (max 3 attempts)
       └──────► Fixer
```

The orchestrator maintains shared context across the entire pipeline — tracking repair histories, agent outputs, scoring, and bounded retry attempts. Each agent has access to all prior context so downstream agents can reason about what has already been attempted.

---

## Agents

### Analyzer Agent

Receives the buggy source code and traceback. Returns structured debugging signals:

- `root_cause` — exception class name (e.g. `TypeError`, `NameError`)
- `error_line` — exact line number of the failure
- `reasoning` — concise explanation of why the error occurred

Uses deterministic generation (`do_sample=False`) for consistency.

### Fixer Agent

Generates the smallest possible patch that resolves the identified root cause while preserving original program intent. Returns a JSON object with two fields:

- `patched_code` — full corrected program as a JSON string value
- `explanation` — one-sentence description of the change

**Output parsing** is multi-stage and defensive. The parser first checks for truncation (output must end with `}`), then attempts direct JSON extraction, then falls back to regex extraction of the outermost `{...}` block. Every accepted patch is compile-checked with Python's `compile()` before being passed downstream — a `SyntaxError` triggers an immediate retry.

**Token budget** is set to `max_new_tokens=8192` to accommodate long function bodies without truncation, which was the root cause of compile failures on complex HumanEval problems.

**On retry attempts**, the fixer receives the full critique context — failed patch, evaluator reasoning, failure type, and retry guidance — injected directly into the prompt. A critical rule is enforced on retries: when the error is caused by a wrong operator, variable name, or boolean value, the only valid fix is to restore the original token. The fixer is explicitly forbidden from changing surrounding code to work around the bad value.

**Forbidden behaviors** (enforced via prompt):
- Adding `try/except` blocks
- Inventing arbitrary fallback values
- Bypassing the error with guard conditions
- Rewriting unrelated code
- Repeating a previously failed patch strategy

### Sandbox Executor

Runs the patched program in an isolated subprocess with a configurable timeout. Captures stdout, stderr, and exit code. Returns execution success/failure with full output for downstream evaluation.

### Evaluator Agent

Combines three signal sources into a blended repair score:

**Heuristic signals (40% weight)**
- Execution success/failure
- Structural change ratio (changed lines vs total, not full-file token similarity)
- Large structural change penalty

**LLM signals (60% weight)**
- `intent_preserved` — does the patch preserve the original program's semantics?
- `root_cause_fixed` — does the patch address the actual root cause?
- `introduced_regression` — does the patch introduce new failures?
- `minimal_fix` — is the change the smallest sufficient repair?

A repair passes if `execution_success=True` AND `final_score >= 0.75`.

The evaluator prompt includes explicit override rules that take precedence over general evaluation:

- **Rule 1** — if execution succeeds and stderr is empty, `root_cause_fixed` must be true
- **Rule 2** — uncommenting a return statement is always a valid minimal fix
- **Rule 3** — do not recompute math from docstring examples
- **Rule 4** — restoring a flipped comparison or boolean operator is always a valid minimal fix

### Critique Agent

Reviews failed repair attempts and generates structured feedback:

- `failure_type` — short category (e.g. `invented_value`, `bypass_fix`, `semantic_change`)
- `critique` — precise explanation of why the patch violated intent preservation
- `retry_guidance` — actionable instructions for the next repair attempt
- `should_retry` — whether another attempt is likely to succeed

Critique output is injected directly into the fixer's next prompt alongside the failed patch, preventing the fixer from repeating the same strategy.

---

## Scoring

```
final_score = 0.4 × heuristic_score + 0.6 × llm_score

llm_score = (
    0.4 × intent_preserved
  + 0.4 × root_cause_fixed
  + 0.2 × (1 - introduced_regression)
)

heuristic_score = base_score - penalties
```

Structural change ratio is computed over changed lines only, not the full file. This prevents single-variable renames in long functions from being penalized as large structural changes.

---

## Benchmark

### Dataset

Built on top of [openai/openai_humaneval](https://huggingface.co/datasets/openai/openai_humaneval) — 164 Python programming problems, each with a canonical solution and test harness.

### Mutation Engine

The mutation engine injects a single realistic bug into each canonical solution. 12 mutation strategies are implemented:

| Strategy | Bug Type | Exception |
|---|---|---|
| `missing_return` | Comment out return statement | TypeError / AssertionError |
| `wrong_return_type` | Wrap return in `str()` | TypeError / AssertionError |
| `wrong_variable` | Rename variable definition | NameError |
| `delete_import` | Comment out import line | NameError |
| `flip_comparison` | `==` → `!=`, `<` → `>` | AssertionError |
| `wrong_operator` | `+` → `-`, `*` → `//` | AssertionError |
| `off_by_one` | Decrement numeric literal | AssertionError |
| `flip_boolean` | `True` → `False` | AssertionError |
| `wrong_argument` | Add extra `None` argument | TypeError |
| `slice_to_index` | `lst[i]` → `lst[i+999]` | IndexError |
| `string_to_int` | Replace string literal with `0` | TypeError |
| `none_assignment` | `var = expr` → `var = None` | TypeError / AttributeError |

Each mutation is compile-checked before acceptance so errors are runtime failures, not parse-time failures. The loader tries up to 8 random seeds per problem to find a crashable mutation.

### Failure Capture

The benchmark captures both runtime exceptions (stderr) and `AssertionError` from the HumanEval test harness (wrong-output failures). This gives coverage across the full failure spectrum rather than only hard crashes.

---

## Results

Latest benchmark run across all 164 HumanEval problems:

| Metric | Value |
|---|---|
| PASS@1 | 156/164 (95.1%) |
| Average score | 0.940 |
| Avg analysis latency | 4.0s |
| Avg fix latency | 16.3s |
| Avg evaluation latency | 6.4s |
| Avg total latency | 27.1s |

**Per bug type:**

| Bug Type | Pass | Total | Rate | Avg Score |
|---|---|---|---|---|
| AssertionError | 100 | 105 | 95.2% | 0.945 |
| AttributeError | 1 | 1 | 100% | 1.000 |
| IndexError | 9 | 9 | 100% | 0.964 |
| NameError | 14 | 15 | 93.3% | 0.941 |
| TypeError | 32 | 34 | 94.1% | 0.914 |

**Progression across development iterations:**

| Stage | pass@1 | avg score |
|---|---|---|
| Initial 38-case run | 38/38 (100%) | 0.971 |
| First 164-case run | 152/164 (92.7%) | 0.918 |
| After scoring fix | 153/164 (93.3%) | 0.921 |
| After parser + token budget fix | 158/164 (96.3%) | 0.941 |
| After evaluator rule updates | **156/164 (95.1%)** | **0.940** |

---

## Project Structure

```
agentic-debugger/
├── agents/
│   ├── base_agent.py          # Shared retry logic, JSON extraction, timing
│   ├── analyzer.py            # Root cause identification
│   ├── fixer.py               # Patch generation with multi-stage JSON parsing
│   ├── evaluator.py           # Blended scoring + override rules
│   └── critique.py            # Failure analysis and retry guidance
├── orchestrator/
│   └── orchestrator.py        # Pipeline coordination and context management
├── benchmark/
│   ├── mutator.py             # 12-strategy mutation engine
│   ├── humaneval_loader.py    # Dataset loading + failure capture
│   └── humaneval_reporter.py  # pass@1, per-type breakdown, failure analysis
├── sandbox/
│   └── runner.py              # Subprocess execution with timeout
├── models/
│   └── llm.py                 # HuggingFace model wrapper
├── utils/
│   ├── scoring.py             # Heuristic scoring and blended score computation
│   ├── display.py             # ANSI terminal display
│   ├── dashboard.py           # HTML benchmark dashboard
│   └── logger.py              # Logging setup
└── main_humaneval.py          # CLI entry point
```

---

## Setup

### Requirements

- Python 3.11
- CUDA-capable GPU with at least 20GB VRAM
- CUDA 12.4
- Anaconda or Miniconda

Tested on:
- Ubuntu 24.04
- CUDA 12.4 / cuDNN 9.1
- Qwen2.5-Coder-32B-Instruct-AWQ

---

### Option A — Conda (recommended)

Clone the repo and recreate the exact environment from the provided `environment.yml`:

```bash
git clone https://github.com/your-username/agentic-debugger
cd agentic-debugger
conda env create -f environment.yml
conda activate qwen311
```

The `environment.yml` pins all dependencies including CUDA toolkit, torch, and transformers to the exact versions used during benchmarking.

---

### Option B — pip into existing environment

If you already have a Python 3.11 environment with CUDA configured:

```bash
pip install torch==2.6.0+cu124 torchaudio==2.6.0+cu124 torchvision==0.21.0+cu124 \
    --index-url https://download.pytorch.org/whl/cu124

pip install -r requirements.txt
```

---

### Core Dependencies

| Package | Version | Purpose |
|---|---|---|
| `torch` | 2.6.0+cu124 | Model inference |
| `transformers` | 5.9.0 | HuggingFace model loading |
| `autoawq` | 0.2.9 | AWQ quantization support |
| `accelerate` | 1.13.0 | GPU memory management |
| `datasets` | 4.8.5 | HumanEval dataset loading |
| `tokenizers` | 0.22.2 | Fast tokenization |
| `safetensors` | 0.7.0 | Model weight loading |
| `triton` | 3.2.0 | Kernel optimization |
| `optimum` | 2.1.0 | Inference optimization |
| `huggingface-hub` | 1.17.0 | Model downloading |
| `numpy` | 2.2.6 | Numerical operations |
| `rich` | 15.0.0 | Terminal display |
| `tqdm` | 4.67.3 | Progress bars |
| `requests` | 2.34.2 | HTTP client |
| `pyyaml` | 6.0.3 | Config parsing |

Full pinned dependency list is available in `environment.yml` and `requirements.txt`.

---

### Model Download

The system uses `Qwen/Qwen2.5-Coder-32B-Instruct-AWQ` from HuggingFace. It will be downloaded automatically on first run (~18GB). To pre-download manually:

```bash
huggingface-cli download Qwen/Qwen2.5-Coder-32B-Instruct-AWQ
```

You will need a HuggingFace account and may need to accept the model licence at [huggingface.co/Qwen/Qwen2.5-Coder-32B-Instruct-AWQ](https://huggingface.co/Qwen/Qwen2.5-Coder-32B-Instruct-AWQ).

### Running the Benchmark

```bash
# Full 164-case benchmark
python main_humaneval.py --max 164 --seed 42

# Specific bug types only
python main_humaneval.py --max 164 --bug-types AssertionError TypeError

# Save HTML dashboard to custom path
python main_humaneval.py --max 164 --output results.html

# Run without opening browser
python main_humaneval.py --max 164 --no-browser

# Background run with logging
nohup python main_humaneval.py --max 164 --seed 42 > run.log 2>&1 &
```

### CLI Options

| Flag | Default | Description |
|---|---|---|
| `--max` | all | Maximum number of cases to run |
| `--seed` | 42 | Random seed for mutation |
| `--bug-types` | all | Filter to specific exception types |
| `--output` | `benchmark_results.html` | HTML dashboard output path |
| `--no-color` | false | Disable ANSI terminal colors |
| `--no-browser` | false | Skip opening dashboard in browser |

---

## Observability

After every benchmark run the framework automatically generates an interactive HTML dashboard containing:

- Pass/fail statistics and trend
- Per-bug-type breakdown with score distributions
- Full repair trace for every case (analysis → fix → execution → evaluation → critique)
- Agent latency statistics
- Failure analysis with verdict and mutation description

The terminal display shows a live 3-column layout per case (Analysis / Fix / Evaluation) with score bars, attempt counters, and word-wrapped verdicts.

---

## Key Design Decisions

**Why `max_new_tokens=8192` for the fixer?**
Long HumanEval functions with extensive docstrings push the generation window. Early runs used a lower token budget which caused truncated JSON output and compile failures on complex problems. Setting 8192 tokens eliminates truncation as a failure mode. The parser also includes a truncation check (output must end with `}`) and a regex fallback extractor so partial outputs are caught cleanly rather than silently failing.

**Why multi-stage JSON parsing?**
The model occasionally produces valid JSON content without clean delimiters, or wraps it in prose. The parser tries direct extraction first, then falls back to finding the outermost `{...}` block via regex. Every path ends with a `compile()` check — if the patched code has a syntax error, it retries rather than passing broken code to the executor.

**Why blended scoring?**
Pure execution success is insufficient — a patch can remove the exception while changing program semantics. Pure LLM scoring is inconsistent. Blending heuristic signals (structural change, execution) with LLM signals (intent, regression) produces more reliable pass/fail decisions.

**Why structural ratio over changed lines?**
Full-file token similarity penalizes single-variable renames in long functions. Computing ratio over only the changed lines gives an accurate measure of edit size regardless of function length.

**Why capture AssertionError?**
The original loader only captured hard crashes (non-zero exit with stderr). Capturing AssertionError from the test harness expands from ~38 to ~164 crashable cases, adding the harder class of wrong-output logic bugs.

**Why stall detection?**
If two consecutive repair attempts produce identical scores, the critique loop has stalled. Breaking early saves two LLM calls per stalled case without affecting accuracy.

---

## Limitations and Future Work

**Current limitations:**
- Single-file repair only — no cross-file or repository-level reasoning
- Benchmark mutations are synthetic — real-world bugs have more complex root causes
- Evaluator can misclassify semantically equivalent operator restores as intent violations
- Fix generation fails on very long functions that exceed effective generation window

**Planned improvements:**
- Repository-level context and multi-file repair
- Security-oriented mutations (injection patterns, unsafe API usage, privilege escalation)
- Real-world bug datasets (BugsInPy, Defects4J Python port)
- Stronger intent-preservation evaluation via formal specification
- Parallel repair attempts with selection
- Fine-tuned evaluator to reduce misclassification rate

---

## Research Context

This project sits at the intersection of several active research areas:

- Automated Program Repair (APR)
- Agentic Software Engineering
- LLM-Based Reasoning Systems
- Benchmark Design and Evaluation
- AI for Cybersecurity and Vulnerability Remediation

The same architecture used for program repair extends naturally to security patch generation, vulnerability detection, exploit remediation, and autonomous software maintenance — areas of active interest in the incoming PhD research agenda this project supports.

---

## Citation

If you use this framework or benchmark in your research, please cite:

```bibtex
@misc{agentic-debugger-2025,
  title   = {Agentic Debugger: Automated Program Repair through Collaborative AI Agents},
  author  = {Your Name},
  year    = {2025},
  url     = {https://github.com/your-username/agentic-debugger}
}
```

---

## License

MIT License — see [LICENSE](LICENSE) for details.

---

*Built with Qwen2.5-Coder-32B-AWQ · Evaluated on HumanEval · 95.1% PASS@1*
