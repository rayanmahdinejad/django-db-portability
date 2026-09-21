# django-db-portability

Catches Django code written for one database that will break when ported to
another, and provides runtime helpers for the one divergence static analysis
can't catch: Oracle silently treats `''` as `NULL`, PostgreSQL doesn't.

This does **not** try to make Django fully database-agnostic — Django's ORM
already handles the common cases (pagination, joins, sequences). It targets
the specific, well-documented gaps that leak through: source-DB-only
`contrib` modules, raw SQL with source-DB-only syntax, and the
empty-string/NULL trap.

Checks are organized by `(source, target)` pair. **`postgres -> oracle`,
`oracle -> postgres`, `postgres -> mysql`, and `mysql -> postgres` are
implemented today** — see `src/db_portability/checks/`. Adding another pair
(e.g. `mysql -> oracle`) means writing a sibling module and registering it;
`dbp-scan`'s `--from`/`--to` picks it up automatically once it exists.

## Install

```bash
pip install django-db-portability          # lint checks only
pip install "django-db-portability[django]" # + runtime helpers (fields/managers)
```

## 1. Static checks

### flake8 plugin

Runs automatically once installed — flake8 picks up plugins from
`flake8.extension` entry points. Always runs the `postgres -> oracle` checks
(flake8 plugins have no natural way to expose a `--from`/`--to` pair):

```bash
flake8 --select=DBP myproject/
```

| Code | Flags |
|------|-------|
| DBP001 | Postgres-only field (`ArrayField`, `HStoreField`, `CITextField`, range fields, ...) |
| DBP002 | Postgres full-text search (`SearchVector`, `SearchQuery`, `TrigramSimilarity`, ...) |
| DBP003 | Postgres-only aggregate (`ArrayAgg`, `StringAgg`, `BoolAnd`, ...) |
| DBP004 | `.extra()` — raw SQL fragment, needs manual review |
| DBP005 | Raw SQL (`RunSQL`, `cursor.execute`, `.raw()`) containing Postgres-only syntax (`ON CONFLICT`, `RETURNING`, `ILIKE`, `::` casts, ...) |
| DBP006 | `CharField`/`TextField(unique=True, blank=True)` without `null=True` — the NULL/empty-string trap below |
| DBP007 | Other Postgres-only `contrib` modules (indexes, constraints, operations) |
| DBP008 | `.distinct(*fields)` — PostgreSQL's `DISTINCT ON`, unsupported on every other backend |
| DBP009 | `CharField` without `max_length` — fine on Postgres, fails Oracle's system check (`fields.E120`) |
| DBP010 | `.annotate()` combining an aggregate (`Count`, `Sum`, ...) with a `Subquery`-based annotation — the resulting `GROUP BY` contains a subquery expression, which Oracle rejects (`ORA-22818`), even if the queryset is only ever used as the value inside another `.update(col=Subquery(...))` |
| DBP011 | `.annotate()` with an aggregate (`Count`, `Sum`, ...) on a model known (in the same file) to have a `JSONField`, without a prior `.values()`/`.only()` to narrow the `SELECT` — the aggregate forces `GROUP BY` on every other selected column, and Oracle rejects a `JSONField`'s `CLOB`/`NCLOB` column there (`ORA-00932`), even though PostgreSQL's `jsonb` tolerates it |

DBP0xx is reserved for `postgres -> oracle`. A future pair gets its own
block (DBP1xx, DBP2xx, ...) so codes stay stable as pairs are added.

DBP011 links a queryset back to its model by name within the same file (no
Django app registry is loaded), so it won't catch the model and the
`.annotate()` call living in separate files (e.g. `models.py` vs `views.py`)
— only cases where both appear together, such as a manager/queryset method
defined on the model itself.

Add to your CI lint step or `setup.cfg`:

```ini
[flake8]
select = E,F,DBP
```

### the reverse direction: `oracle -> postgres`

Not exposed through the flake8 plugin (which always runs `postgres ->
oracle` — see above), but available through `dbp-scan --from oracle --to
postgres`. This pair is smaller: PostgreSQL is generally more permissive
than Oracle, so most of what leaks through going this direction is raw SQL
written against Oracle-only syntax, plus the empty-string/NULL trap biting
in the opposite direction.

| Code | Flags |
|------|-------|
| DBP101 | Raw SQL (`RunSQL`, `cursor.execute`, `.raw()`) containing Oracle-specific syntax (`ROWNUM`, `SYSDATE`, `NVL(`, `DECODE(`, `CONNECT BY`, `MINUS`, `DUAL`, `.NEXTVAL`/`.CURRVAL`, ...) |
| DBP102 | `.extra()` — raw SQL fragment, needs manual review |
| DBP103 | `CharField`/`TextField(unique=True, blank=True)` without `null=True` — the reverse NULL/empty-string trap: Oracle coerces repeated blanks to `NULL` (so they pass the unique constraint), PostgreSQL doesn't, so a second blank row that worked on Oracle raises a unique-constraint violation on PostgreSQL |

DBP1xx is reserved for `oracle -> postgres`.

### `postgres -> mysql`

Also not exposed through the flake8 plugin — available through `dbp-scan
--from postgres --to mysql`. Similar shape to `postgres -> oracle` (same
Postgres-only `contrib` modules, same raw-SQL and `.distinct(*fields)`
risks, same declared-length requirement on character columns), plus
MySQL's InnoDB index key-length limit, which Postgres has no equivalent
of. There is **no** empty-string/NULL trap in this direction: MySQL, like
PostgreSQL, stores `''` as a real, non-NULL value — that divergence is
specific to Oracle.

