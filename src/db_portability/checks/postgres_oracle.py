"""
Rules for the postgres -> oracle pair: flags Django ORM / raw-SQL usage that
is known to work on PostgreSQL but silently break (or behave differently) on
Oracle.

This does not try to make a project fully database-agnostic - Django's ORM
already handles that for the common cases. It only flags the specific,
well-documented leaks: Postgres-only contrib modules, raw SQL with
Postgres-only syntax, and the empty-string/NULL divergence between the two
backends.

Codes DBP0xx are reserved for this pair. A future pair (e.g. mysql -> oracle)
should use its own block (DBP1xx, DBP2xx, ...) so codes stay stable as pairs
are added - see db_portability.checks.REGISTRY.
"""
import ast

from db_portability.checks.base import (
    call_names,
    dotted_name,
    is_none,
    is_true,
    keyword_value,
    string_constant,
)

SOURCE = "postgres"
TARGET = "oracle"

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

RAW_SQL_MARKERS = (
    "on conflict",
    "returning",
    "ilike",
    "serial",
    "gen_random_uuid(",
    "->>",
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

AGGREGATE_FUNC_NAMES = {
    "Count",
    "Sum",
    "Avg",
    "Min",
    "Max",
    "StdDev",
    "Variance",
}

JSON_FIELD_NAMES = {"JSONField"}

# DBP004 (.extra()) and DBP006 (NULL/empty-string trap) need manual review /
# are data-dependent rather than guaranteed breakage - callers may want to
# report them at a lower severity than the rest.
WARN_CODES = {"DBP004", "DBP006"}


def _classes_with_json_field(tree):
    """Names of classes (models) that define at least one JSONField anywhere
    in their body - used by DBP011 to link `Model.objects...annotate(...)`
    back to a model known to carry a CLOB/NCLOB-backed column, without a
    full Django app registry."""
    names = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.ClassDef):
            continue
        for sub in ast.walk(node):
            if isinstance(sub, ast.Call):
                fname = dotted_name(sub.func)
                short = fname.rsplit(".", 1)[-1] if fname else ""
                if short in JSON_FIELD_NAMES:
                    names.add(node.name)
                    break
    return names


def _chain_root_and_calls(node):
    """Walk back through a `Root.a().b().c(...)` call chain starting from
    `node`'s callee. Returns the leftmost Name id (or None) and the set of
    method short-names called earlier in the chain, so callers can tell
    e.g. whether `.values()`/`.only()` already narrowed the SELECT."""
    calls = set()
    current = node.func.value if isinstance(node.func, ast.Attribute) else None
    while isinstance(current, ast.Call):
        fname = dotted_name(current.func)
        short = fname.rsplit(".", 1)[-1] if fname else ""
        if short:
            calls.add(short)
        current = (
            current.func.value if isinstance(current.func, ast.Attribute) else None
        )
    while isinstance(current, ast.Attribute):
        current = current.value
    root = current.id if isinstance(current, ast.Name) else None
    return root, calls


