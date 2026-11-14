"""
Rules for the postgres -> sqlite pair: flags Django ORM / raw-SQL usage that
is known to work on PostgreSQL but break, or silently behave differently,
on SQLite.

This is the pair Django projects hit when tests run on SQLite and production
runs on PostgreSQL. It covers the same Postgres-only contrib modules, raw
SQL, and `.distinct(*fields)` risks as postgres -> mysql, plus the SQLite
gaps that one actually trips over: `.select_for_update()` (ignored, or
NotSupportedError for nowait/skip_locked/of), deferrable unique constraints
(ignored), and PostgreSQL operator classes (ignored).

There is no NULL/empty-string trap here: SQLite, like PostgreSQL, stores ''
as a real value. SQLite also allows VARCHAR with no declared length
(`supports_unlimited_charfield`) and has no InnoDB-style index key limit, so
those mysql/oracle checks are not repeated.

Not flagged, on purpose:
- `ON CONFLICT` (SQLite upsert since 3.24), `RETURNING` (since 3.35), and
  JSON `->` / `->>` (since 3.38). Current SQLite runs all three.
- `SERIAL` as a column type. SQLite accepts unknown type names, so the
  statement runs; it just has no sequence. Same for other affinity-only
  types (BOOLEAN, DECIMAL), which this checker does not try to cover.
- `AlterField` / `AddConstraint` migration operations. Django's SQLite
  schema editor rebuilds the table for those. The same clauses inside raw
  SQL are flagged, because SQLite rejects `ALTER COLUMN`, `ADD CONSTRAINT`,
  and `DROP CONSTRAINT` as written.

Codes DBP4xx are reserved for this pair, per the block scheme described in
db_portability.checks.REGISTRY.
"""
import ast
import re

from db_portability.checks.base import (
    dotted_name,
    is_none,
    keyword_value,
    string_constant,
)

SOURCE = "postgres"
TARGET = "sqlite"

POSTGRES_FIELD_NAMES = {
    "ArrayField",
    "HStoreField",
    "CITextField",
    "CICharField",
    "CIEmailField",
    "RangeField",
    "IntegerRangeField",
    "BigIntegerRangeField",
    "DecimalRangeField",
    "DateTimeRangeField",
    "DateRangeField",
}

POSTGRES_SEARCH_NAMES = {
    "SearchVector",
    "SearchQuery",
    "SearchRank",
    "SearchVectorField",
    "SearchHeadline",
    "TrigramSimilarity",
    "TrigramDistance",
    "TrigramWordSimilarity",
    "TrigramWordDistance",
    "TrigramStrictWordSimilarity",
    "TrigramStrictWordDistance",
}

POSTGRES_AGGREGATE_NAMES = {
    "ArrayAgg",
    "BitAnd",
    "BitOr",
    "BitXor",
    "BoolAnd",
    "BoolOr",
    "JSONBAgg",
    "StringAgg",
    "Corr",
    "CovarPop",
    "RegrAvgX",
    "RegrAvgY",
    "RegrCount",
    "RegrIntercept",
    "RegrR2",
    "RegrSlope",
    "RegrSXX",
    "RegrSXY",
    "RegrSYY",
    "StatAggregate",
}

# Everything else under django.contrib.postgres (indexes, constraints,
# operations) - also Postgres-only, but less common, so lumped into one code.
POSTGRES_OTHER_MODULES = {
    "django.contrib.postgres.indexes",
    "django.contrib.postgres.constraints",
    "django.contrib.postgres.operations",
    "django.contrib.postgres.functions",
    "django.contrib.postgres.validators",
}

# Postgres syntax SQLite rejects. ON CONFLICT, RETURNING, ->>, and SERIAL are
# intentionally absent - see the module docstring.
RAW_SQL_MARKERS = (
    "ilike",
    "::",
    "#>>",
    "gen_random_uuid(",
    "distinct on",
    "for update",
    "skip locked",
    "at time zone",
    "to_tsvector(",
    "to_tsquery(",
    "unnest(",
    "generate_series(",
    "string_agg(",
    "array_agg(",
    "interval '",
    "similar to",
    "alter column",
    "add constraint",
    "drop constraint",
)

RAW_SQL_CALL_NAMES = {"RunSQL", "execute", "raw"}

# Postgres LATERAL joins have no SQLite equivalent. Word-bounded so a column
# named "bilateral" does not match.
LATERAL_RE = re.compile(r"\blateral\b", re.IGNORECASE)