| Code | Flags |
|------|-------|
| DBP201 | Postgres-only field (`ArrayField`, `HStoreField`, `CITextField`, range fields, ...) |
| DBP202 | Postgres full-text search (`SearchVector`, `SearchQuery`, `TrigramSimilarity`, ...) — MySQL has its own, incompatible `FULLTEXT`/`MATCH AGAINST` API |
| DBP203 | Postgres-only aggregate (`ArrayAgg`, `StringAgg`, `BoolAnd`, ...) |
| DBP204 | `.extra()` — raw SQL fragment, needs manual review |
| DBP205 | Raw SQL (`RunSQL`, `cursor.execute`, `.raw()`) containing Postgres-only syntax (`ON CONFLICT`, `RETURNING`, `ILIKE`, `::` casts, ...) |
| DBP206 | Other Postgres-only `contrib` modules (indexes, constraints, operations) |
| DBP207 | `.distinct(*fields)` — PostgreSQL's `DISTINCT ON`, unsupported on MySQL |
| DBP208 | `CharField` without `max_length` — fine on Postgres, but MySQL's `VARCHAR` requires a declared length (fails Django's `fields.E120` on MySQL too) |
| DBP209 | `CharField`/`TextField(unique=True)` or `db_index=True` with `max_length` over ~191 characters — PostgreSQL has no index-length limit, but MySQL's InnoDB key-length limit can reject the index on a `utf8mb4` column that long (`Specified key was too long`); the exact threshold depends on server version/config, so this needs manual review |

DBP2xx is reserved for `postgres -> mysql`.

### `mysql -> postgres`

Available through `dbp-scan --from mysql --to postgres`. Like `oracle ->
postgres`, this is a smaller pair: PostgreSQL is a stricter, more
standards-compliant engine, so most of what leaks through here is raw SQL
written against MySQL-only syntax. No empty-string/NULL trap in this
direction either — see above.

| Code | Flags |
|------|-------|
| DBP301 | Raw SQL (`RunSQL`, `cursor.execute`, `.raw()`) containing MySQL-specific syntax (backtick identifiers, `AUTO_INCREMENT`, `ON DUPLICATE KEY UPDATE`, `GROUP_CONCAT(`, `IFNULL(`, `STR_TO_DATE(`, `DATE_FORMAT(`, `UNSIGNED`, the `LIMIT offset, count` comma form, ...) |
| DBP302 | `.extra()` — raw SQL fragment, needs manual review |

DBP3xx is reserved for `mysql -> postgres`.

### `dbp-scan` — readable terminal output

`flake8 --select=DBP` prints one flat line per finding, which turns into an
unreadable wall of text on a real project. `dbp-scan` runs the same checks
but groups findings by file and colorizes them, and lets you pick the
`--from`/`--to` pair (`postgres -> oracle`, `oracle -> postgres`,
`postgres -> mysql`, or `mysql -> postgres` today):

```bash
dbp-scan myproject/                         # postgres -> oracle (default)
dbp-scan --from postgres --to oracle myproject/
dbp-scan --from oracle --to postgres myproject/
dbp-scan --from postgres --to mysql myproject/
dbp-scan --from mysql --to postgres myproject/
dbp-scan --quiet myproject/                 # summary line only
dbp-scan --no-color myproject/ > report.txt
dbp-scan --format html --output report.html myproject/   # standalone HTML report
```

The HTML report is a single self-contained file (no external assets) with a
summary, a per-file breakdown, and a search/severity filter, so it's easy to
open locally or publish as a CI artifact.

It skips `migrations/`, `.venv`, `.git`, `__pycache__`, `node_modules`,
`.tox`, `build`, and `dist` by default (`--exclude NAME` adds more), and
exits `1` if any issues were found — same convention as flake8, so it's
safe to use as a CI gate too. An unregistered pair (e.g. `--from mysql`)
exits `2` with the list of pairs that are actually implemented.

## 2. The NULL / empty-string trap

Oracle coerces `''` to `NULL` for `VARCHAR2`/`CLOB` columns. PostgreSQL does
not. Django's own convention — "never set `null=True` on `CharField`" — is
exactly what makes the two backends disagree: identical code, identical
input, different stored value depending on which `DATABASES` alias the query
hits. It's data-dependent, so it won't show up as a test failure until you
have the right data.

### Option A — swap the field type

```python
from db_portability.fields import PortableCharField

class Widget(models.Model):
    code = PortableCharField(max_length=20, null=True, blank=True)
```

`PortableCharField`/`PortableTextField` normalize `''` → `None` in Python
before the value reaches *either* database, so both backends store and
return the same thing. This requires `null=True` — that's intentional.

### Option B — can't change the field? Query both cases explicitly

```python
from db_portability.managers import empty_or_null_q

Widget.objects.filter(empty_or_null_q("code"))
```

or use the manager mixin:

```python
from db_portability.managers import PortableManager

class Widget(models.Model):
    code = models.CharField(max_length=20, blank=True)
    objects = PortableManager()

Widget.objects.empty_or_null("code")
Widget.objects.exclude_empty_or_null("code")
```

## Development

```bash
python -m venv .venv
.venv\Scripts\pip install -e ".[test]"
.venv\Scripts\pytest
```
