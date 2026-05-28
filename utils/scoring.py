from utils.ast_utils import structural_change_ratio, detect_new_control_flow, operator_changed

def compute_heuristic_score(original_code, patched_code, execution_success):

    score = 1.0

    penalties = []

    if not execution_success:

        score -= 0.5

        penalties.append("execution_failed")

    ratio = structural_change_ratio(original_code, patched_code)

    if ratio > 0.3:

        score -= 0.2

        penalties.append("large_structural_change")

    if detect_new_control_flow(original_code, patched_code):

        score -= 0.15

        penalties.append("new_control_flow")

    if operator_changed(original_code, patched_code):

        score -= 0.25

        penalties.append("operator_semantics_changed")

    score = max(score, 0.0)

    return {
        "score": round(score, 2),
        "penalties": penalties,
        "structural_ratio": ratio
    }
