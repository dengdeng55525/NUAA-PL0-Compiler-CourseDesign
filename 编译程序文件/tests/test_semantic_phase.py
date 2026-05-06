import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from main_cli import compile_and_run


def test_semantic_proc_used_as_expression_rejected():
    src = """program p;
var x;
procedure f;
begin
end;
begin
  x := f;
  write(x)
end"""

    try:
        compile_and_run(src)
        assert False, 'expected semantic error'
    except RuntimeError as e:
        assert '过程' in str(e) or 'proc' in str(e)
