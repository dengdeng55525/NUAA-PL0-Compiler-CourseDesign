import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from main_cli import compile_and_run


def test_const_used_in_expression():
    src = """program p;
const a := 7;
var x;
begin
  x := a + 1;
  write(x)
end"""
    out = compile_and_run(src)
    assert out == [8]
