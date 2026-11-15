<p align="center">
  <a href="https://pypi.org/project/django-db-portability/"><img alt="PyPI" src="https://img.shields.io/pypi/v/django-db-portability?style=flat-square&color=0f6e6b"></a>
  <a href="https://pypi.org/project/django-db-portability/"><img alt="Python" src="https://img.shields.io/pypi/pyversions/django-db-portability?style=flat-square&color=0f6e6b"></a>
  <a href="https://github.com/rayanmahdinejad/django-db-portability/blob/main/LICENSE"><img alt="License" src="https://img.shields.io/pypi/l/django-db-portability?style=flat-square&color=0f6e6b"></a>
</p>

<h1 align="center">django-db-portability</h1>

<p align="center">
  Find Django code written for one database that breaks, or behaves differently, on another.
</p>

<p align="center">
  <code>postgres → oracle</code> ·
  <code>oracle → postgres</code> ·
  <code>postgres → mysql</code> ·
  <code>mysql → postgres</code> ·
  <code>postgres → sqlite</code>
</p>

Django's ORM already covers pagination, joins, and sequences. These checks cover what still leaks through: database-only `contrib` modules, raw SQL, and the empty-string / `NULL` trap. Oracle stores `''` as `NULL`. PostgreSQL does not. A runtime helper covers that case, because a scan cannot see the data.

## Install

```bash
pip install django-db-portability            # scanner and flake8 plugin
pip install "django-db-portability[django]"  # plus PortableCharField / PortableManager
```

```bash
dbp-scan myproject/                              # postgres → oracle
dbp-scan --from postgres --to sqlite myproject/  # tests on SQLite, production on PostgreSQL
```

The command exits `1` when it finds anything, so it can gate CI. It skips `migrations/`, virtualenvs, and `.git`. An unknown pair exits `2`.

## A scan

```text
myproject/api/utils.py
  42:5  DBP403 'ArrayAgg' is a PostgreSQL-only aggregate

myproject/services.py
  18:16  DBP408 .select_for_update() does not lock rows on SQLite

2 issue(s) in 2 file(s): DBP403 x1, DBP408 x1
```

Warnings count as findings. The HTML report is one file and makes no network requests:

```bash
dbp-scan --from postgres --to sqlite --format html --output report.html --open myproject/
```

## Pairs

| From | To | Command |
|------|-----|---------|
| postgres | oracle | `dbp-scan myproject/` and `flake8 --select=DBP` |
| oracle | postgres | `dbp-scan --from oracle --to postgres myproject/` |
| postgres | mysql | `dbp-scan --from postgres --to mysql myproject/` |
| mysql | postgres | `dbp-scan --from mysql --to postgres myproject/` |
| postgres | sqlite | `dbp-scan --from postgres --to sqlite myproject/` |

The flake8 plugin always runs `postgres → oracle`. Every other pair is `dbp-scan` only.

```ini
[flake8]
select = E,F,DBP
```

Codes stay in fixed blocks: `DBP0xx` oracle, `DBP1xx` back to postgres, `DBP2xx` mysql, `DBP3xx` back to postgres, `DBP4xx` sqlite. A new pair is a module in `src/db_portability/checks/` with `SOURCE`, `TARGET`, and `run(tree)`.

## Empty string and NULL

Oracle turns `''` into `NULL` on `VARCHAR2` / `CLOB`. PostgreSQL keeps `''`. Django's habit of leaving `null=True` off a `CharField` is what makes the same input store two different values. Tests miss it until that row exists.

Normalize before either database sees the value:

```python
from db_portability.fields import PortableCharField

class Widget(models.Model):
    code = PortableCharField(max_length=20, null=True, blank=True)
```

`PortableCharField` and `PortableTextField` turn `''` into `None`. `null=True` is required.

If the column has to stay as it is, query both forms:

```python
from db_portability.managers import PortableManager

class Widget(models.Model):
    code = models.CharField(max_length=20, blank=True)
    objects = PortableManager()

Widget.objects.empty_or_null("code")
Widget.objects.exclude_empty_or_null("code")
```

`empty_or_null_q("code")` is the same `Q` object when you already have a manager.

## Check reference

Open a pair for the full code list.

<details>
<summary><b>postgres → oracle</b> · DBP001–DBP011 · also the flake8 plugin</summary>

`DBP004` and `DBP006` are warnings. `.extra()` needs a manual look, and the empty-string trap depends on the data.

