"""Repro: check how web frontend parses inputs like '5,3' vs '5, 3'.

The user reports:
- input "5,3" => no output
- input "100,200" => output 300

Backend VM/codegen is fine (see scripts/repro_example_inputs_5_3.py).
So this script mimics the current frontend parsing rules to see when numbers are dropped.

Run it to inspect parsed arrays.
"""

from __future__ import annotations


def parse_like_frontend(inputs_raw: str) -> list[int]:
    s = inputs_raw.strip()
    if not s:
        return []
    out: list[int] = []
    for part in s.split(','):
        part = part.strip()
        if not part:
            continue
        try:
            n = int(part)
        except Exception:
            # matches Number.isFinite && Number.isInteger filter dropping invalid
            continue
        out.append(n)
    return out


def main() -> None:
    cases = [
        "5,3",
        "5, 3",
        "100,200",
        "100, 200",
        "5，3",  # Chinese comma
        "5， 3",
        "  5 ,3 ",
        "5,3,",
    ]
    for c in cases:
        print(repr(c), "=>", parse_like_frontend(c))


if __name__ == "__main__":
    main()

