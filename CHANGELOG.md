# Changelog

All notable changes to this project are documented here.
Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

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
