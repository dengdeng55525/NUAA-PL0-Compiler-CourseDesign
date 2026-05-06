import sys, os

ROOT = os.path.dirname(os.path.dirname(__file__))
sys.path.insert(0, ROOT)

from web.app import process_source

SRC_THE = """program p;
var x;
begin
  if x > 0 the
    write(x)
end"""


def _find_missing_then(errs):
    for e in errs:
        if e.get('auto_recovered') and '缺少关键字 then' in (e.get('message') or ''):
            return e
    return None


def _replace_trailing_word(text: str, line_no: int, old: str, new: str) -> str:
    lines = text.split('\n')
    idx = line_no - 1
    assert 0 <= idx < len(lines)
    import re
    lines[idx] = re.sub(rf"\b{old}\b\s*$", new, lines[idx])
    return '\n'.join(lines)


def test_the_typo_can_be_fixed_by_replacing_trailing_the():
    before = process_source(SRC_THE, inputs=[], auto_recover=True)
    errs_before = before.get('parser_errors') or []
    e = _find_missing_then(errs_before)
    assert e is not None

    fixed = _replace_trailing_word(SRC_THE, 4, 'the', 'then')
    after = process_source(fixed, inputs=[], auto_recover=True)
    errs_after = after.get('parser_errors') or []

    assert _find_missing_then(errs_after) is None

