from db_portability.suppress import parse_suppressions


def test_parses_single_code_with_reason():
    source = "x = 1  # dbp-scan: ignore[DBP001] handled via vendor branch\n"
    result = parse_suppressions(source)
    assert result[1].codes == frozenset({"DBP001"})
    assert result[1].reason == "handled via vendor branch"


def test_parses_multiple_codes():
    source = "x = 1  # dbp-scan: ignore[DBP001,DBP003] reviewed\n"
    result = parse_suppressions(source)
    assert result[1].codes == frozenset({"DBP001", "DBP003"})


def test_codes_are_case_insensitive():
    source = "x = 1  # dbp-scan: ignore[dbp001] reviewed\n"
    result = parse_suppressions(source)
    assert result[1].codes == frozenset({"DBP001"})


def test_missing_reason_still_parses_with_empty_reason():
    source = "x = 1  # dbp-scan: ignore[DBP001]\n"
    result = parse_suppressions(source)
    assert result[1].codes == frozenset({"DBP001"})
    assert result[1].reason == ""


def test_line_without_marker_is_not_suppressed():
    source = "x = 1  # just a comment\n"
    assert parse_suppressions(source) == {}


def test_tracks_correct_line_numbers_across_multiple_lines():
    source = (
        "a = 1\n"
        "b = 2  # dbp-scan: ignore[DBP001] reason one\n"
        "c = 3\n"
        "d = 4  # dbp-scan: ignore[DBP002] reason two\n"
    )
    result = parse_suppressions(source)
    assert set(result.keys()) == {2, 4}
    assert result[2].reason == "reason one"
    assert result[4].reason == "reason two"
