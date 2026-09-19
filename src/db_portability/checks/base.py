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


def is_none(node):
    return isinstance(node, ast.Constant) and node.value is None


def call_names(node):
    """Short names (last dotted component) of every Call anywhere in this
    subtree, e.g. to check what a .annotate()/.update() argument expression
    is built out of without having to track variable assignments."""
    names = set()
    for sub in ast.walk(node):
        if isinstance(sub, ast.Call):
            name = dotted_name(sub.func)
            if name:
                names.add(name.rsplit(".", 1)[-1])
    return names