| Code | Flags |
|------|-------|
| DBP001 | Postgres-only field (`ArrayField`, `HStoreField`, `CITextField`, range fields, ...) |
| DBP002 | Postgres full-text search (`SearchVector`, `SearchQuery`, `TrigramSimilarity`, ...) |
| DBP003 | Postgres-only aggregate (`ArrayAgg`, `StringAgg`, `BoolAnd`, ...) |
| DBP004 | `.extra()` — raw SQL fragment, needs manual review |
| DBP005 | Raw SQL (`RunSQL`, `cursor.execute`, `.raw()`) with Postgres-only syntax (`ON CONFLICT`, `RETURNING`, `ILIKE`, `::` casts, ...) |
| DBP006 | `CharField` / `TextField(unique=True, blank=True)` without `null=True` |
| DBP007 | Other Postgres-only `contrib` modules (indexes, constraints, operations) |
| DBP008 | `.distinct(*fields)` — PostgreSQL `DISTINCT ON` |
| DBP009 | `CharField` without `max_length` — fails Oracle's system check (`fields.E120`) |
| DBP010 | `.annotate()` mixing an aggregate with a `Subquery`. Oracle rejects the subquery in `GROUP BY` (`ORA-22818`), including when that queryset is only used inside `.update(col=Subquery(...))` |
| DBP011 | Aggregate `.annotate()` on a model in the same file that has a `JSONField`, with no earlier `.values()` / `.only()`. Oracle rejects the `CLOB` / `NCLOB` column in `GROUP BY` (`ORA-00932`) |

`DBP011` matches the model and the queryset by name in one file. A model in `models.py` and the call in `views.py` stays invisible.

</details>

<details>
<summary><b>oracle → postgres</b> · DBP101–DBP103</summary>

PostgreSQL accepts most Oracle ORM usage. What still breaks is Oracle-only SQL, and the empty-string trap in reverse: a second blank row that passed a unique constraint on Oracle raises on PostgreSQL.

| Code | Flags |
|------|-------|
| DBP101 | Raw SQL with Oracle syntax (`ROWNUM`, `SYSDATE`, `NVL(`, `DECODE(`, `CONNECT BY`, `MINUS`, `DUAL`, `.NEXTVAL` / `.CURRVAL`, ...) |
| DBP102 | `.extra()` — raw SQL fragment, needs manual review |
| DBP103 | `CharField` / `TextField(unique=True, blank=True)` without `null=True` |

</details>

<details>
<summary><b>postgres → mysql</b> · DBP201–DBP209</summary>

Same Postgres-only modules, raw SQL, and `.distinct(*fields)` as the Oracle pair, plus MySQL's index key-length limit. MySQL stores `''` as `''`, so there is no empty-string trap. `DBP204` and `DBP209` are warnings.

| Code | Flags |
|------|-------|
| DBP201 | Postgres-only field (`ArrayField`, `HStoreField`, `CITextField`, range fields, ...) |
| DBP202 | Postgres full-text search. MySQL's `FULLTEXT` / `MATCH AGAINST` API is a different one |
| DBP203 | Postgres-only aggregate (`ArrayAgg`, `StringAgg`, `BoolAnd`, ...) |
| DBP204 | `.extra()` — raw SQL fragment, needs manual review |
| DBP205 | Raw SQL with Postgres-only syntax (`ON CONFLICT`, `RETURNING`, `ILIKE`, `::` casts, ...) |
| DBP206 | Other Postgres-only `contrib` modules |
| DBP207 | `.distinct(*fields)` — `DISTINCT ON`, unsupported on MySQL |
| DBP208 | `CharField` without `max_length` — MySQL `VARCHAR` needs a length (`fields.E120`) |
| DBP209 | Indexed `CharField` / `TextField` longer than ~191 characters. InnoDB can reject the key (`Specified key was too long`). The limit depends on the server |

</details>

<details>
<summary><b>mysql → postgres</b> · DBP301–DBP302</summary>

Raw SQL written for MySQL. PostgreSQL stores `''` as `''`, so there is no empty-string trap.

| Code | Flags |
|------|-------|
| DBP301 | Raw SQL with MySQL syntax (backticks, `AUTO_INCREMENT`, `ON DUPLICATE KEY UPDATE`, `GROUP_CONCAT(`, `IFNULL(`, `STR_TO_DATE(`, `DATE_FORMAT(`, `UNSIGNED`, `LIMIT offset, count`, ...) |
| DBP302 | `.extra()` — raw SQL fragment, needs manual review |

