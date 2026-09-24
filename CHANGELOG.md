# Changelog

All notable changes to this project are documented here.
Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [0.5.0] - 2026-09-24

### Added

- Inline suppression comments for `dbp-scan` findings: `# dbp-scan:
  ignore[CODE] reason` on the same line as a finding excludes it from the
  issue count and exit code, for code that already handles a flagged
  difference at runtime (e.g. a `connection.vendor == "oracle"` branch). A
  comment can list more than one code (`ignore[DBP001,DBP003]`) but must
  carry a reason — one with no reason leaves the finding active and appends
  a note asking for one, instead of silently suppressing it.
- `--show-ignored` lists suppressed findings individually, alongside their
  reason, instead of just folding them into the summary count. Suppressed
  findings always show up as a `(N suppressed)` note in the text summary
  and a "Suppressed" card in the `--format html` report, so they stay
  auditable even without the flag.

## [0.4.0] - 2026-09-21

### Added

- New `postgres -> mysql` check pair (`DBP2xx`), available via `dbp-scan
  --from postgres --to mysql`:
  - DBP201/DBP202/DBP203/DBP206: Postgres-only `contrib` fields, full-text
    search, aggregates, and other modules (indexes/constraints/operations)
    — none of which exist on MySQL either.
  - DBP204: `.extra()` — raw SQL fragment, needs manual review.
  - DBP205: raw SQL containing Postgres-only syntax (`ON CONFLICT`,
    `RETURNING`, `ILIKE`, `::` casts, ...) that won't run on MySQL as-is.
  - DBP207: `.distinct(*fields)` — PostgreSQL's `DISTINCT ON`, unsupported
    on MySQL.
  - DBP208: `CharField` without `max_length` — fine on Postgres, but
    MySQL's `VARCHAR` requires a declared length (`fields.E120`).
  - DBP209: `CharField`/`TextField(unique=True)` or `db_index=True` with
    `max_length` over ~191 characters — PostgreSQL has no index-length
    limit, but MySQL's InnoDB key-length limit can reject an index on a
    `utf8mb4` column that long (`Specified key was too long`).
  - There is no empty-string/NULL trap in this pair: MySQL, like
    PostgreSQL, stores `''` as a real, non-NULL value (that divergence is
    specific to Oracle).
- New `mysql -> postgres` check pair (`DBP3xx`), available via `dbp-scan
  --from mysql --to postgres`:
  - DBP301: raw SQL containing MySQL-specific syntax (backtick
    identifiers, `AUTO_INCREMENT`, `ON DUPLICATE KEY UPDATE`,
    `GROUP_CONCAT(`, `IFNULL(`, `STR_TO_DATE(`, `DATE_FORMAT(`,
    `UNSIGNED`, the `LIMIT offset, count` comma form, ...) that won't run
    on PostgreSQL as-is.
  - DBP302: `.extra()` — raw SQL fragment, needs manual review.

### Changed

- Extracted the model-field-vs-serializer/form-field detection helpers
  (used by DBP009/DBP208 to avoid flagging `serializers.CharField`/
  `forms.CharField`) out of `postgres_oracle` into `checks/base`, so
  `postgres_mysql` can share them instead of duplicating the logic.

## [0.3.0] - 2026-09-21

### Added

- `dbp-scan --format html` renders findings as a standalone HTML report
  (`--output FILE` to name it, defaults to `dbp-scan-report.html`) instead
  of only printing to the terminal: summary counts, a per-file breakdown,
  and a severity/search filter, all in a single self-contained file.

### Changed

- The PyPI publish workflow now runs the test suite before building and
  publishing a release, instead of building/publishing unconditionally.

## [0.2.1] - 2026-09-20

### Fixed

- DBP009 and DBP006 no longer flag `CharField`/`TextField`/etc. calls that
  aren't actual model field declarations:
  - `rest_framework.serializers.CharField(...)` / `django.forms.CharField(...)`
    share a name with `models.CharField` but map to no database column, so
    Oracle's declared-length requirement never applied to them. On a real
    DRF-heavy project this was the overwhelming majority of DBP009's
    findings (e.g. 659 of 665 on one project, all in `serializers.py`/
    `views.py`, none in `models.py`).
  - `models.CharField()` used as a bare `output_field=` type marker inside
    an expression (`Coalesce(..., output_field=CharField())`,
    `Cast(expr, CharField())`) isn't a stored column either, so it's
    exempt from Oracle's `fields.E120` check. DBP009 now only fires when
    the `CharField(...)` call is the direct right-hand side of an
    assignment (`name = models.CharField(...)`).

## [0.2.0] - 2026-09-20

### Added

- New `oracle -> postgres` check pair (`DBP1xx`), available via `dbp-scan
  --from oracle --to postgres` (not exposed through the flake8 plugin,
  which always runs `postgres -> oracle`):
  - DBP101: raw SQL (`RunSQL`, `cursor.execute`, `.raw()`) containing
    Oracle-specific syntax (`ROWNUM`, `SYSDATE`, `NVL(`, `DECODE(`,
    `CONNECT BY`, `MINUS`, `DUAL`, `.NEXTVAL`/`.CURRVAL`, ...) that will
    not run on PostgreSQL as-is.
  - DBP102: `.extra()` — raw SQL fragment, needs manual review.
  - DBP103: `CharField`/`TextField(unique=True, blank=True)` without
    `null=True` — the reverse NULL/empty-string trap: Oracle coerces
    repeated blanks to `NULL` (so they pass the unique constraint),
    PostgreSQL doesn't, so a second blank row that worked on Oracle
    raises a unique-constraint violation there.
- DBP011: `.annotate()` combining an aggregate (`Count`, `Sum`, ...) with a
  model (recognized by name in the same file) that has a `JSONField`,
  without a prior `.values()`/`.only()` to narrow the `SELECT` — Django's
  `GROUP BY` then includes every other selected column, and Oracle rejects
  a `JSONField`'s `CLOB`/`NCLOB` column there (`ORA-00932`), even though
  PostgreSQL's `jsonb` tolerates it.

## [0.1.3] - 2026-09-19

### Added

- DBP010: `.annotate()` combining an aggregate (`Count`, `Sum`, ...) with a
  `Subquery`-based annotation — Oracle rejects the subquery expression this
  forces into the `GROUP BY` (`ORA-22818`). Also fires when that queryset is
  never iterated directly and is only used as the value inside another
  `.update(col=Subquery(...))`.
- DBP009: `CharField` without `max_length` — PostgreSQL's varchar needs no
  declared length, so this passes silently there, but Oracle's VARCHAR2
  requires one and Django's system checks (`fields.E120`) will reject it.

## [0.1.2] - 2026-09-19

### Added

- DBP008: `.distinct(*fields)` — PostgreSQL's `DISTINCT ON` extension,
  unsupported (raises `NotSupportedError`) on every other backend.

## [0.1.1] - 2026-09-18

### Added

- `dbp-scan` now prints an immediate file count and, in an interactive
  terminal, a live per-file progress line on stderr, instead of printing
  nothing until the scan finishes.

## [0.1.0] - 2026-09-18

### Added

- Initial release: DBP001-DBP007 static checks for the `postgres -> oracle`
  pair (Postgres-only fields, full-text search, aggregates, `.extra()`, raw
  SQL with Postgres-only syntax, other `contrib.postgres` modules, and the
  NULL/empty-string trap).
- `PortableCharField` / `PortableTextField` and the `PortableManager` /
  `empty_or_null_q` runtime helpers for the empty-string/NULL divergence.
- `dbp-scan` CLI and the `flake8` `DBP` plugin.
