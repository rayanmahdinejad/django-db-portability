"""
Rules for the postgres -> mysql pair: flags Django ORM / raw-SQL usage that
is known to work on PostgreSQL but silently break (or behave differently) on
MySQL/MariaDB.

This does not try to make a project fully database-agnostic - Django's ORM
already handles that for the common cases. It only flags the specific,
well-documented leaks: Postgres-only contrib modules, raw SQL with
Postgres-only syntax, `.distinct(*fields)`, the declared-length requirement
on character columns, and MySQL's index key-length limit.

Unlike postgres -> oracle, there is no NULL/empty-string trap here: MySQL,
like PostgreSQL, stores '' as a real, non-NULL value rather than coercing it
to NULL.

Codes DBP2xx are reserved for this pair, per the block scheme described in
db_portability.checks.REGISTRY.
"""
from db_portability.checks.base import (
    direct_assignment_call_ids,
    dotted_name,
    is_non_model_field_call,
    is_none,
    is_true,
    keyword_value,
    string_constant,
)
import ast

SOURCE = "postgres"
TARGET = "mysql"

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

# Unlike the postgres -> oracle list this doesn't include "serial" or "->>":
# MySQL supports both (SERIAL as a column-type alias, ->> as its own JSON
# path-extraction operator since 5.7.13), so neither would actually break.
RAW_SQL_MARKERS = (
    "on conflict",
    "returning",
    "ilike",
    "gen_random_uuid(",
    "#>>",
    "::",
)

RAW_SQL_CALL_NAMES = {"RunSQL", "execute", "raw"}

CHAR_BASED_FIELDS = {
    "CharField",
    "TextField",
    "SlugField",
    "EmailField",
    "URLField",
}

# Conservative estimate of MySQL's InnoDB index key-length limit expressed in
# utf8mb4 characters (4 bytes/char). Historically 767 bytes (pre-5.7.7, or
# innodb_large_prefix disabled) -> 191 chars; innodb_large_prefix (default
# since 5.7.7) raises this to 3072 bytes -> 768 chars. Flagged as a WARN
# since whether it actually breaks depends on server version/config.
MYSQL_UTF8MB4_INDEX_LIMIT = 191

# DBP204 (.extra()) and DBP209 (index key-length risk) need manual review /
# depend on server config rather than being guaranteed breakage.
WARN_CODES = {"DBP204", "DBP209"}


class _Visitor(ast.NodeVisitor):
    def __init__(self, direct_field_calls=frozenset()):
        self.errors = []
        self.direct_field_calls = direct_field_calls

    def _add(self, node, code, message):
        self.errors.append((node.lineno, node.col_offset, f"{code} {message}"))

    def visit_ImportFrom(self, node):
        module = node.module or ""
        if module == "django.contrib.postgres.fields":
            for alias in node.names:
                if alias.name in POSTGRES_FIELD_NAMES or alias.name == "*":
                    self._add(
                        node,
                        "DBP201",
                        f"'{alias.name}' is a PostgreSQL-only field type and "
                        "has no MySQL equivalent",
                    )
        elif module == "django.contrib.postgres.search":
            for alias in node.names:
                self._add(
                    node,
                    "DBP202",
                    f"'{alias.name}' is PostgreSQL full-text search and will "
                    "not work against MySQL (which has its own, incompatible "
                    "FULLTEXT/MATCH AGAINST API)",
                )
        elif module == "django.contrib.postgres.aggregates":
            for alias in node.names:
                self._add(
                    node,
                    "DBP203",
                    f"'{alias.name}' is a PostgreSQL-only aggregate",
                )
        elif module in POSTGRES_OTHER_MODULES:
            self._add(
                node,
                "DBP206",
                f"'{module}' is PostgreSQL-specific (indexes/constraints/"
                "operations do not exist on MySQL)",
            )
        self.generic_visit(node)

    def visit_Call(self, node):
        func_name = dotted_name(node.func)
        short_name = func_name.rsplit(".", 1)[-1] if func_name else ""

        if short_name == "extra":
            self._add(
                node,
                "DBP204",
                ".extra() injects raw SQL fragments - review for "
                "PostgreSQL-only syntax before running on MySQL",
            )

        if short_name in RAW_SQL_CALL_NAMES and node.args:
            sql = string_constant(node.args[0])
            if sql is not None:
                lowered = sql.lower()
                hits = [m for m in RAW_SQL_MARKERS if m in lowered]
                if hits:
                    self._add(
                        node,
                        "DBP205",
                        f"raw SQL contains PostgreSQL-specific syntax "
                        f"({', '.join(hits)}) - will not run on MySQL as-is",
                    )

        if short_name == "distinct" and (node.args or node.keywords):
            self._add(
                node,
                "DBP207",
                ".distinct(*fields) is PostgreSQL's DISTINCT ON extension - "
                "MySQL (and every other backend) only supports argument-less "
                ".distinct()",
            )

        if (
            short_name == "CharField"
            and not is_non_model_field_call(func_name)
            and id(node) in self.direct_field_calls
        ):
            max_length = keyword_value(node, "max_length")
            if max_length is None or is_none(max_length):
                self._add(
                    node,
                    "DBP208",
                    "CharField without max_length: PostgreSQL's varchar "
                    "needs no declared length (supports_unlimited_charfield), "
                    "but MySQL's VARCHAR requires one - Django's system "
                    "checks (fields.E120) will fail on MySQL",
                )

        if (
            short_name in CHAR_BASED_FIELDS
            and not is_non_model_field_call(func_name)
            and id(node) in self.direct_field_calls
        ):
            unique = keyword_value(node, "unique")
            db_index = keyword_value(node, "db_index")
            if is_true(unique) or is_true(db_index):
                max_length = keyword_value(node, "max_length")
                length = (
                    max_length.value
                    if isinstance(max_length, ast.Constant)
                    and isinstance(max_length.value, int)
                    else None
                )
                if length is not None and length > MYSQL_UTF8MB4_INDEX_LIMIT:
                    self._add(
                        node,
                        "DBP209",
                        f"{short_name}(max_length={length}, "
                        f"unique=True/db_index=True): PostgreSQL has no "
                        "index-length limit, but MySQL's InnoDB index "
                        "key-length limit can reject an index on a "
                        f"utf8mb4 column over ~{MYSQL_UTF8MB4_INDEX_LIMIT} "
                        "characters ('Specified key was too long') - the "
                        "exact threshold depends on server version/config, "
                        "so this needs manual review",
                    )

        self.generic_visit(node)


def run(tree):
    """Return sorted (lineno, col, "CODE message") tuples for a parsed module."""
    visitor = _Visitor(direct_field_calls=direct_assignment_call_ids(tree))
    visitor.visit(tree)
    return sorted(visitor.errors)
