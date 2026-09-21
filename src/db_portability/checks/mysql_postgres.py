"""
Rules for the mysql -> postgres pair: flags Django ORM / raw-SQL usage that
is known to work on MySQL/MariaDB but silently break (or behave differently)
on PostgreSQL.

This is a smaller set than postgres -> mysql: PostgreSQL is a stricter, more
standards-compliant engine (no implicit type coercion in comparisons, no
non-strict SQL mode), so most of what leaks through going this direction is
raw SQL written against MySQL-only syntax. There is no NULL/empty-string
trap here either: MySQL, like PostgreSQL, stores '' as a real, non-NULL
value rather than coercing it to NULL (that divergence is specific to
Oracle - see db_portability.checks.oracle_postgres).

Codes DBP3xx are reserved for this pair, per the block scheme described in
db_portability.checks.REGISTRY.
"""
import ast
import re

from db_portability.checks.base import string_constant

SOURCE = "mysql"
TARGET = "postgres"

RAW_SQL_CALL_NAMES = {"RunSQL", "execute", "raw"}

# MySQL/MariaDB syntax with no PostgreSQL equivalent (or a different name),
# so raw SQL that uses it errors out unchanged on PostgreSQL.
RAW_SQL_MARKERS = (
    "`",
    "auto_increment",
    "on duplicate key update",
    "group_concat(",
    "ifnull(",
    "str_to_date(",
    "date_format(",
    " unsigned",
    "straight_join",
)

# MySQL's comma form of LIMIT (`LIMIT offset, count`) - PostgreSQL only
# accepts `LIMIT count OFFSET offset`.
LIMIT_COMMA_RE = re.compile(r"\blimit\s+\d+\s*,\s*\d+", re.IGNORECASE)

WARN_CODES = {"DBP302"}


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
                if LIMIT_COMMA_RE.search(lowered):
                    hits.append("LIMIT offset, count")
                if hits:
                    self._add(
                        node,
                        "DBP301",
                        f"raw SQL contains MySQL-specific syntax "
                        f"({', '.join(h.strip() for h in hits)}) - will not "
                        "run on PostgreSQL as-is",
                    )

        if func_name == "extra":
            self._add(
                node,
                "DBP302",
                ".extra() injects raw SQL fragments - review for "
                "MySQL-only syntax before running on PostgreSQL",
            )

        self.generic_visit(node)


def run(tree):
    """Return sorted (lineno, col, "CODE message") tuples for a parsed module."""
    visitor = _Visitor()
    visitor.visit(tree)
    return sorted(visitor.errors)
