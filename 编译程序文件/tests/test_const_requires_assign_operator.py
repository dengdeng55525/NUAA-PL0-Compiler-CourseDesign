import sys, os

ROOT = os.path.dirname(os.path.dirname(__file__))
sys.path.insert(0, ROOT)

from web.app import process_source


def test_const_decl_rejects_eq_operator():
    src = """program p;
const
  a = 1;
var x;
begin
  x := a;
  write(x)
end"""

    r = process_source(src, inputs=[], compile_mode='classic', auto_recover=False)
    # Should report parser error and not run.
    assert r.get('parser_errors'), "expected parser error for const using '='"
    assert r.get('code') is None
    assert r.get('output') is None
