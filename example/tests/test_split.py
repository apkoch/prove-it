from fractions import Fraction

import pytest
from hypothesis import given
from hypothesis import strategies as st

from splitter import split

totals = st.integers(min_value=0, max_value=10**9)
weights = st.lists(st.integers(min_value=1, max_value=1000), min_size=1, max_size=40)


@pytest.mark.req("REQ-SPL-01")
@given(totals, weights)
def test_shares_sum_to_total(total, ws):
    assert sum(split(total, ws)) == total


@pytest.mark.req("REQ-SPL-02")
@given(totals, weights)
def test_each_share_within_a_cent_of_exact(total, ws):
    for share, w in zip(split(total, ws), ws, strict=True):
        assert abs(share - Fraction(total * w, sum(ws))) < 1


@pytest.mark.req("REQ-SPL-03")
def test_leftover_cents_go_to_largest_remainders_then_earliest():
    # $1.00 three ways: 33⅓ each, so one cent is left over and the first payer gets it.
    assert split(100, [1, 1, 1]) == [34, 33, 33]
    # 1001 cents by 1:2:1 → 250.25, 500.5, 250.25: the middle remainder is largest.
    assert split(1001, [1, 2, 1]) == [250, 501, 250]


@pytest.mark.req("REQ-SPL-01")
def test_rejects_non_positive_weights():
    with pytest.raises(ValueError):
        split(100, [1, 0])
