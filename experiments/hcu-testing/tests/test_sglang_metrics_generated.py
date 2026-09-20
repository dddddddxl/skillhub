"""CPU behavior tests for SGLang metrics buckets; no device claims.

Oracles are explicit arithmetic examples, not calls to another bucket helper.
The zero-length sequence is treated as empty; invalid inputs tested here are
those rejected explicitly or by the documented numeric conversion operations.
Negative lengths, NaN/inf, and public API guarantees for such inputs are not
specified by these tests.
"""
import pytest

from sglang.srt.observability.utils import (
    exponential_buckets,
    generate_buckets,
    two_sides_exponential_buckets,
)


@pytest.mark.parametrize('rule', [None, [], ['default']])
def test_default_normalizes_without_mutating_input(rule):
    original = [4.0, 1.0, 4.0, 2.0]
    assert generate_buckets(rule, original) == [1.0, 2.0, 4.0]
    assert original == [4.0, 1.0, 4.0, 2.0]


def test_custom_converts_sorts_deduplicates_without_mutation():
    rule = ['custom', '2', '0.5', '2.0', '1']
    result = generate_buckets(rule, [])
    assert result == [0.5, 1.0, 2.0]
    assert all(isinstance(x, float) for x in result)
    assert rule == ['custom', '2', '0.5', '2.0', '1']


def test_custom_empty():
    assert generate_buckets(['custom'], [1.0]) == []


@pytest.mark.parametrize('base', ['1', '0', '-2'])
def test_tse_rejects_nonexpanding_base(base):
    with pytest.raises(AssertionError, match='Base must be greater'):
        generate_buckets(['tse', '10', base, '4'], [])


def test_unknown_rule_rejected():
    with pytest.raises(AssertionError):
        generate_buckets(['unknown'], [])


@pytest.mark.parametrize('rule', [
    ['tse', '10', '2'], ['tse', '10', '2', '4', 'extra'],
    ['custom', 'not-a-number'], ['tse', '10', '2', '1.5'],
])
def test_malformed_rule_rejected(rule):
    with pytest.raises(ValueError):
        generate_buckets(rule, [])


def test_tse_dispatch_has_independent_expected_values():
    # Center 5 with distances 3 and 9, clamped at zero and sorted.
    assert generate_buckets(['tse', '5', '3', '4'], []) == [0, 2, 5, 8, 14]


def test_tse_zero_count_is_center_only():
    assert two_sides_exponential_buckets(5.0, 2.0, 0) == [5.0]


@pytest.mark.parametrize('start,width,length,expected', [
    (0.25, 2.0, 4, [0.25, 0.5, 1.0, 2.0]),
    (0.05, 1.5, 4, [0.05, 0.075, 0.1125, 0.16875]),
    (2.0, 3.0, 1, [2.0]),
    (2.0, 3.0, 0, []),
])
def test_exponential_sequence(start, width, length, expected):
    # Ordinary CPU double arithmetic: allow rounding, not algorithm changes.
    assert exponential_buckets(start, width, length) == pytest.approx(expected, rel=1e-12, abs=1e-15)
