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


def is_non_model_field_call(func_name):
    """True if a dotted call name looks like a DRF serializer or Django
    form field rather than a model field - e.g. `serializers.CharField`
    or `forms.CharField`. Those share names with `models` fields
    (CharField, TextField, ...) but map to no database column, so a
    declared-length requirement doesn't apply to them."""
    parts = func_name.split(".")
    return "serializers" in parts or "forms" in parts


def direct_assignment_call_ids(tree):
    """id() of every Call that is the direct right-hand side of an
    assignment (`name = Field(...)`) - i.e. a plausible field declaration,
    as opposed to a Call used as an argument inside another expression
    (`output_field=CharField()`, `Cast(expr, CharField())`), which several
    ORM expressions use as a bare output-type marker rather than a stored
    column. Comparing by id() (not equality) since AST nodes aren't
    hashable/comparable by value."""
    ids = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Assign, ast.AnnAssign)) and isinstance(
            node.value, ast.Call
        ):
            ids.add(id(node.value))
    return ids


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
