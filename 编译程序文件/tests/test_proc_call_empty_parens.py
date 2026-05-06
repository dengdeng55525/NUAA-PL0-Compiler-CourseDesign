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


def test_procedure_and_call_allow_empty_parens():
    # 按要求.txt 的 BNF（扩充版）
    # - procedure <id>([...]); 允许空参数列表 ()
    # - call <id>([...])      允许空实参列表 ()
    src = """program p;
var x;

procedure outer();
  procedure inner();
  begin
    x := x + 1;
    write(x)
  end;
begin
  x := 10;
  call inner();
  call inner()
end;

begin
  call outer()
end
"""

    tokens = tokenize(src)
    prog, errs = parse_tokens_with_errors(tokens, source=src, auto_recover=True, strict_bnf=True)

    assert prog is not None
    assert errs == []