class _Visitor(ast.NodeVisitor):
    def __init__(self, json_field_classes=frozenset()):
        self.errors = []
        self.json_field_classes = json_field_classes

    def _add(self, node, code, message):
        self.errors.append((node.lineno, node.col_offset, f"{code} {message}"))

    def visit_ImportFrom(self, node):
        module = node.module or ""
        if module == "django.contrib.postgres.fields":
            for alias in node.names:
                if alias.name in POSTGRES_FIELD_NAMES or alias.name == "*":
                    self._add(
                        node,
                        "DBP001",
                        f"'{alias.name}' is a PostgreSQL-only field type and "
                        "has no Oracle equivalent",
                    )
        elif module == "django.contrib.postgres.search":
            for alias in node.names:
                self._add(
                    node,
                    "DBP002",
                    f"'{alias.name}' is PostgreSQL full-text search and will "
                    "not work against Oracle",
                )
        elif module == "django.contrib.postgres.aggregates":
            for alias in node.names:
                self._add(
                    node,
                    "DBP003",
                    f"'{alias.name}' is a PostgreSQL-only aggregate",
                )
        elif module in POSTGRES_OTHER_MODULES:
            self._add(
                node,
                "DBP007",
                f"'{module}' is PostgreSQL-specific (indexes/constraints/"
                "operations do not exist on Oracle)",
            )
        self.generic_visit(node)

    def visit_Call(self, node):
        func_name = dotted_name(node.func)
        short_name = func_name.rsplit(".", 1)[-1] if func_name else ""

        if short_name == "extra":
            self._add(
                node,
                "DBP004",
                ".extra() injects raw SQL fragments - review for "
                "PostgreSQL-only syntax before running on Oracle",
            )

        if short_name in RAW_SQL_CALL_NAMES and node.args:
            sql = string_constant(node.args[0])
            if sql is not None:
                lowered = sql.lower()
                hits = [m for m in RAW_SQL_MARKERS if m in lowered]
                if hits:
                    self._add(
                        node,
                        "DBP005",
                        f"raw SQL contains PostgreSQL-specific syntax "
                        f"({', '.join(hits)}) - will not run on Oracle as-is",
                    )

        if short_name == "distinct" and (node.args or node.keywords):
            self._add(
                node,
                "DBP008",
                ".distinct(*fields) is PostgreSQL's DISTINCT ON extension - "
                "Oracle (and every other backend) only supports argument-less "
                ".distinct()",
            )

        if short_name in CHAR_BASED_FIELDS:
            unique = keyword_value(node, "unique")
            blank = keyword_value(node, "blank")
            null = keyword_value(node, "null")
            if is_true(unique) and is_true(blank) and not is_true(null):
                self._add(
                    node,
                    "DBP006",
                    f"{short_name}(unique=True, blank=True) without "
                    "null=True: Oracle coerces '' to NULL but PostgreSQL "
                    "does not, so unique/empty behavior will diverge "
                    "between backends",
                )

        if short_name == "annotate" and (node.args or node.keywords):
            names = set()
            for arg in node.args:
                names |= call_names(arg)
            for kw in node.keywords:
                names |= call_names(kw.value)
            if names & AGGREGATE_FUNC_NAMES and "Subquery" in names:
                self._add(
                    node,
                    "DBP010",
                    ".annotate() combines an aggregate (Count/Sum/Avg/Min/"
                    "Max/...) with a Subquery-based annotation - the "
                    "resulting GROUP BY contains a subquery expression, "
                    "which Oracle rejects (ORA-22818). This holds even if "
                    "the queryset is never iterated directly and is only "
                    "used as the value inside another "
                    ".update(col=Subquery(...))",
                )

            if names & AGGREGATE_FUNC_NAMES:
                root, chain_calls = _chain_root_and_calls(node)
                if root in self.json_field_classes and not (
                    chain_calls & {"values", "only"}
                ):
                    self._add(
                        node,
                        "DBP011",
                        f"'{root}' has a JSONField, and this .annotate() "
                        "aggregate is applied without a prior .values()/"
                        ".only() to narrow the SELECT - Django's GROUP BY "
                        "will include every other selected column, and "
                        "Oracle rejects a JSONField's CLOB/NCLOB column in "
                        "GROUP BY (ORA-00932), even though PostgreSQL's "
                        "jsonb tolerates it",
                    )

        if short_name == "CharField":
            max_length = keyword_value(node, "max_length")
            if max_length is None or is_none(max_length):
                self._add(
                    node,
                    "DBP009",
                    "CharField without max_length: PostgreSQL's varchar "
                    "needs no declared length (supports_unlimited_charfield), "
                    "but Oracle's VARCHAR2 requires one - Django's system "
                    "checks (fields.E120) will fail on Oracle",
                )

        self.generic_visit(node)


def run(tree):
    """Return sorted (lineno, col, "CODE message") tuples for a parsed module."""
    visitor = _Visitor(json_field_classes=_classes_with_json_field(tree))
    visitor.visit(tree)
    return sorted(visitor.errors)
