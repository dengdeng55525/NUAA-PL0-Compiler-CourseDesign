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


def find_missing_then_error(errs):
    for e in errs:
        if e.get('auto_recovered') and '缺少关键字 then' in (e.get('message') or ''):
            return e
    return None


def replace_trailing_the_with_then(text: str) -> str:
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if line.rstrip().endswith('the'):
            lines[i] = line.rstrip()[:-3] + 'then'
            break
    return '\n'.join(lines)


if __name__ == '__main__':
    before = process_source(SRC, inputs=[], auto_recover=True)
    errs_before = before.get('parser_errors') or []
    print('before errors:', len(errs_before))
    print('missing then present:', find_missing_then_error(errs_before) is not None)

    fixed = replace_trailing_the_with_then(SRC)
    after = process_source(fixed, inputs=[], auto_recover=True)
    errs_after = after.get('parser_errors') or []

    print('after errors:', len(errs_after))
    print('missing then present:', find_missing_then_error(errs_after) is not None)
    for i, e in enumerate(errs_after[:10], 1):
        print(i, e.get('message'))
