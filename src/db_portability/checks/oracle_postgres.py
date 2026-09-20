"""
Rules for the oracle -> postgres pair: flags Django ORM / raw-SQL usage that
is known to work on Oracle but silently break (or behave differently) on
PostgreSQL.

This is a smaller set than postgres -> oracle: PostgreSQL is generally more
permissive (no declared-length requirement on character columns, no
CLOB-in-GROUP-BY/DISTINCT restriction, ...), so most of the leaks running
this direction come from raw SQL written against Oracle-specific syntax, or
from the empty-string/NULL divergence biting in the opposite direction.

Codes DBP1xx are reserved for this pair, per the block scheme described in
db_portability.checks.REGISTRY.
"""
import ast

from db_portability.checks.base import keyword_value, is_true, string_constant

SOURCE = "oracle"
TARGET = "postgres"

CHAR_BASED_FIELDS = {
    "CharField",
    "TextField",
    "SlugField",
    "EmailField",
    "URLField",
}

RAW_SQL_CALL_NAMES = {"RunSQL", "execute", "raw"}

# Oracle/PL-SQL syntax with no PostgreSQL equivalent (or a different name),
# so raw SQL that uses it errors out unchanged on PostgreSQL.
RAW_SQL_MARKERS = (
    "rownum",
    "sysdate",
    "nvl(",
    "decode(",
    "connect by",
    "minus",
    " dual",
    "(+)",
    ".nextval",
    ".currval",
)

WARN_CODES = {"DBP102"}


class _Visitor(ast.NodeVisitor):
    def __init__(self):
        self.errors = []

    def _add(self, node, code, message):
        self.errors.append((node.lineno, node.col_offset, f"{code} {message}"))

    def visit_Call(self, node):
        func_name = None
        if isinstance(node.func, ast.Attribute):
            func_name = node.func.attr
        elif isinstance(node.func, ast.Name):
            func_name = node.func.id

        if func_name in RAW_SQL_CALL_NAMES and node.args:
            sql = string_constant(node.args[0])
            if sql is not None:
                lowered = sql.lower()
                hits = [m for m in RAW_SQL_MARKERS if m in lowered]
                if hits:
                    self._add(
                        node,
                        "DBP101",
                        f"raw SQL contains Oracle-specific syntax "
                        f"({', '.join(h.strip() for h in hits)}) - will not "
                        "run on PostgreSQL as-is",
                    )

        if func_name == "extra":
            self._add(
                node,
                "DBP102",
                ".extra() injects raw SQL fragments - review for "
                "Oracle-only syntax before running on PostgreSQL",
            )

        if func_name in CHAR_BASED_FIELDS:
            unique = keyword_value(node, "unique")
            blank = keyword_value(node, "blank")
            null = keyword_value(node, "null")
            if is_true(unique) and is_true(blank) and not is_true(null):
                self._add(
                    node,
                    "DBP103",
                    f"{func_name}(unique=True, blank=True) without "
                    "null=True: Oracle coerces '' to NULL (so repeated "
                    "blanks pass the unique constraint), but PostgreSQL "
                    "stores '' as a real, non-NULL value - a second blank "
                    "row that worked on Oracle raises a unique-constraint "
                    "violation on PostgreSQL",
                )

        self.generic_visit(node)


def run(tree):
    """Return sorted (lineno, col, "CODE message") tuples for a parsed module."""
    visitor = _Visitor()
    visitor.visit(tree)
    return sorted(visitor.errors)
