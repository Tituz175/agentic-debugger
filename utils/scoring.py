import difflib


# ---------------------------------------------------------------------------
# Heuristic scoring
# ---------------------------------------------------------------------------

# Weight used when blending heuristic and LLM evaluation scores.
HEURISTIC_WEIGHT = 0.4
LLM_WEIGHT       = 0.6

# Penalty applied to the heuristic score for each triggered rule.
_PENALTIES = {
    "execution_failed":      0.5,   # patch doesn't even run
    "large_structural_change": 0.2, # too many tokens changed
    "empty_patch":           1.0,   # fixer returned nothing
}

# A patch that changes more than this fraction of tokens is "large".
_LARGE_CHANGE_THRESHOLD = 0.30


def _token_ratio(original: str, patched: str) -> float:
    """Only compare lines that actually changed."""
    orig_lines    = original.strip().splitlines()
    patched_lines = patched.strip().splitlines()
    
    # Find lines that differ
    changed_orig    = []
    changed_patched = []
    for o, p in zip(orig_lines, patched_lines):
        if o != p:
            changed_orig.append(o)
            changed_patched.append(p)
    
    # Also catch added/removed lines
    len_diff = abs(len(orig_lines) - len(patched_lines))
    
    if not changed_orig and len_diff == 0:
        return 1.0  # identical
    
    # Ratio of changed tokens vs total tokens
    total_tokens   = sum(len(l.split()) for l in orig_lines) or 1
    changed_tokens = sum(len(l.split()) for l in changed_orig) + len_diff
    return 1.0 - (changed_tokens / total_tokens)


def compute_heuristic_score(
    original_code: str,
    patched_code: str,
    execution_success: bool,
) -> dict:
    """
    Return a heuristic assessment of the patch quality.

    Keys
    ----
    score            : float in [0, 1]
    structural_ratio : fraction of tokens that changed  (0 = identical)
    penalties        : list of penalty names that fired
    """
    penalties: list[str] = []
    score = 1.0

    if not patched_code or not patched_code.strip():
        penalties.append("empty_patch")
        score -= _PENALTIES["empty_patch"]
        return {
            "score": max(score, 0.0),
            "structural_ratio": 1.0,
            "penalties": penalties,
        }

    if not execution_success:
        penalties.append("execution_failed")
        score -= _PENALTIES["execution_failed"]

    similarity = _token_ratio(original_code, patched_code)
    structural_ratio = round(1.0 - similarity, 6)

    if structural_ratio > _LARGE_CHANGE_THRESHOLD:
        penalties.append("large_structural_change")
        score -= _PENALTIES["large_structural_change"]

    return {
        "score": round(max(score, 0.0), 4),
        "structural_ratio": structural_ratio,
        "penalties": penalties,
    }


# ---------------------------------------------------------------------------
# Final blended score
# ---------------------------------------------------------------------------

def compute_final_score(heuristics: dict, llm_eval: dict) -> float:
    """
    Blend the heuristic score with the LLM evaluator's boolean signals
    into a single float in [0, 1].

    LLM component weights
    ---------------------
    intent_preserved      : 0.40  — most important
    root_cause_fixed      : 0.40  — equally important
    not introduced_regression : 0.20  — tiebreaker
    """
    llm_score = (
        float(llm_eval.get("intent_preserved", False))      * 0.40
        + float(llm_eval.get("root_cause_fixed", False))    * 0.40
        + float(not llm_eval.get("introduced_regression", True)) * 0.20
    )

    blended = (
        HEURISTIC_WEIGHT * heuristics["score"]
        + LLM_WEIGHT     * llm_score
    )
    return round(blended, 4)


def passed_threshold(
    execution_success: bool,
    final_score: float,
    threshold: float = 0.75,
) -> bool:
    """
    A run passes iff it executed successfully AND the blended score
    meets the threshold.  Both conditions are required.
    """
    return execution_success and final_score >= threshold
