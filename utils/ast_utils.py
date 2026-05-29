import ast

def parse_code(code):
    try:
        return ast.parse(code)
    except SyntaxError as e:
        print(f"Syntax error in code: {e}")
        return None

def count_ast_nodes(code):
    tree = parse_code(code)
    if tree is None:
        return 0
    return sum(1 for _ in ast.walk(tree))


def structural_change_ratio(original_code, patched_code):

    original_tree = parse_code(original_code)
    patched_tree = parse_code(patched_code)

    if original_tree is None or patched_tree is None:
        return 0.0

    original_nodes = sum(1 for _ in ast.walk(original_tree))
    patched_nodes = sum(1 for _ in ast.walk(patched_tree))

    difference = abs(patched_nodes - original_nodes)

    return difference / original_nodes
    

def get_node_types(code: str):

    tree = parse_code(code)

    if tree is None:
        return []

    return [
        type(node).__name__
        for node in ast.walk(tree)
    ]


def detect_new_control_flow(original_code, patched_code):

    original_tree = parse_code(original_code)
    patched_tree = parse_code(patched_code)

    if original_tree is None or patched_tree is None:
        return False

    original_nodes = {
        type(node).__name__
        for node in ast.walk(original_tree)
    }

    patched_nodes = {
        type(node).__name__
        for node in ast.walk(patched_tree)
    }

    dangerous_nodes = {
        "If",
        "While",
        "For",
        "Try"
    }

    newly_added = patched_nodes - original_nodes

    return bool(
        dangerous_nodes.intersection(newly_added)
    )


def operator_changed(original_code, patched_code):

    original_tree = parse_code(original_code)
    patched_tree = parse_code(patched_code)

    if original_tree is None or patched_tree is None:
        return False

    original_ops = [
        type(node.op).__name__
        for node in ast.walk(original_tree)
        if isinstance(node, ast.BinOp)
    ]

    patched_ops = [
        type(node.op).__name__
        for node in ast.walk(patched_tree)
        if isinstance(node, ast.BinOp)
    ]

    return original_ops != patched_ops
