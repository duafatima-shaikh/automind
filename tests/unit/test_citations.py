from automind.generation.citations import extract_citations, strip_invalid, validate

SOURCES = ["The monthly pass costs 18 dollars.", "Bicycles are available until midnight."]


def test_extract_handles_groups():
    assert extract_citations("A [1] and B [1, 2][3].") == [1, 1, 2, 3]


def test_strip_invalid_removes_only_bad_numbers():
    assert strip_invalid("Fact [1][7]. Other [2, 9].", 2) == "Fact [1]. Other [2]."


def test_validate_reports_support():
    report = validate("The monthly pass costs 18 dollars [1].", SOURCES)
    assert report.ok and report.grounding_score == 1.0


def test_validate_flags_invalid_and_unsupported():
    report = validate("The pass is free for everyone [2]. Also true [5].", SOURCES)
    assert report.invalid == [5]
    assert report.grounding_score == 0.0


def test_trailing_citation_after_period_counts():
    report = validate("The monthly pass costs 18 dollars. [1]", SOURCES)
    assert report.grounding_score == 1.0
