"""\
回归测试：三层嵌套（global -> outer -> inner）

目标：
- 确保过程入口绑定正确（call outer 不会跳进 inner）
- 确保静态链 L 计算正确：inner 能同时访问 outer 的局部变量 x 和全局变量 g

预期输出：
- inner 每次 write(x); write(g)
- main 最后 write(g)

输出应为：[1, 10, 2, 20, 20]
"""

import importlib.util
import os

from lexer import tokenize_with_errors
from semantic import analyze
from codegen import CodeGenerator
from vm import VM


def _load_local_parser():
    root = os.path.dirname(os.path.dirname(__file__))
    parser_path = os.path.join(root, 'parser.py')
    spec = importlib.util.spec_from_file_location('user_parser', parser_path)
    mod = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(mod)
    return mod


def test_three_level_nested_scope_access_and_entry_binding():
    src = """program nested2;
var g;

procedure outer;
var x;

procedure inner;
begin
    x := x + 1;
    g := g + 10;
    write(x);
    write(g)
end;

begin
    x := 0;
    call inner;
    call inner
end;

begin
    g := 0;
    call outer;
    write(g)
end
"""

    toks, lex_errs = tokenize_with_errors(src)
    assert not lex_errs

    parser = _load_local_parser()
    prog, perrs = parser.parse_tokens_with_errors(toks, src, auto_recover=False)
    assert prog is not None
    assert perrs == []

    serrs = analyze(prog, source=src, fold_consts=True)
    assert serrs == []

    code = CodeGenerator().generate(prog)
    out = VM(code, inputs=[]).run()

    assert out == [1, 10, 2, 20, 20]
