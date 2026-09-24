"""
Inline suppression comments for dbp-scan findings.

    x = array_field.contains(y)  # dbp-scan: ignore[DBP001] vendor-branched, see below

A suppression comment must sit on the same physical line as the finding it
silences (the same convention flake8's `# noqa` uses) and must name the
code(s) it silences plus a reason:

    # dbp-scan: ignore[DBP001] reason text
    # dbp-scan: ignore[DBP001,DBP003] reason text

A comment matching the marker with an empty reason is treated as invalid:
the finding is NOT suppressed, so the missing reason gets noticed instead of
silently doing nothing. This is a plain per-line regex (like `# noqa`), not a
tokenizer, so a `#`-comment-shaped string literal could in principle false
match -- an accepted tradeoff for keeping this dependency-free.
"""
import re

_PATTERN = re.compile(
    r"#\s*dbp-scan:\s*ignore\[\s*([A-Za-z0-9_,\s]+?)\s*\]\s*(.*?)\s*$"
)


class Suppression:
    __slots__ = ("codes", "reason")

    def __init__(self, codes, reason):
        self.codes = codes
        self.reason = reason


def parse_suppressions(source):
    """Return {lineno: Suppression} for '# dbp-scan: ignore[...]' comments in source."""
    suppressions = {}
    for lineno, line in enumerate(source.splitlines(), 1):
        match = _PATTERN.search(line)
        if not match:
            continue
        codes = frozenset(
            code.strip().upper() for code in match.group(1).split(",") if code.strip()
        )
        if not codes:
            continue
        suppressions[lineno] = Suppression(codes, match.group(2).strip())
    return suppressions


def parse_suppressions_from_file(path):
    with open(path, "r", encoding="utf-8", errors="replace") as fh:
        return parse_suppressions(fh.read())
