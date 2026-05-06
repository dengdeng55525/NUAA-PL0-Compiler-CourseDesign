import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from lexer import tokenize

# Explicitly load local parser.py to avoid clashing with stdlib 'parser'
import importlib.util
_parser_path = os.path.join(os.path.dirname(__file__), '..', 'parser.py')
_spec = importlib.util.spec_from_file_location('user_parser', _parser_path)
_mod = importlib.util.module_from_spec(_spec)
assert _spec and _spec.loader
_spec.loader.exec_module(_mod)
parse_tokens_with_errors = getattr(_mod, 'parse_tokens_with_errors')


def test_call_with_wrong_arity_reports_error():
    src = """program p;
var x;
procedure add(a,b);
begin
  write(a+b)
end;
begin
  x := 1;
  call add(x)
end"""
    toks = tokenize(src)
    prog, errs = parse_tokens_with_errors(toks, source=src, auto_recover=False)
    assert any('期望 2 个参数' in (e.get('message') or '') for e in errs)
