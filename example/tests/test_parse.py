import pytest

from splitter import parse_cents


@pytest.mark.req("REQ-SPL-04")
@pytest.mark.parametrize(
    ("text", "cents"), [("12.34", 1234), ("0.1", 10), (" 7 ", 700), ("0.29", 29)]
)
def test_parses_to_exact_cents(text, cents):
    assert parse_cents(text) == cents


@pytest.mark.req("REQ-SPL-04")
@pytest.mark.parametrize("text", ["1.234", "abc", ""])
def test_rejects_bad_amounts(text):
    with pytest.raises(ValueError):
        parse_cents(text)
