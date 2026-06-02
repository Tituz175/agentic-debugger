from agents.base_agent import BaseAgent
from utils.logger import setup_logger
from utils.scoring import (
    compute_heuristic_score,
    compute_final_score,
    passed_threshold,
)

logger = setup_logger()


class EvaluatorAgent(BaseAgent):
    """
    Evaluates whether a patch correctly fixes the bug and preserves intent.

    Scoring
    -------
    The final score blends:
    - Heuristic signals: execution success, structural change ratio
    - LLM signals: intent_preserved, root_cause_fixed, introduced_regression

    A run passes iff it executed successfully AND final_score >= 0.75.
    """

    max_retries = 2

    _SYSTEM_PROMPT = (
        "You are a strict software repair evaluator. "
        "Judge only what is in front of you. Be precise and conservative."
    )

    def __init__(self, llm):
        super().__init__(llm)

    # ------------------------------------------------------------------
    # Prompt construction
    # ------------------------------------------------------------------

    def _build_prompt(self, context: dict, heuristics: dict) -> str:
        return f"""
You are a strict software repair evaluator.
 
Determine whether the patched code:
1. Fixes the root cause of the bug.
2. Preserves the original program's intent.
3. Is a minimal change (no unnecessary additions).
4. Does not introduce new bugs or regressions.
 
Return ONLY this structure — nothing before, nothing after:
 
<json>
{{
    "intent_preserved": <true|false>,
    "minimal_fix": <true|false>,
    "root_cause_fixed": <true|false>,
    "introduced_regression": <true|false>,
    "reasoning": "<one or two sentences explaining your verdict>"
}}
</json>

==================================================
EXECUTION OVERRIDE RULES  (apply before everything else)
==================================================

RULE 1 — EXECUTION IS GROUND TRUTH:
If execution_success is True AND stderr is empty, then root_cause_fixed
MUST be true. A patch that executes without error has resolved the
exception by definition. Do NOT second-guess a passing execution by
re-evaluating the math, logic, or test assertions mentally.
Never mark root_cause_fixed=false when execution succeeded cleanly.
If the fix is a rename (foo_undefined → foo), minimal_fix MUST 
also be true regardless of structural_ratio

RULE 2 — COMMENTED-OUT CODE:
If the patch simply uncomments a return statement or commented-out logic,
this is ALWAYS a valid minimal fix. Mark intent_preserved=true and
root_cause_fixed=true unconditionally. Do NOT speculate about why the
code was commented out — that is not your concern.

RULE 3 — DO NOT RECOMPUTE MATH:
You cannot verify mathematical correctness of outputs. Do not attempt to
mentally compute expected values from docstring examples. If the code
runs and the test harness passes, the math is correct.

RULE 4 — COMPARISON AND BOOLEAN FLIP FIXES:
If the mutation flipped a comparison operator (== ↔ !=, < ↔ >, <= ↔ >=)
or a boolean literal (True ↔ False), and the patch restores the original
operator or literal, this is ALWAYS a valid minimal fix.
Mark intent_preserved=true and minimal_fix=true unconditionally.
Execution success confirms the restoration is correct.
Do NOT second-guess a single operator or literal restore.
 
==================================================
GENERAL EVALUATION RULES
==================================================
 
Reject (mark intent_preserved=false) when:
- The fix assigns a hardcoded value to a variable that had no inferable
  correct value from the surrounding code.
- The fix changes an index, operand, or variable to bypass the error
  rather than addressing why it occurred.
- The fix removes or silences functionality (e.g. wrapping in try/except,
  deleting the failing line).
- The fix introduces logic, imports, or control flow that was not present
  and was not required to resolve the traceback.
 
Accept (mark intent_preserved=true) only when:
- The fix makes the smallest syntactic or type change that resolves the
  traceback AND the corrected value is directly derivable from context
  (e.g. a missing colon, a wrong type cast, a clearly off-by-one index).
- Original semantics and data flow are fully preserved.
- No new failure modes are introduced.
 
==================================================
ERROR-SPECIFIC RULES  (root cause: {context["analysis"]["root_cause"]})
==================================================
 
NameError — undefined variable:
- If the fix defines the missing variable with ANY hardcoded value
  (0, None, "", [], False, or a value copied from another variable),
  mark intent_preserved=false and root_cause_fixed=false.
- Rationale: the correct value cannot be determined from the code alone.
  Inventing a value changes program behaviour in an unknown way.
- Exception: if the variable name and context make the value
  unambiguously obvious (e.g. `PI = 3.14159` where PI is used in a
  circle formula), you may accept it.
- If the buggy code contains `foo_undefined` and the patch replaces ALL
  occurrences of `foo_undefined` with `foo` (or vice versa), and `foo`
  appears elsewhere in the original code as a defined variable or parameter,
  this is ALWAYS a valid minimal rename fix.
- Mark intent_preserved=true and minimal_fix=true regardless of
  structural_ratio. The ratio is misleading for rename-only fixes.
 
IndexError — index out of range:
- If the fix changes the index to the last valid element (e.g. 5 → 2),
  mark intent_preserved=false unless the original index was clearly a
  typo of an adjacent valid index (e.g. 3 → 2 in a 3-element list).
- Rationale: the list likely needs more elements, not a different index.
 
ZeroDivisionError — division by zero:
- If the fix changes the divisor from 0 to any non-zero literal,
  mark intent_preserved=false and root_cause_fixed=false.
- Rationale: changing the divisor bypasses the error without explaining
  why it was zero. A real fix requires understanding the data source.
 
TypeError — wrong type:
- A minimal cast (str(), int(), float()) that preserves the operation's
  intent is acceptable. Mark intent_preserved=true.
- Adding isinstance() checks or try/except is not acceptable.
 
SyntaxError — missing punctuation/keyword:
- Adding the missing token (colon, bracket, indent) is always acceptable.
  Mark intent_preserved=true and root_cause_fixed=true.
 
AttributeError / KeyError:
- If the fix adds a default value or fallback, mark intent_preserved=false.
- If the fix corrects a clear typo in an attribute or key name,
  mark intent_preserved=true.
 
==================================================
CONFIDENCE AWARENESS
==================================================
 
If the fixer reported low confidence or an ambiguity note, weight that
heavily. A fix that the fixer itself flagged as uncertain should be
scrutinised more strictly, not given the benefit of the doubt.
 
---
 
Root cause:      {context["analysis"]["root_cause"]}
Original code:   {context["code"]}
 
Patched code:    {context["fix"]["patched_code"]}
 
Traceback:       {context["traceback"]}
 
Execution stdout:    {context["execution_result"]["stdout"]}
Execution success:   {context["execution_success"]}
Execution stderr:    {context["execution_result"]["stderr"] or "none"}
 
Fixer confidence:   {context["fix"].get("confidence", "not reported")}
Ambiguity note:     {context["fix"].get("ambiguity_note", "none")}
 
Heuristic score:    {heuristics["score"]}
Penalties:          {heuristics["penalties"]}
Structural change:  {heuristics["structural_ratio"]:.4f}
(Note: ratio reflects full-file token similarity, not edit size.
 A single variable rename in a long function may show high ratio.)
""".strip()

    # ------------------------------------------------------------------
    # parse_and_validate callback
    # ------------------------------------------------------------------

    def _parse(self, raw: str, latency: float) -> dict:
        parsed = self.extract_json(raw)

        required = {
            "intent_preserved",
            "minimal_fix",
            "root_cause_fixed",
            "introduced_regression",
            "reasoning",
        }
        missing = required - parsed.keys()
        if missing:
            raise ValueError(f"Missing keys in evaluator output: {missing}")

        for bool_key in ("intent_preserved", "minimal_fix",
                         "root_cause_fixed", "introduced_regression"):
            if not isinstance(parsed[bool_key], bool):
                raise ValueError(
                    f"{bool_key} must be a boolean, got {type(parsed[bool_key])}"
                )

        return parsed

    # ------------------------------------------------------------------
    # Entry point
    # ------------------------------------------------------------------

    def run(self, context: dict) -> dict:
        run_id = context.get("run_id", "unknown")
        logger.info(f"[Run {run_id}] EvaluatorAgent started")

        original_code     = context["code"]
        patched_code      = context["fix"]["patched_code"]
        execution_success = context["execution_success"]

        heuristics = compute_heuristic_score(
            original_code, patched_code, execution_success
        )
        logger.info(f"[Run {run_id}] Heuristic result: {heuristics}")

        llm_eval = self._run_with_retries(
            run_id=run_id,
            label="Evaluator",
            system_prompt=self._SYSTEM_PROMPT,
            user_prompt=self._build_prompt(context, heuristics),
            parse_and_validate=self._parse,
            # Deterministic — evaluation should not vary between calls
            generate_kwargs={"do_sample": False, "temperature": 0.0},
        )

        if llm_eval is None:
            logger.error(f"[Run {run_id}] EvaluatorAgent returning failure sentinel")
            return {
                "passed": False,
                "score": heuristics["score"],
                "heuristics": heuristics,
                "intent_preserved": False,
                "minimal_fix": False,
                "root_cause_fixed": False,
                "introduced_regression": True,
                "reasoning": "Evaluator failed after all retries.",
            }

        final_score = compute_final_score(heuristics, llm_eval)
        passed = passed_threshold(execution_success, final_score)

        evaluation = {
            "passed": passed,
            "score": final_score,
            "heuristics": heuristics,
            **llm_eval,
        }

        logger.info(f"[Run {run_id}] Evaluation result: {evaluation}")
        return evaluation
    