from decimal import Decimal

from coding_agent_performance.trace.cost import usd_to_micros


def test_decimal_usd_converts_to_micros() -> None:
    assert usd_to_micros("0.012345") == 12345
    assert usd_to_micros(0.000012) == 12


def test_integer_micros_from_whole_dollars() -> None:
    assert usd_to_micros(2) == 2_000_000
    assert usd_to_micros(Decimal("1")) == 1_000_000


def test_non_finite_values_are_zero() -> None:
    assert usd_to_micros(float("nan")) == 0
    assert usd_to_micros(float("inf")) == 0
    assert usd_to_micros(float("-inf")) == 0
    assert usd_to_micros("NaN") == 0
    assert usd_to_micros("Infinity") == 0


def test_extreme_exponent_is_zero() -> None:
    assert usd_to_micros("1e999999") == 0


def test_invalid_types_are_zero() -> None:
    assert usd_to_micros(True) == 0
    assert usd_to_micros(False) == 0
    assert usd_to_micros(None) == 0
    assert usd_to_micros(["0.1"]) == 0
    assert usd_to_micros({"usd": "0.1"}) == 0


def test_unparseable_value_is_zero() -> None:
    assert usd_to_micros("1e999999-hidden-cost") == 0
