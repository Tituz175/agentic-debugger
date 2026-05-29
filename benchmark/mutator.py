"""
mutator.py

Introduces a single deliberate bug into a correct Python function body.
Each mutator targets a specific exception type so the resulting traceback
is predictable and matches your debugger's error-specific evaluation rules.

Design principles
-----------------
- One bug per function — keeps cases unambiguous for the evaluator.
- Each mutation is reversible — the original is stored alongside the mutant.
- Mutations are chosen based on what's present in the code, not randomly,
  so every generated case is guaranteed to be triggerable.
"""

import ast
import random
import re
import textwrap
from dataclasses import dataclass


@dataclass
class MutationResult:
    task_id:        str
    buggy_code:     str       # full executable program (prompt + mutated body)
    original_code:  str       # full executable program (prompt + canonical body)
    bug_type:       str       # exception class name the bug will raise
    mutation_desc:  str       # human-readable description of what changed
    test_code:      str       # HumanEval test harness (check + assert block)
    entry_point:    str       # function name


# ---------------------------------------------------------------------------
# Individual mutation strategies
# ---------------------------------------------------------------------------

def _mutate_off_by_one(source: str) -> tuple[str, str] | None:
    """
    Change a numeric literal involved in indexing or range() by ±1.
    Produces: IndexError or incorrect output (logic bug).
    """
    # Find integer literals that are likely loop bounds or indices
    pattern = re.compile(r'\b([2-9]|[1-9]\d+)\b')
    matches = list(pattern.finditer(source))
    if not matches:
        return None
    m = random.choice(matches)
    original_val = int(m.group())
    mutated_val  = original_val - 1
    mutated = source[:m.start()] + str(mutated_val) + source[m.end():]
    return mutated, f"Changed literal {original_val} → {mutated_val} (off-by-one)"


def _mutate_wrong_operator(source: str) -> tuple[str, str] | None:
    """
    Swap a comparison or arithmetic operator.
    Produces: wrong output / logic bug.
    """
    swaps = [
        (r'(?<![=!<>])<=(?!=)', '<'),
        (r'(?<![=!<>])>=(?!=)', '>'),
        (r'(?<![=!<>])<(?![=])',  '<='),
        (r'(?<![=!<>])>(?![=])',  '>='),
        (r'\+(?!=)',              '-'),
        (r'-(?!=)',               '+'),
    ]
    random.shuffle(swaps)
    for pattern, replacement in swaps:
        m = re.search(pattern, source)
        if m:
            mutated = source[:m.start()] + replacement + source[m.end():]
            return mutated, f"Swapped operator '{m.group()}' → '{replacement}'"
    return None


def _mutate_wrong_return_type(source: str) -> tuple[str, str] | None:
    """
    Change a return value to the wrong type.
    Produces: TypeError downstream when the caller uses the result.
    """
    # Find 'return <something>' lines and wrap the value in str()
    m = re.search(r'(return\s+)([^"\'\n][^\n]+)', source)
    if not m:
        return None
    original_val = m.group(2).strip()
    # Don't double-wrap or wrap None/True/False
    if original_val in ('None', 'True', 'False') or original_val.startswith('str('):
        return None
    mutated_line = m.group(1) + f'str({original_val})'
    mutated = source[:m.start()] + mutated_line + source[m.end():]
    return mutated, f"Wrapped return value in str(): return {original_val} → return str({original_val})"


def _mutate_missing_return(source: str) -> tuple[str, str] | None:
    """
    Remove the final return statement so the function returns None.
    Produces: TypeError when caller uses the result arithmetically.
    """
    lines = source.split('\n')
    for i in reversed(range(len(lines))):
        stripped = lines[i].strip()
        if stripped.startswith('return ') and stripped != 'return None':
            removed_line = lines[i]
            lines[i] = lines[i].replace(stripped, '# ' + stripped)  # comment it out
            return '\n'.join(lines), f"Commented out: '{stripped}' → function returns None"
    return None


def _mutate_wrong_variable(source: str) -> tuple[str, str] | None:
    """
    Rename one local variable to an undefined name.
    Produces: NameError.
    """
    try:
        tree = ast.parse(textwrap.dedent(source))
    except SyntaxError:
        return None

    # Collect assigned local variable names (exclude params and builtins)
    assigned = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    assigned.add(target.id)
        elif isinstance(node, (ast.AugAssign, ast.AnnAssign)):
            if isinstance(node.target, ast.Name):
                assigned.add(node.target.id)

    if not assigned:
        return None

    victim = random.choice(list(assigned))
    # Replace one usage of the variable (not the assignment) with a mangled name
    mangled = victim + '_undefined'
    # Only replace in non-assignment positions — crude but effective
    pattern = re.compile(r'(?<!\w)' + re.escape(victim) + r'(?!\w)\s*(?![=+\-*/%&|^])')
    m = pattern.search(source)
    if not m:
        return None
    mutated = source[:m.start()] + mangled + source[m.end():]
    return mutated, f"Renamed usage of '{victim}' → '{mangled}' (NameError)"


# Ordered by preference — try each until one succeeds
_STRATEGIES = [
    ('TypeError',   _mutate_wrong_return_type),
    ('TypeError',   _mutate_missing_return),
    ('NameError',   _mutate_wrong_variable),
    ('LogicError',  _mutate_wrong_operator),
    ('LogicError',  _mutate_off_by_one),
]


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def mutate(task_id: str, prompt: str, canonical_solution: str,
           test: str, entry_point: str,
           seed: int | None = None) -> MutationResult | None:
    """
    Given a HumanEval problem, produce a MutationResult with a single bug
    introduced into the body.  Returns None if no mutation could be applied.
    """
    if seed is not None:
        random.seed(seed)

    # Reconstruct the full correct program
    full_solution = prompt + canonical_solution

    # Shuffle strategies so we get variety across problems
    strategies = _STRATEGIES.copy()
    random.shuffle(strategies)

    for bug_type, strategy_fn in strategies:
        result = strategy_fn(canonical_solution)
        if result is None:
            continue

        mutated_body, mutation_desc = result

        # Sanity-check: mutated body must differ from original
        if mutated_body == canonical_solution:
            continue

        # Build the full buggy program
        buggy_code = prompt + mutated_body

        return MutationResult(
            task_id=task_id,
            buggy_code=buggy_code,
            original_code=full_solution,
            bug_type=bug_type,
            mutation_desc=mutation_desc,
            test_code=test,
            entry_point=entry_point,
        )

    return None
