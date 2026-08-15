"""Strict JSON parsing shared by the collector and capture reader."""

import json
import math


class InvalidJsonError(ValueError):
    """JSON text is invalid or contains a non-finite number."""

    def __init__(self, reason: str = "invalid JSON") -> None:
        super().__init__(reason)


def loads_json(text: str) -> object:
    """Parse JSON without accepting NaN, Infinity, or overflowed floats."""
    try:
        parsed: object = json.loads(text, parse_constant=_reject_non_finite)
    except RecursionError, json.JSONDecodeError, ValueError:
        raise InvalidJsonError from None
    try:
        _reject_non_finite_tree(parsed)
    except RecursionError:
        raise InvalidJsonError from None
    return parsed


def _reject_non_finite(_value: str) -> object:
    raise ValueError("non-finite number")


def _reject_non_finite_tree(value: object) -> None:
    if isinstance(value, float) and not math.isfinite(value):
        raise InvalidJsonError
    if isinstance(value, dict):
        for item in value.values():
            _reject_non_finite_tree(item)
    elif isinstance(value, list):
        for item in value:
            _reject_non_finite_tree(item)
