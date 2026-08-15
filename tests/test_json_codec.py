import pytest

from coding_agent_performance.trace.json_codec import InvalidJsonError, loads_json


@pytest.mark.parametrize("token", ["NaN", "Infinity", "-Infinity"])
def test_rejects_non_finite_constants(token: str) -> None:
    with pytest.raises(InvalidJsonError) as exc_info:
        loads_json(f'{{"n": {token}}}')
    assert token not in str(exc_info.value)
    assert token not in repr(exc_info.value)


def test_rejects_overflow_float() -> None:
    with pytest.raises(InvalidJsonError) as exc_info:
        loads_json('{"n": 1e999}')
    assert "1e999" not in str(exc_info.value)


def test_rejects_invalid_syntax_without_document() -> None:
    secret = "developer@example.invalid"
    with pytest.raises(InvalidJsonError) as exc_info:
        loads_json('{"prompt": "' + secret)
    assert secret not in str(exc_info.value)
    assert secret not in repr(exc_info.value)
    assert "prompt" not in str(exc_info.value)


def test_recursion_error_is_invalid_json(monkeypatch: pytest.MonkeyPatch) -> None:
    def boom(_text: str, **_kwargs: object) -> object:
        raise RecursionError

    monkeypatch.setattr("coding_agent_performance.trace.json_codec.json.loads", boom)
    with pytest.raises(InvalidJsonError) as exc_info:
        loads_json("{}")
    assert "{}" not in str(exc_info.value)


def test_tree_recursion_error_is_invalid_json(monkeypatch: pytest.MonkeyPatch) -> None:
    def boom(_value: object) -> None:
        raise RecursionError

    monkeypatch.setattr("coding_agent_performance.trace.json_codec._reject_non_finite_tree", boom)
    with pytest.raises(InvalidJsonError):
        loads_json("{}")


def test_parses_finite_object() -> None:
    assert loads_json('{"n": 1.5, "ok": true}') == {"n": 1.5, "ok": True}
