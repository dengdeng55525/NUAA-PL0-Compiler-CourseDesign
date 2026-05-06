import sys, os

ROOT = os.path.dirname(os.path.dirname(__file__))
sys.path.insert(0, ROOT)

from web.app import process_source

SRC = """program example;
const
    max := 100,
    pi := 314;
var
    x, y, sum;

procedure multiply(a, b);
var result;
begin
    result := a * b;
    write(result)
end;

begin
    read(x, y);
    sum := x + y;

    if sum > max 
        writewrite(sum)
    else
        call multiply(x, y);

    while x < 10 do
    begin
        x := x + 1;
        if odd x then
            write(x)
    end
end"""


def _find_missing_then_error(errs):
    for e in errs:
        if e.get('auto_recovered') and '缺少关键字 then' in (e.get('message') or ''):
            return e
    return None


def _insert_then_like_frontend(text: str, err: dict) -> str:
    # Mimic current frontend patch: insert 'then\n' at the statement start token.
    lines = text.split('\n')
    line = max(1, min(int(err.get('line') or 1), len(lines)))
    col = max(1, int(err.get('col') or 1))
    pos = 0
    for i in range(line-1):
        pos += len(lines[i]) + 1
    pos += col - 1
    return text[:pos] + 'then\n' + text[pos:]


def test_autofix_then_does_not_explode_errors():
    before = process_source(SRC, inputs=[], auto_recover=True)
    errs_before = before.get('parser_errors') or []
    e_then = _find_missing_then_error(errs_before)
    assert e_then is not None, 'expected a missing-then auto-recover error'

    fixed = _insert_then_like_frontend(SRC, e_then)
    after = process_source(fixed, inputs=[], auto_recover=True)
    errs_after = after.get('parser_errors') or []

    # It might not reduce errors (because writewrite is still wrong), but it should not cascade wildly.
    assert len(errs_after) <= len(errs_before) + 1
