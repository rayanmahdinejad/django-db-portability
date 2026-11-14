"""
Registry of database portability checks, keyed by (source, target).

postgres -> oracle, oracle -> postgres, postgres -> mysql,
mysql -> postgres, and postgres -> sqlite are implemented today. To add
another pair (e.g. mysql -> oracle), write a sibling module exposing
SOURCE, TARGET, and run(tree), then register it below - dbp-scan's
--from/--to picks it up automatically.
"""
from db_portability.checks import (
    mysql_postgres,
    oracle_postgres,
    postgres_mysql,
    postgres_oracle,
    postgres_sqlite,
)

REGISTRY = {
    (postgres_oracle.SOURCE, postgres_oracle.TARGET): postgres_oracle,
    (oracle_postgres.SOURCE, oracle_postgres.TARGET): oracle_postgres,
    (postgres_mysql.SOURCE, postgres_mysql.TARGET): postgres_mysql,
    (mysql_postgres.SOURCE, mysql_postgres.TARGET): mysql_postgres,
    (postgres_sqlite.SOURCE, postgres_sqlite.TARGET): postgres_sqlite,
}


def get_checks(source, target):
    key = (source.lower(), target.lower())
    try:
        return REGISTRY[key]
    except KeyError:
        supported = ", ".join(f"{s} -> {t}" for s, t in available_pairs())
        raise ValueError(
            f"no checks registered for {source} -> {target}. "
            f"Supported pairs: {supported}"
        ) from None


def available_pairs():
    return sorted(REGISTRY)
