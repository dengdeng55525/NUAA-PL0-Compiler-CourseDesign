import os, sys

ROOT = os.path.dirname(os.path.dirname(__file__))
sys.path.insert(0, ROOT)

from web.app import process_source


def test_missing_comma_autorecover_is_reported():
    src = """program p;
const
  a := 1
  b := 2;
var x;
begin
  x := a;
  write(x)
end"""
    res = process_source(src, inputs=[], auto_recover=True, enable_opt=False)
    errs = res.get('parser_errors') or []
    assert any(e.get('auto_recovered') and '缺少逗号' in (e.get('message') or '') for e in errs)
