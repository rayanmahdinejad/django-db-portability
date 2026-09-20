from db_portability import cli
from db_portability.checks import postgres_oracle


def test_scan_file_collects_sorted_errors(tmp_path):
    f = tmp_path / "models.py"
    f.write_text(
        "from django.contrib.postgres.fields import ArrayField\n"
        "from django.contrib.postgres.aggregates import ArrayAgg\n"
    )
    errors, syntax_err = cli.scan_file(str(f), postgres_oracle)
    assert syntax_err is None
    codes = [msg.split()[0] for _, _, msg in errors]
    assert codes == ["DBP001", "DBP003"]


def test_scan_file_reports_syntax_error(tmp_path):
    f = tmp_path / "broken.py"
    f.write_text("def broken(:\n")
    errors, syntax_err = cli.scan_file(str(f), postgres_oracle)
    assert errors is None
    assert syntax_err is not None


def test_iter_python_files_skips_excluded_dirs(tmp_path):
    (tmp_path / "migrations").mkdir()
    (tmp_path / "migrations" / "0001_initial.py").write_text("x = 1\n")
    (tmp_path / "models.py").write_text("x = 1\n")

    found = set(cli.iter_python_files([str(tmp_path)], cli.DEFAULT_EXCLUDES))
    assert str(tmp_path / "models.py") in found
    assert str(tmp_path / "migrations" / "0001_initial.py") not in found


def test_main_returns_1_when_issues_found(tmp_path, capsys):
    f = tmp_path / "models.py"
    f.write_text("from django.contrib.postgres.fields import ArrayField\n")
    exit_code = cli.main(["--no-color", str(f)])
    out = capsys.readouterr().out
    assert exit_code == 1
    assert "DBP001" in out


def test_main_returns_0_when_clean(tmp_path, capsys):
    f = tmp_path / "models.py"
    f.write_text("x = 1\n")
    exit_code = cli.main(["--no-color", str(f)])
    out = capsys.readouterr().out
    assert exit_code == 0
    assert "No postgres -> oracle portability issues found." in out


def test_main_supports_from_to_flags(tmp_path, capsys):
    f = tmp_path / "models.py"
    f.write_text("x = 1\n")
    exit_code = cli.main(["--no-color", "--from", "postgres", "--to", "oracle", str(f)])
    assert exit_code == 0


def test_main_supports_oracle_to_postgres(tmp_path, capsys):
    f = tmp_path / "models.py"
    f.write_text("cursor.execute('SELECT * FROM t WHERE ROWNUM <= 10')\n")
    exit_code = cli.main(
        ["--no-color", "--from", "oracle", "--to", "postgres", str(f)]
    )
    out = capsys.readouterr().out
    assert exit_code == 1
    assert "DBP101" in out


def test_main_rejects_unregistered_pair(tmp_path, capsys):
    f = tmp_path / "models.py"
    f.write_text("x = 1\n")
    exit_code = cli.main(["--no-color", "--from", "mysql", "--to", "oracle", str(f)])
    err = capsys.readouterr().err
    assert exit_code == 2
    assert "mysql" in err