</details>

<details>
<summary><b>postgres → sqlite</b> · DBP401–DBP410</summary>

Tests on SQLite, production on PostgreSQL. SQLite stores `''`, allows `CharField` without `max_length`, and has no InnoDB key-length limit, so those checks are absent.

`ON CONFLICT`, `RETURNING`, and JSON `->` / `->>` are left alone. SQLite has supported them since 3.24, 3.35, and 3.38. Django rebuilds the table for `AlterField` and `AddConstraint`, so those migration operations are left alone too. The same clauses in raw SQL are flagged, because SQLite rejects `ALTER COLUMN` and `ADD CONSTRAINT` as written.

`DBP404` and `DBP408`–`DBP410` are warnings. The code runs, but not the way it does on PostgreSQL.

| Code | Flags |
|------|-------|
| DBP401 | Postgres-only field (`ArrayField`, `HStoreField`, `CITextField`, range fields, ...) |
| DBP402 | Postgres full-text search. SQLite FTS5 is a different API |
| DBP403 | Postgres-only aggregate (`ArrayAgg`, `StringAgg`, `BoolAnd`, ...) |
| DBP404 | `.extra()` — raw SQL fragment, needs manual review |
| DBP405 | Raw SQL SQLite rejects (`ILIKE`, `::` casts, `#>` / `#>>`, `LATERAL`, `FOR UPDATE`, `gen_random_uuid(`, `ALTER COLUMN`, `ADD CONSTRAINT`, ...) |
| DBP406 | Other Postgres-only `contrib` modules |
| DBP407 | `.distinct(*fields)` — `DISTINCT ON`, raises `NotSupportedError` |
| DBP408 | `.select_for_update()` — a bare call is ignored. `nowait`, `skip_locked`, and `of` raise `NotSupportedError` |
| DBP409 | `UniqueConstraint(deferrable=...)` — ignored, so the constraint is enforced immediately |
| DBP410 | `opclasses` on `Index` / `UniqueConstraint` — ignored, so the index is created without them |

</details>

## dbp-scan

```bash
dbp-scan myproject/
dbp-scan --from postgres --to sqlite myproject/
dbp-scan --quiet myproject/
dbp-scan --no-color myproject/ > report.txt
dbp-scan --format html --output report.html --open myproject/
```

<details>
<summary><b>Every flag</b></summary>

| Option | Default | Description |
|--------|---------|-------------|
| `paths` | `.` | Files or directories to scan. |
| `--from` | `postgres` | Database the code is written for. |
| `--to` | `oracle` | Database being ported to. |
| `--format` | `text` | `html` writes a standalone report. |
| `--output` | `dbp-scan-report.html` | Report path for `--format html`. |
| `--open` | off | Open the HTML report. Text output never launches a browser. |
| `--quiet` | off | Summary line only. The HTML report still lists every finding. |
| `--show-ignored` | off | Print suppressed findings with their reasons. |
| `--no-color` | off | Disable ANSI color. Also honors `NO_COLOR`. Color is off when stdout is not a terminal. |
| `--no-progress` | off | Hide the `[i/N] path` line on stderr. |
| `--exclude` | | Extra directory name to skip. Repeatable. Adds to `migrations/`, `.venv/`, `.git/`, `__pycache__/`, `node_modules/`, `.tox/`, `build/`, `dist/`. |
| `--version` | | Print the installed version and exit. |

</details>

### Silence one line

The comment has to name the code and give a reason. `ignore[DBP001]` with no reason stays active.

```python
from django.contrib.postgres.fields import ArrayField  # dbp-scan: ignore[DBP001] read-only mirror, Oracle side uses a JSON column instead

if connection.vendor == "oracle":
    cursor.execute("SELECT * FROM t WHERE ROWNUM <= 10")  # dbp-scan: ignore[DBP101] oracle-only branch, postgres branch below uses LIMIT
else:
    cursor.execute("SELECT * FROM t LIMIT 10")
```

One comment can list several codes: `ignore[DBP001,DBP003]`. Suppressed findings leave the exit code and still show up as `(M suppressed)`. `--show-ignored` prints them.

## Development

```bash
python -m venv .venv
.venv\Scripts\pip install -e ".[test]"
.venv\Scripts\pytest
```
