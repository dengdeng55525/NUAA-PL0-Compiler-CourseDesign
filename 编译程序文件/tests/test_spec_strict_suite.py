"""严格对照 要求.txt 的 BNF 与目标机指令集：

目的：
- 保证 parser 不会“吞掉”不合法输入
- 保证 codegen/vm 只使用要求.txt 列出的指令以及合理的 OPR 子操作
- 保证关键语法约束：
  - <prog> 末尾必须 EOF（不允许 '.'，也不允许任何多余 token）
  - const 必须用 ':='（出现 '=' 必须报错；auto_recover 可选择跳过 '=' 继续）
  - <proc> 与 call 的参数括号：按要求.txt 使用 ()，允许空 ()

说明：本套测试只做“严格性”检查，不追求覆盖所有语义。
"""

from __future__ import annotations

import os
import sys
import importlib.util

ROOT = os.path.dirname(os.path.dirname(__file__))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import pytest

from lexer import tokenize_with_errors

# load local parser.py
PARSER_PATH = os.path.join(ROOT, 'parser.py')
_spec = importlib.util.spec_from_file_location('user_parser', PARSER_PATH)
_mod = importlib.util.module_from_spec(_spec)
assert _spec and _spec.loader
_spec.loader.exec_module(_mod)
parse_tokens_with_errors = getattr(_mod, 'parse_tokens_with_errors')

from semantic import analyze
from codegen import CodeGenerator
from vm import VM


ALLOWED_OPS = {
    'LIT', 'OPR', 'LOD', 'STO', 'CAL', 'INT', 'JMP', 'JPC', 'RED', 'WRT'
}

# 这份 OPR 子操作码来自仓库实现（vm.py）。这里不与要求.txt 完全绑定，因为要求.txt
# 把 OPR 的子操作码描述得比较粗略（将“读入”等也说成 OPR=16 的例子）。
# 我们只做：OPR 的 a 必须是 int 且在合理范围内。
ALLOWED_OPR_A = set(range(0, 21))


def _compile_to_ir(src: str, *, auto_recover: bool = False):
    toks, lex_errs = tokenize_with_errors(src)
    assert lex_errs == []
    prog, perrs = parse_tokens_with_errors(toks, source=src, auto_recover=auto_recover)
    assert prog is not None
    assert perrs == []
    sem_errs = analyze(prog, source=src, fold_consts=True)
    assert sem_errs == []
    code = CodeGenerator().generate(prog)
    return code


def _assert_ir_allowed(code):
    assert code is not None
    for (op, l, a) in code:
        assert op in ALLOWED_OPS
        assert isinstance(l, int)
        assert isinstance(a, int)
        if op == 'OPR':
            assert a in ALLOWED_OPR_A


def test_prog_must_end_at_eof_rejects_trailing_tokens():
    src = """program p;
begin
end((((
"""
    toks, lex_errs = tokenize_with_errors(src)
    assert lex_errs == []
    prog, perrs = parse_tokens_with_errors(toks, source=src, auto_recover=True)
    assert prog is not None
    assert any(e.get('code') == 'PAR_TRAILING_TOKENS' for e in perrs), perrs


def test_prog_forbids_dot_everywhere():
    src = """program p;
begin
end.
"""
    toks, lex_errs = tokenize_with_errors(src)
    assert lex_errs == []
    prog, perrs = parse_tokens_with_errors(toks, source=src, auto_recover=False)
    assert prog is not None
    assert any(e.get('code') == 'PAR_DOT_FORBIDDEN' for e in perrs), perrs


def test_const_requires_assign_operator_reports_error():
    src = """program p;
const a = 1;
begin
end
"""
    toks, lex_errs = tokenize_with_errors(src)
    assert lex_errs == []
    prog, perrs = parse_tokens_with_errors(toks, source=src, auto_recover=False)
    assert prog is not None
    assert any(e.get('code') == 'PAR_CONST_REQUIRES_ASSIGN' for e in perrs), perrs


def test_const_requires_assign_operator_can_recover_when_enabled():
    src = """program p;
const a = 1;
var x;
begin
  x := a;
  write(x)
end
"""
    # auto_recover=True 时允许“跳过 = 并按 := 继续”，但必须仍然报错
    toks, lex_errs = tokenize_with_errors(src)
    assert lex_errs == []
    prog, perrs = parse_tokens_with_errors(toks, source=src, auto_recover=True)
    assert prog is not None
    assert any(e.get('code') == 'PAR_CONST_REQUIRES_ASSIGN' for e in perrs)


def test_procedure_and_call_allow_empty_parens_per_bnf():
    src = """program p;
var x;
procedure outer();
begin
  x := 1
end;
begin
  call outer();
  write(x)
end
"""
    code = _compile_to_ir(src)
    _assert_ir_allowed(code)
    out = VM(code, inputs=[]).run()
    assert out == [1]


def test_no_unlisted_ir_ops_emitted_on_typical_programs():
    programs = [
        """program p; var x; begin x := 1; write(x) end""",
        """program p; const a := 2; var x; begin x := a*3; write(x) end""",
        """program p; var x; begin x := 0; while x < 3 do begin write(x); x := x + 1 end end""",
    ]
    for src in programs:
        code = _compile_to_ir(src)
        _assert_ir_allowed(code)

