"""
Registry of database portability checks, keyed by (source, target).

Only postgres -> oracle exists today. To add another pair (e.g.
mysql -> oracle), write a sibling module exposing SOURCE, TARGET, and
run(tree), then register it below - dbp-scan's --from/--to picks it up
automatically.
"""
from db_portability.checks import postgres_oracle

REGISTRY = {
    (postgres_oracle.SOURCE, postgres_oracle.TARGET): postgres_oracle,
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
