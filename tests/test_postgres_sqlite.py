import ast

from db_portability.checks.postgres_sqlite import WARN_CODES, run


def check(source):
    tree = ast.parse(source)
    return run(tree)


def test_flags_postgres_only_field_import():
    errors = check("from django.contrib.postgres.fields import ArrayField\n")
    assert any(msg.startswith("DBP401") for _, _, msg in errors)


def test_flags_postgres_search_import():
    errors = check("from django.contrib.postgres.search import SearchVector\n")
    assert any(msg.startswith("DBP402") for _, _, msg in errors)


def test_flags_postgres_aggregate_import():
    errors = check("from django.contrib.postgres.aggregates import ArrayAgg\n")
    assert any(msg.startswith("DBP403") for _, _, msg in errors)


def test_flags_extra_call():
    errors = check("qs = SomeModel.objects.extra(where=['1=1'])\n")
    assert any(msg.startswith("DBP404") for _, _, msg in errors)
    assert "DBP404" in WARN_CODES


def test_flags_ilike_in_raw_sql():
    errors = check("cursor.execute(\"SELECT * FROM t WHERE name ILIKE 'a%'\")\n")
    assert any(msg.startswith("DBP405") for _, _, msg in errors)


def test_flags_cast_syntax_in_raw_sql():
    errors = check('cursor.execute("SELECT id::text FROM t")\n')
    assert any("::" in msg for _, _, msg in errors)


def test_flags_json_path_operator_but_not_arrow():
    errors = check("cursor.execute(\"SELECT data #>> '{a}' FROM t\")\n")
    assert any("#>>" in msg for _, _, msg in errors)
    # A lone #> (jsonb, not text) is also Postgres-only.
    errors = check("cursor.execute(\"SELECT data #> '{a}' FROM t\")\n")
    assert any("#>" in msg and "#>>" not in msg for _, _, msg in errors)


def test_flags_alter_column_and_add_constraint_in_raw_sql():
    errors = check(
        'cursor.execute("ALTER TABLE t ALTER COLUMN name TYPE varchar(20)")\n'
    )
    assert any("alter column" in msg for _, _, msg in errors)
    errors = check(
        'cursor.execute("ALTER TABLE t ADD CONSTRAINT u UNIQUE (name)")\n'
    )
    assert any("add constraint" in msg for _, _, msg in errors)


def test_flags_lateral_join():
    errors = check(
        'cursor.execute("SELECT * FROM t, LATERAL (SELECT 1) s")\n'
    )
    assert any("LATERAL" in msg for _, _, msg in errors)


def test_ignores_plain_raw_sql():
    errors = check("cursor.execute('SELECT * FROM t WHERE id = %s', [1])\n")
    assert errors == []


def test_does_not_flag_on_conflict_or_returning():
    # SQLite supports both. Flagging them would false-positive on current SQLite.
    errors = check(
        "cursor.execute('INSERT INTO t (id) VALUES (1) "
        "ON CONFLICT (id) DO NOTHING RETURNING id')\n"
    )
    assert errors == []


def test_does_not_flag_json_arrow_in_raw_sql():
    # SQLite supports ->> for JSON path extraction (3.38+).
    errors = check("cursor.execute(\"SELECT data->>'$.x' FROM t\")\n")
    assert errors == []


def test_does_not_flag_serial_in_raw_sql():
    # SQLite accepts unknown type names, so this statement runs.
    errors = check("cursor.execute('CREATE TABLE t (id SERIAL)')\n")
    assert errors == []


def test_does_not_flag_django_alter_field_or_add_constraint():
    # The schema editor rebuilds the table; these operations are not raw SQL.
    errors = check(
        "migrations.AlterField('widget', 'name', models.CharField(max_length=20))\n"
        "migrations.AddConstraint(\n"
        "    'widget',\n"
        "    models.UniqueConstraint(fields=['name'], name='uniq_name'),\n"
        ")\n"
    )
    assert errors == []


def test_flags_postgres_other_module_import():
    errors = check("from django.contrib.postgres.indexes import GinIndex\n")
    assert any(msg.startswith("DBP406") for _, _, msg in errors)


def test_flags_distinct_with_fields():
    errors = check("SomeModel.objects.distinct('name')\n")
    assert any(msg.startswith("DBP407") for _, _, msg in errors)


def test_does_not_flag_bare_distinct():
    errors = check("SomeModel.objects.distinct()\n")
    assert errors == []


def test_flags_select_for_update():
    errors = check("SomeModel.objects.select_for_update()\n")
    assert any(msg.startswith("DBP408") for _, _, msg in errors)
    assert "DBP408" in WARN_CODES


def test_flags_deferrable_unique_constraint():
    errors = check(
        "models.UniqueConstraint(\n"
        "    fields=['name'], name='uniq_name', deferrable=Deferrable.DEFERRED,\n"
        ")\n"
    )
    assert any(msg.startswith("DBP409") for _, _, msg in errors)


def test_does_not_flag_immediate_unique_constraint():
    errors = check(
        "models.UniqueConstraint(fields=['name'], name='uniq_name')\n"
    )
    assert errors == []


def test_flags_opclasses():
    errors = check(
        'models.Index(fields=["name"], name="idx_name", '
        'opclasses=["varchar_pattern_ops"])\n'
    )
    assert any(msg.startswith("DBP410") for _, _, msg in errors)


def test_does_not_flag_empty_opclasses():
    errors = check('models.Index(fields=["name"], name="idx_name", opclasses=[])\n')
    assert errors == []


def test_does_not_flag_char_field_without_max_length():
    # SQLite allows VARCHAR with no declared length.
    errors = check("name = models.CharField()\n")
    assert errors == []


def test_does_not_flag_unique_blank_char_field():
    # SQLite stores '' as '', so there is no Oracle-style NULL trap.
    errors = check(
        "code = models.CharField(max_length=10, unique=True, blank=True)\n"
    )
    assert errors == []


def test_does_not_flag_long_unique_char_field():
    # No InnoDB key-length limit on SQLite.
    errors = check("code = models.CharField(max_length=255, unique=True)\n")
    assert errors == []
