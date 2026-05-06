from __future__ import annotations

import os
import sys
import importlib.util

# Ensure project root is on sys.path (pytest may run with cwd different from project root)
ROOT = os.path.dirname(os.path.dirname(__file__))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import pytest

from lexer import tokenize_with_errors

# Explicitly load local parser.py to avoid clashing with stdlib 'parser'
PARSER_PATH = os.path.join(ROOT, 'parser.py')
_spec = importlib.util.spec_from_file_location('user_parser', PARSER_PATH)
_user_parser = importlib.util.module_from_spec(_spec)
assert _spec and _spec.loader
_spec.loader.exec_module(_user_parser)
parse_tokens_with_errors = getattr(_user_parser, 'parse_tokens_with_errors')

from codegen import CodeGenerator
from vm import VM


def compile_ok(src: str, *, strict_bnf: bool = True):
    toks, lex_errs = tokenize_with_errors(src)
    assert lex_errs == []
    prog, parse_errs = parse_tokens_with_errors(toks, src, auto_recover=False, strict_bnf=strict_bnf)
    assert parse_errs == []
    assert prog is not None
    from semantic import analyze
    sem_errs = analyze(prog, source=src, fold_consts=True)
    assert sem_errs == []
    code = CodeGenerator().generate(prog)
    return code



def run_ok(src: str, inputs=None, *, strict_bnf: bool = True):
    code = compile_ok(src, strict_bnf=strict_bnf)
    vm = VM(code, inputs or [])
    return vm.run()


BNF_VALID_PROGRAMS = [
    (
        "minimal_body",
        """program p;
begin
end
""",
        [],
    ),
    (
        "const_single",
        """program p;
const a := 7;
var x;
begin
  x := a;
  write(x)
end
""",
        [7],
    ),
    (
        "const_list_commas",
        """program p;
const a := 1, b := 2, c := 3;
var x;
begin
  x := a + b * c;
  write(x)
end
""",
        [7],
    ),
    (
        "var_list",
        """program p;
var x, y, z;
begin
  x := 1;
  y := 2;
  z := x + y;
  write(z)
end
""",
        [3],
    ),
    (
        "proc_no_params",
        """program p;
var x;
procedure inc();
begin
  x := x + 1
end;
begin
  x := 0;
  call inc();
  call inc();
  write(x)
end
""",
        [2],
    ),
    (
        "proc_with_params",
        """program p;
procedure add(a,b);
var t;
begin
  t := a + b;
  write(t)
end;
begin
  call add(1,2)
end
""",
        [3],
    ),
    (
        "if_then_else_relop",
        """program p;
var x;
begin
  x := 3;
  if x > 0 then
    write(1)
  else
    write(0)
end
""",
        [1],
    ),
    (
        "while_do",
        """program p;
var x;
begin
  x := 0;
  while x < 3 do
  begin
    write(x);
    x := x + 1
  end
end
""",
        [0, 1, 2],
    ),
    (
        "write_multi_exprs",
        """program p;
var x;
begin
  x := 2;
  write(x, x+1, (x+2)*3)
end
""",
        [2, 3, 12],
    ),
    (
        "odd_condition",
        """program p;
var x;
begin
  x := 3;
  if odd x then
    write(1)
  else
    write(0)
end
""",
        [1],
    ),
    (
        "unary_sign",
        """program p;
var x;
begin
  x := -(1) + 2;
  write(x)
end
""",
        [1],
    ),
]

BNF_VALID_PROGRAMS_WITH_INPUTS = [
    (
        "read_statement",
        """program p;
var x, y;
begin
  read(x, y);
  write(x);
  write(y)
end
""",
        [11, 22],
        [11, 22],
    ),
]


@pytest.mark.parametrize('name,src,expected', BNF_VALID_PROGRAMS)
def test_bnf_programs_run(name: str, src: str, expected: list[int]):
    out = run_ok(src, inputs=[], strict_bnf=True)
    assert out == expected


@pytest.mark.parametrize('name,src,expected_output,inputs', BNF_VALID_PROGRAMS_WITH_INPUTS)
def test_bnf_programs_run_with_inputs(name: str, src: str, expected_output: list[int], inputs: list[int]):
    out = run_ok(src, inputs=inputs, strict_bnf=True)
    assert out == expected_output


# 兼容旧测试名（防止外部引用）；实际逻辑转到参数化版本
def test_bnf_program_read_statement():
    name, src, expected_output, inputs = BNF_VALID_PROGRAMS_WITH_INPUTS[0]
    out = run_ok(src, inputs=inputs, strict_bnf=True)
    assert out == expected_output
