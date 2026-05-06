import json
import sys, os

# make project root importable
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


def find_missing_then_error(errs):
    for e in errs:
        if e.get('auto_recovered') and '缺少关键字 then' in (e.get('message') or ''):
            return e
    return None


def apply_frontend_like_fix_insert_then(src: str, err: dict) -> str:
    # Mirror the current frontend strategy: insert 'then\n' before err.line/err.col
    lines = src.split('\n')
    line = max(1, min(int(err.get('line') or 1), len(lines)))
    col = max(1, int(err.get('col') or 1))

    # absolute pos
    pos = 0
    for i in range(line-1):
        pos += len(lines[i]) + 1
    pos += col - 1
    return src[:pos] + 'then\n' + src[pos:]


if __name__ == '__main__':
    before = process_source(SRC, inputs=[], auto_recover=True)
    errs_before = before.get('parser_errors') or []
    e_then = find_missing_then_error(errs_before)

    print('errors_before:', len(errs_before))
    if e_then:
        print('missing_then at', e_then.get('line'), e_then.get('col'))
    else:
        print('no missing then error found')
        sys.exit(0)

    fixed_src = apply_frontend_like_fix_insert_then(SRC, e_then)
    after = process_source(fixed_src, inputs=[], auto_recover=True)
    errs_after = after.get('parser_errors') or []

    print('errors_after:', len(errs_after))
    # dump first few messages for inspection
    for i, e in enumerate(errs_after[:10], 1):
        print(i, e.get('message'))

    # Fail if errors blow up (regression detection)
    if len(errs_after) > len(errs_before) + 1:
        raise SystemExit('REGRESSION: errors increased too much after then-fix')

    print('OK')
