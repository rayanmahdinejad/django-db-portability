from django.db.models import Q

from db_portability.managers import empty_or_null_q


def test_empty_or_null_q_builds_expected_conditions():
    q = empty_or_null_q("code")
    expected = Q(code__isnull=True) | Q(code="")
    assert q == expected
