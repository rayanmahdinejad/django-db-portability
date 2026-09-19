import ast

from db_portability.lint import PostgresPortabilityChecker


def run(source):
    tree = ast.parse(source)
    checker = PostgresPortabilityChecker(tree, filename="test.py")
    return [(lineno, col, msg) for lineno, col, msg, _ in checker.run()]


def test_flags_postgres_array_field_import():
    errors = run("from django.contrib.postgres.fields import ArrayField\n")
    assert any(msg.startswith("DBP001") for _, _, msg in errors)


def test_flags_postgres_search_import():
    errors = run(
        "from django.contrib.postgres.search import SearchVector, SearchQuery\n"
    )
    codes = [msg.split()[0] for _, _, msg in errors]
    assert codes == ["DBP002", "DBP002"]


def test_flags_postgres_aggregate_import():
    errors = run("from django.contrib.postgres.aggregates import ArrayAgg\n")
    assert any(msg.startswith("DBP003") for _, _, msg in errors)


def test_flags_postgres_index_module():
    errors = run("from django.contrib.postgres.indexes import GinIndex\n")
    assert any(msg.startswith("DBP007") for _, _, msg in errors)


def test_ignores_unrelated_imports():
    errors = run("from django.db import models\n")
    assert errors == []


def test_flags_extra_call():
    errors = run("qs = SomeModel.objects.extra(where=['1=1'])\n")
    assert any(msg.startswith("DBP004") for _, _, msg in errors)


def test_flags_raw_sql_on_conflict():
    errors = run(
        "migrations.RunSQL('INSERT INTO t VALUES (1) ON CONFLICT DO NOTHING')\n"
    )
    assert any(msg.startswith("DBP005") for _, _, msg in errors)


def test_flags_raw_sql_ilike():
    errors = run("cursor.execute(\"SELECT * FROM t WHERE name ILIKE 'a%'\")\n")
    assert any(msg.startswith("DBP005") for _, _, msg in errors)


def test_ignores_plain_raw_sql():
    errors = run("cursor.execute('SELECT * FROM t WHERE id = %s', [1])\n")
    assert errors == []


def test_flags_unique_blank_without_null():
    errors = run("code = models.CharField(max_length=10, unique=True, blank=True)\n")
    assert any(msg.startswith("DBP006") for _, _, msg in errors)


def test_does_not_flag_unique_blank_with_null():
    errors = run(
        "code = models.CharField(max_length=10, unique=True, blank=True, null=True)\n"
    )
    assert errors == []


def test_does_not_flag_unique_without_blank():
    errors = run("code = models.CharField(max_length=10, unique=True)\n")
    assert errors == []


def test_flags_distinct_on_fields():
    errors = run("qs = SomeModel.objects.order_by('name').distinct('name')\n")
    assert any(msg.startswith("DBP008") for _, _, msg in errors)


def test_does_not_flag_plain_distinct():
    errors = run("qs = SomeModel.objects.distinct()\n")
    assert errors == []
