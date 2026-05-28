import ast

def parse_code(code):
    return ast.parse(code)

def count_ast_nodes(code):
    tree = parse_code(code)
    return sum(1 for _ in ast.walk(tree))


def structural_change_ratio(original_code, patched_code):
    original_nodes = count_ast_nodes(original_code)
    patched_nodes = count_ast_nodes(patched_code)

    difference = abs(patched_nodes - original_nodes)

    return difference / max(original_nodes, 1)
    

def get_node_types(code: str):

    tree = parse_code(code)

    return [
        type(node).__name__
        for node in ast.walk(tree)
    ]


def detect_new_control_flow(original_code, patched_code):

    original_nodes = set(get_node_types(original_code))

    patched_nodes = set(get_node_types(patched_code))

    dangerous_nodes = {
        "If",
        "While",
        "For",
        "Try"
    }

    newly_added = (patched_nodes - original_nodes)

    return bool(
        dangerous_nodes.intersection(newly_added)
    )


def operator_changed(original_code, patched_code):

    original_tree = parse_code(original_code)

    patched_tree = parse_code(patched_code)

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

