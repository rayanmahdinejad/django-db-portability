import ast

from db_portability.checks.mysql_postgres import run


def check(source):
    tree = ast.parse(source)
    return run(tree)


def test_flags_backtick_identifiers_in_raw_sql():
    errors = check("cursor.execute('SELECT `name` FROM `t`')\n")
    assert any(msg.startswith("DBP301") for _, _, msg in errors)


def test_flags_auto_increment_in_raw_sql():
    errors = check(
        "cursor.execute('CREATE TABLE t (id INT AUTO_INCREMENT PRIMARY KEY)')\n"
    )
    assert any(msg.startswith("DBP301") for _, _, msg in errors)


def test_flags_on_duplicate_key_update_in_raw_sql():
    errors = check(
        "cursor.execute('INSERT INTO t VALUES (1) ON DUPLICATE KEY UPDATE x=1')\n"
    )
    assert any(msg.startswith("DBP301") for _, _, msg in errors)


def test_flags_group_concat_in_raw_sql():
    errors = check("cursor.execute('SELECT GROUP_CONCAT(name) FROM t')\n")
    assert any(msg.startswith("DBP301") for _, _, msg in errors)


def test_flags_ifnull_in_raw_sql():
    errors = check("cursor.execute(\"SELECT IFNULL(name, 'x') FROM t\")\n")
    assert any(msg.startswith("DBP301") for _, _, msg in errors)


def test_flags_limit_comma_syntax_in_raw_sql():
    errors = check("cursor.execute('SELECT * FROM t LIMIT 10, 20')\n")
    assert any(msg.startswith("DBP301") for _, _, msg in errors)


def test_ignores_postgres_style_limit_offset():
    errors = check("cursor.execute('SELECT * FROM t LIMIT 20 OFFSET 10')\n")
    assert errors == []


def test_ignores_plain_raw_sql():
    errors = check("cursor.execute('SELECT * FROM t WHERE id = %s', [1])\n")
    assert errors == []


def test_flags_extra_call():
    errors = check("qs = SomeModel.objects.extra(where=['1=1'])\n")
    assert any(msg.startswith("DBP302") for _, _, msg in errors)
