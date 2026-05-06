from __future__ import annotations


def parse_inputs(inputs_raw: str):
    raw = (inputs_raw or '').strip()
    if not raw:
        return []
    out = []
    for s in raw.split(','):
        s = s.strip()
        if not s:
            continue
        try:
            n = int(s)
        except Exception:
            continue
        out.append(n)
    return out


def test_parse_inputs_basic():
    assert parse_inputs('3,5') == [3, 5]


def test_parse_inputs_with_spaces_and_trailing_comma():
    assert parse_inputs(' 3 , 5 , ') == [3, 5]


def test_parse_inputs_ignores_invalid():
    assert parse_inputs('3,a,5') == [3, 5]


def test_parse_inputs_negative():
    assert parse_inputs('-1,2') == [-1, 2]

