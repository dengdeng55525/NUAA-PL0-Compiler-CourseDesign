import sys, os

ROOT = os.path.dirname(os.path.dirname(__file__))
sys.path.insert(0, ROOT)

from web.app import process_source

SRC = """program p;
var x;
begin
  if x > 0 the
    write(x)
end"""


def _find_missing_then_error(errs):
    for e in errs:
        if e.get('auto_recovered') and '缺少关键字 then' in (e.get('message') or ''):
            return e
    return None


def _replace_trailing_the_with_then(text: str) -> str:
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if line.rstrip().endswith('the'):
            lines[i] = line.rstrip()[:-3] + 'then'
            break
    return '\n'.join(lines)


def test_the_typo_fix_removes_missing_then_error():
    before = process_source(SRC, inputs=[], auto_recover=True)
    errs_before = before.get('parser_errors') or []
    assert _find_missing_then_error(errs_before) is not None

    fixed = _replace_trailing_the_with_then(SRC)
    after = process_source(fixed, inputs=[], auto_recover=True)
    errs_after = after.get('parser_errors') or []

    assert _find_missing_then_error(errs_after) is None
