import ast

from db_portability.checks.oracle_postgres import run


def check(source):
    tree = ast.parse(source)
    return run(tree)


def test_flags_rownum_in_raw_sql():
    errors = check("cursor.execute('SELECT * FROM t WHERE ROWNUM <= 10')\n")
    assert any(msg.startswith("DBP101") for _, _, msg in errors)


def test_flags_nvl_in_raw_sql():
    errors = check("cursor.execute(\"SELECT NVL(name, 'x') FROM t\")\n")
    assert any(msg.startswith("DBP101") for _, _, msg in errors)


def test_flags_decode_in_raw_sql():
    errors = check("cursor.execute(\"SELECT DECODE(status, 1, 'a', 'b') FROM t\")\n")
    assert any(msg.startswith("DBP101") for _, _, msg in errors)


def test_flags_dual_table_in_raw_sql():
    errors = check("cursor.execute('SELECT SYSDATE FROM DUAL')\n")
    codes = [msg.split()[0] for _, _, msg in errors]
    assert codes == ["DBP101"]


def test_flags_sequence_nextval_in_raw_sql():
    errors = check("cursor.execute('SELECT my_seq.NEXTVAL FROM DUAL')\n")
    assert any(msg.startswith("DBP101") for _, _, msg in errors)


def test_ignores_plain_raw_sql():
    errors = check("cursor.execute('SELECT * FROM t WHERE id = %s', [1])\n")
    assert errors == []


def test_flags_extra_call():
    errors = check("qs = SomeModel.objects.extra(where=['1=1'])\n")
    assert any(msg.startswith("DBP102") for _, _, msg in errors)


def test_flags_unique_blank_without_null():
    errors = check("code = models.CharField(max_length=10, unique=True, blank=True)\n")
    assert any(msg.startswith("DBP103") for _, _, msg in errors)


def test_does_not_flag_unique_blank_with_null():
    errors = check(
        "code = models.CharField(max_length=10, unique=True, blank=True, null=True)\n"
    )
    assert errors == []


def test_does_not_flag_unique_without_blank():
    errors = check("code = models.CharField(max_length=10, unique=True)\n")
    assert errors == []
