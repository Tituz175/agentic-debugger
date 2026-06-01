"""
mutator.py

12 mutation strategies covering all Python function types.
"""

import ast
import random
import re
import textwrap
from dataclasses import dataclass


@dataclass
class MutationResult:
    task_id:       str
    buggy_code:    str
    original_code: str
    bug_type:      str
    mutation_desc: str
    test_code:     str
    entry_point:   str


def _parse_safe(source):
    try:
        return ast.parse(textwrap.dedent(source))
    except SyntaxError:
        return None


def _assigned_names(source):
    tree = _parse_safe(source)
    if not tree:
        return []
    names = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            for t in node.targets:
                if isinstance(t, ast.Name):
                    names.append(t.id)
        elif isinstance(node, (ast.AugAssign, ast.AnnAssign)):
            if isinstance(node.target, ast.Name):
                names.append(node.target.id)
    return names


def _mutate_missing_return(source):
    lines = source.split("\n")
    for i in reversed(range(len(lines))):
        stripped = lines[i].strip()
        if stripped.startswith("return ") and stripped != "return None":
            lines[i] = lines[i].replace(stripped, "# " + stripped)
            mutated = "\n".join(lines)
            if mutated != source:
                return mutated, f"Commented out: '{stripped}' → function returns None"
    return None


def _mutate_wrong_return_type(source):
    m = re.search(r"(return\s+)([^#\"\'\n][^\n]+)", source)
    if not m:
        return None
    val = m.group(2).strip()
    if val in ("None", "True", "False") or val.startswith(("str(", "int(", "float(")):
        return None
    mutated = source[: m.start()] + m.group(1) + f"str({val})" + source[m.end():]
    return mutated, f"Wrapped return value in str(): return {val} → return str({val})"


def _mutate_wrong_variable(source):
    assigned = _assigned_names(source)
    if not assigned:
        return None
    random.shuffle(assigned)
    for victim in assigned:
        mangled = victim + "_undefined"
        pattern = re.compile(r"(?<!\w)" + re.escape(victim) + r"(?!\w)\s*=(?!=)")
        m = pattern.search(source)
        if not m:
            continue
        end_of_name = m.start() + len(victim)
        mutated = source[: m.start()] + mangled + source[end_of_name:]
        if mutated != source:
            return mutated, f"Renamed definition of '{victim}' → '{mangled}' (NameError on first use)"
    return None


def _mutate_delete_import(source):
    lines = source.split("\n")
    import_lines = [i for i, l in enumerate(lines)
                    if l.strip().startswith(("import ", "from "))]
    if not import_lines:
        return None
    idx = random.choice(import_lines)
    removed = lines[idx].strip()
    new_lines = lines[:idx] + ["# " + lines[idx]] + lines[idx + 1:]
    mutated = "\n".join(new_lines)
    return mutated, f"Commented out import: '{removed}' → NameError on first use"


def _mutate_flip_comparison(source):
    swaps = [("==", "!="), ("!=", "=="),
             (r"(?<![<>])<=(?!=)", "<"), (r"(?<![<>])>=(?!=)", ">"),
             (r"(?<![<>=])>(?![=>])", ">="), (r"(?<![<>=])<(?![=<])", "<=")]
    random.shuffle(swaps)
    for pattern, replacement in swaps:
        m = re.search(pattern, source)
        if m:
            mutated = source[: m.start()] + replacement + source[m.end():]
            if mutated != source:
                return mutated, f"Flipped comparison '{m.group()}' → '{replacement}'"
    return None


def _mutate_wrong_operator(source):
    swaps = [(r"(?<!\w)\+(?!=)", "-"), (r"(?<!\w)-(?!=)", "+"),
             (r"(?<!\w)\*(?!\*)", "//"), (r"(?<!\w)//", "*")]
    random.shuffle(swaps)
    for pattern, replacement in swaps:
        m = re.search(pattern, source)
        if m:
            mutated = source[: m.start()] + replacement + source[m.end():]
            if mutated != source:
                return mutated, f"Swapped operator '{m.group()}' → '{replacement}'"
    return None


def _mutate_off_by_one(source):
    pattern = re.compile(r"\b([2-9]|[1-9]\d+)\b")
    matches = list(pattern.finditer(source))
    if not matches:
        return None
    m = random.choice(matches)
    original_val = int(m.group())
    mutated = source[: m.start()] + str(original_val - 1) + source[m.end():]
    return mutated, f"Changed literal {original_val} → {original_val - 1} (off-by-one)"


