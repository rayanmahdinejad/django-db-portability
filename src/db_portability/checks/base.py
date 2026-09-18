"""AST-walking helpers shared by every (source, target) rule module."""
import ast


def dotted_name(node):
    """Best-effort reconstruction of a dotted attribute/name chain."""
    parts = []
    while isinstance(node, ast.Attribute):
        parts.append(node.attr)
        node = node.value
    if isinstance(node, ast.Name):
        parts.append(node.id)
    return ".".join(reversed(parts))


def string_constant(node):
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    return None


def keyword_value(call, name):
    for kw in call.keywords:
        if kw.arg == name:
            return kw.value
    return None


def is_true(node):
    return isinstance(node, ast.Constant) and node.value is True
