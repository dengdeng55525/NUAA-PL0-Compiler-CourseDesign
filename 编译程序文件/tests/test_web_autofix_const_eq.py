import sys, os

ROOT = os.path.dirname(os.path.dirname(__file__))
sys.path.insert(0, ROOT)

from web.app import process_source


def test_web_backend_emits_autorecoverable_const_eq_diagnostic():
    src = """program p;
const
  a = 1;
var x;
begin
  x := a;
  write(x)
end"""

    res = process_source(src, inputs=[], compile_mode='classic', auto_recover=True)
    errs = res.get('parser_errors') or []
    assert errs
    e0 = errs[0]
    assert e0.get('auto_recovered') is True
    assert e0.get('code') == 'PAR_CONST_REQUIRES_ASSIGN'
    assert e0.get('token_value') == '='
    assert e0.get('line') == 3