def _mutate_flip_boolean(source):
    for original, replacement in [("True", "False"), ("False", "True")]:
        m = re.search(r"\b" + original + r"\b", source)
        if m:
            mutated = source[: m.start()] + replacement + source[m.end():]
            if mutated != source:
                return mutated, f"Flipped boolean {original} → {replacement}"
    return None


def _mutate_wrong_argument(source):
    pattern = re.compile(r"(\w+)\(([^()]+)\)")
    skip = {"print", "len", "range", "list", "dict", "set", "tuple",
            "str", "int", "float", "bool", "type", "isinstance", "sorted",
            "enumerate", "zip", "map", "filter", "sum", "min", "max"}
    matches = [m for m in pattern.finditer(source) if m.group(1) not in skip]
    if not matches:
        return None
    m = random.choice(matches)
    mutated = source[: m.start()] + f"{m.group(1)}({m.group(2)}, None)" + source[m.end():]
    if mutated != source:
        return mutated, f"Added extra None argument to '{m.group(1)}(...)' → TypeError"
    return None


def _mutate_slice_to_index(source):
    pattern = re.compile(r"(\w+)\[([^\[\]:]+)\]")
    matches = list(pattern.finditer(source))
    if not matches:
        return None
    m = random.choice(matches)
    inner = m.group(2).strip()
    if inner.startswith(("'", '"')):
        return None
    mutated = source[: m.start()] + f"{m.group(1)}[{inner}+999]" + source[m.end():]
    if mutated != source:
        return mutated, f"Changed index [{inner}] → [{inner}+999] → IndexError"
    return None


def _mutate_string_to_int(source):
    pattern = re.compile(r'(?<![\'"\\])("(?:[^"\\]|\\.)+"|\'(?:[^\'\\]|\\.)+\')')
    matches = list(pattern.finditer(source))
    def_lines = {i for i, l in enumerate(source.split("\n"))
                 if l.strip().startswith(("def ", "class "))}
    candidates = [m for m in matches
                  if source[: m.start()].count("\n") - 1 not in def_lines
                  and m.group() not in ('""', "''")]
    if not candidates:
        return None
    m = random.choice(candidates)
    mutated = source[: m.start()] + "0" + source[m.end():]
    if mutated != source:
        return mutated, f"Replaced string literal {m.group()} with 0 → TypeError"
    return None


def _mutate_none_assignment(source):
    assigned = _assigned_names(source)
    if not assigned:
        return None
    random.shuffle(assigned)
    for victim in assigned:
        pattern = re.compile(
            r"(?<!\w)" + re.escape(victim) + r"(?!\w)\s*=\s*(?!None)([^\n]+)"
        )
        m = pattern.search(source)
        if not m:
            continue
        original_rhs = m.group(1).strip()
        if original_rhs.startswith(("=", "+", "-", "*", "/")):
            continue
        mutated = source[: m.start()] + f"{victim} = None" + source[m.start() + len(m.group(0)):]
        if mutated != source:
            return mutated, f"Changed '{victim} = {original_rhs}' → '{victim} = None' → TypeError on use"
    return None


_STRATEGIES = [
    ("TypeError",  _mutate_missing_return),
    ("TypeError",  _mutate_wrong_return_type),
    ("NameError",  _mutate_wrong_variable),
    ("NameError",  _mutate_delete_import),
    ("LogicError", _mutate_flip_comparison),
    ("LogicError", _mutate_wrong_operator),
    ("LogicError", _mutate_off_by_one),
    ("LogicError", _mutate_flip_boolean),
    ("TypeError",  _mutate_wrong_argument),
    ("IndexError", _mutate_slice_to_index),
    ("TypeError",  _mutate_string_to_int),
    ("TypeError",  _mutate_none_assignment),
]


def mutate(task_id, prompt, canonical_solution, test, entry_point, seed=None):
    if seed is not None:
        random.seed(seed)

    full_solution = prompt + canonical_solution
    strategies = _STRATEGIES.copy()
    random.shuffle(strategies)

    for bug_type, strategy_fn in strategies:
        result = strategy_fn(canonical_solution)
        if result is None:
            continue
        mutated_body, mutation_desc = result
        if mutated_body == canonical_solution:
            continue
        # Must compile so errors are runtime, not parse-time
        try:
            compile(prompt + mutated_body, "<mutant>", "exec")
        except SyntaxError:
            continue
        return MutationResult(
            task_id=task_id,
            buggy_code=prompt + mutated_body,
            original_code=full_solution,
            bug_type=bug_type,
            mutation_desc=mutation_desc,
            test_code=test,
            entry_point=entry_point,
        )
    return None