# .extra() needs manual review. The other three run, but not the way they do
# on PostgreSQL: SQLite ignores the call or the clause instead of honoring it.
WARN_CODES = {"DBP404", "DBP408", "DBP409", "DBP410"}


def _specified(node):
    """True when a keyword was passed and isn't None or an empty list/tuple."""
    if node is None or is_none(node):
        return False
    if isinstance(node, (ast.List, ast.Tuple)) and not node.elts:
        return False
    return True


class _Visitor(ast.NodeVisitor):
    def __init__(self):
        self.errors = []

    def _add(self, node, code, message):
        self.errors.append((node.lineno, node.col_offset, f"{code} {message}"))

    def visit_ImportFrom(self, node):
        module = node.module or ""
        if module == "django.contrib.postgres.fields":
            for alias in node.names:
                if alias.name in POSTGRES_FIELD_NAMES or alias.name == "*":
                    self._add(
                        node,
                        "DBP401",
                        f"'{alias.name}' is a PostgreSQL-only field type and "
                        "has no SQLite equivalent",
                    )
        elif module == "django.contrib.postgres.search":
            for alias in node.names:
                self._add(
                    node,
                    "DBP402",
                    f"'{alias.name}' is PostgreSQL full-text search and will "
                    "not work against SQLite (which has its own FTS5 API, "
                    "not SearchVector/SearchQuery)",
                )
        elif module == "django.contrib.postgres.aggregates":
            for alias in node.names:
                self._add(
                    node,
                    "DBP403",
                    f"'{alias.name}' is a PostgreSQL-only aggregate",
                )
        elif module in POSTGRES_OTHER_MODULES:
            self._add(
                node,
                "DBP406",
                f"'{module}' is PostgreSQL-specific (indexes/constraints/"
                "operations do not exist on SQLite)",
            )
        self.generic_visit(node)

    def visit_Call(self, node):
        func_name = dotted_name(node.func)
        short_name = func_name.rsplit(".", 1)[-1] if func_name else ""

        if short_name == "extra":
            self._add(
                node,
                "DBP404",
                ".extra() injects raw SQL fragments - review for "
                "PostgreSQL-only syntax before running on SQLite",
            )

        if short_name in RAW_SQL_CALL_NAMES and node.args:
            sql = string_constant(node.args[0])
            if sql is not None:
                lowered = sql.lower()
                hits = [m for m in RAW_SQL_MARKERS if m in lowered]
                # `#>` is Postgres-only too, but it is a prefix of `#>>`,
                # which is already reported on its own.
                if "#>" in lowered.replace("#>>", ""):
                    hits.append("#>")
                if LATERAL_RE.search(lowered):
                    hits.append("LATERAL")
                if hits:
                    self._add(
                        node,
                        "DBP405",
                        f"raw SQL contains PostgreSQL-specific syntax "
                        f"({', '.join(hits)}) - will not run on SQLite as-is",
                    )

        if short_name == "distinct" and (node.args or node.keywords):
            self._add(
                node,
                "DBP407",
                ".distinct(*fields) is PostgreSQL's DISTINCT ON extension - "
                "SQLite only supports argument-less .distinct() and raises "
                "NotSupportedError otherwise",
            )

        if short_name == "select_for_update":
            self._add(
                node,
                "DBP408",
                ".select_for_update() does not lock rows on SQLite: a bare "
                "call is ignored, and nowait/skip_locked/of raise "
                "NotSupportedError",
            )

        if short_name == "UniqueConstraint":
            deferrable = keyword_value(node, "deferrable")
            if _specified(deferrable):
                self._add(
                    node,
                    "DBP409",
                    "UniqueConstraint(deferrable=...) is ignored on SQLite, "
                    "so a unique constraint that PostgreSQL defers until "
                    "commit is enforced immediately there",
                )

        if short_name in {"Index", "UniqueConstraint"}:
            opclasses = keyword_value(node, "opclasses")
            if _specified(opclasses):
                self._add(
                    node,
                    "DBP410",
                    f"{short_name}(opclasses=...) uses a PostgreSQL operator "
                    "class, which SQLite ignores - the index is created "
                    "without it",
                )

        self.generic_visit(node)


def run(tree):
    """Return sorted (lineno, col, "CODE message") tuples for a parsed module."""
    visitor = _Visitor()
    visitor.visit(tree)
    return sorted(visitor.errors)
