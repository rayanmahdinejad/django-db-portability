import ast

from db_portability.checks.postgres_mysql import run


def check(source):
    tree = ast.parse(source)
    return run(tree)


def test_flags_postgres_only_field_import():
    errors = check("from django.contrib.postgres.fields import ArrayField\n")
    assert any(msg.startswith("DBP201") for _, _, msg in errors)


def test_flags_postgres_search_import():
    errors = check("from django.contrib.postgres.search import SearchVector\n")
    assert any(msg.startswith("DBP202") for _, _, msg in errors)


def test_flags_postgres_aggregate_import():
    errors = check("from django.contrib.postgres.aggregates import ArrayAgg\n")
    assert any(msg.startswith("DBP203") for _, _, msg in errors)


def test_flags_extra_call():
    errors = check("qs = SomeModel.objects.extra(where=['1=1'])\n")
    assert any(msg.startswith("DBP204") for _, _, msg in errors)


def test_flags_on_conflict_in_raw_sql():
    errors = check(
        "cursor.execute('INSERT INTO t VALUES (1) ON CONFLICT DO NOTHING')\n"
    )
    assert any(msg.startswith("DBP205") for _, _, msg in errors)


def test_flags_cast_syntax_in_raw_sql():
    errors = check("cursor.execute(\"SELECT id::text FROM t\")\n")
    assert any(msg.startswith("DBP205") for _, _, msg in errors)


def test_ignores_plain_raw_sql():
    errors = check("cursor.execute('SELECT * FROM t WHERE id = %s', [1])\n")
    assert errors == []


def test_does_not_flag_serial_in_raw_sql():
    # MySQL supports SERIAL as a column-type alias, so this is not breakage.
    errors = check("cursor.execute('CREATE TABLE t (id SERIAL)')\n")
    assert errors == []


def test_does_not_flag_json_arrow_in_raw_sql():
    # MySQL supports ->> for JSON path extraction too (5.7.13+).
    errors = check("cursor.execute(\"SELECT data->>'$.x' FROM t\")\n")
    assert errors == []


def test_flags_postgres_other_module_import():
    errors = check("from django.contrib.postgres.indexes import GinIndex\n")
    assert any(msg.startswith("DBP206") for _, _, msg in errors)


def test_flags_distinct_with_fields():
    errors = check("SomeModel.objects.distinct('name')\n")
    assert any(msg.startswith("DBP207") for _, _, msg in errors)


def test_does_not_flag_bare_distinct():
    errors = check("SomeModel.objects.distinct()\n")
    assert errors == []


def test_flags_char_field_without_max_length():
    errors = check("name = models.CharField()\n")
    assert any(msg.startswith("DBP208") for _, _, msg in errors)


def test_does_not_flag_char_field_with_max_length():
    errors = check("name = models.CharField(max_length=150)\n")
    assert errors == []


def test_does_not_flag_serializer_char_field_without_max_length():
    errors = check("name = serializers.CharField(required=False)\n")
    assert errors == []


def test_flags_long_unique_char_field_for_mysql_index_limit():
    errors = check("code = models.CharField(max_length=255, unique=True)\n")
    assert any(msg.startswith("DBP209") for _, _, msg in errors)


def test_flags_long_db_indexed_char_field_for_mysql_index_limit():
    errors = check("code = models.CharField(max_length=255, db_index=True)\n")
    assert any(msg.startswith("DBP209") for _, _, msg in errors)


def test_does_not_flag_short_unique_char_field():
    errors = check("code = models.CharField(max_length=100, unique=True)\n")
    assert errors == []


def test_does_not_flag_long_char_field_without_unique_or_index():
    errors = check("code = models.CharField(max_length=255)\n")
    assert errors == []
