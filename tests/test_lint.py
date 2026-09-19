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


def test_flags_char_field_without_max_length():
    errors = run("section_title = models.CharField(null=True)\n")
    assert any(msg.startswith("DBP009") for _, _, msg in errors)


def test_flags_char_field_with_max_length_none():
    errors = run("section_title = models.CharField(max_length=None, null=True)\n")
    assert any(msg.startswith("DBP009") for _, _, msg in errors)


def test_does_not_flag_char_field_with_max_length():
    errors = run("section_title = models.CharField(max_length=150, null=True)\n")
    assert errors == []


def test_flags_aggregate_with_subquery_in_annotate():
    errors = run(
        "qs = UserCourse.objects.annotate(\n"
        "    total=Count('content', distinct=True),\n"
        "    completed=Subquery(inner_qs.values('n')[:1]),\n"
        ")\n"
    )
    assert any(msg.startswith("DBP010") for _, _, msg in errors)


def test_flags_aggregate_with_subquery_used_later_in_update():
    errors = run(
        "qs = UserCourse.objects.annotate(\n"
        "    total=Count('content', distinct=True),\n"
        "    new_status=Case(When(total=0, then=Subquery(inner_qs)), default=1),\n"
        ")\n"
        "UserCourse.objects.filter(pk__in=qs).update(status=Subquery(qs))\n"
    )
    assert any(msg.startswith("DBP010") for _, _, msg in errors)


def test_does_not_flag_annotate_with_only_aggregate():
    errors = run("qs = UserCourse.objects.annotate(total=Count('content'))\n")
    assert errors == []


def test_does_not_flag_annotate_with_only_subquery():
    errors = run(
        "qs = UserCourse.objects.annotate(latest=Subquery(inner_qs.values('n')[:1]))\n"
    )
    assert errors == []


def test_flags_aggregate_annotate_on_model_with_json_field():
    errors = run(
        "class Trainee(models.Model):\n"
        "    business_info = models.JSONField()\n"
        "\n"
        "qs = Trainee.objects.filter(active=True).annotate(\n"
        "    open_courses=Count('user_id__usercourse', distinct=True),\n"
        ")\n"
    )
    assert any(msg.startswith("DBP011") for _, _, msg in errors)


def test_does_not_flag_aggregate_annotate_after_values():
    errors = run(
        "class Trainee(models.Model):\n"
        "    business_info = models.JSONField()\n"
        "\n"
        "qs = Trainee.objects.values('id', 'name').annotate(total=Count('x'))\n"
    )
    assert errors == []


def test_does_not_flag_aggregate_annotate_after_only():
    errors = run(
        "class Trainee(models.Model):\n"
        "    business_info = models.JSONField()\n"
        "\n"
        "qs = Trainee.objects.only('id').annotate(total=Count('x'))\n"
    )
    assert errors == []


def test_does_not_flag_aggregate_annotate_without_json_field():
    errors = run(
        "class UserCourse(models.Model):\n"
        "    status = models.CharField(max_length=10)\n"
        "\n"
        "qs = UserCourse.objects.annotate(total=Count('content'))\n"
    )
    assert errors == []
