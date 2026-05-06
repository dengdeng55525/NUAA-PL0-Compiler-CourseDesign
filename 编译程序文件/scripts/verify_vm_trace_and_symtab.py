"""\
验证新增的“符号表树导出”和“VM trace(程序栈/静态链)”不会破坏既有逻辑。

原则：
- 只做脚本级冒烟测试，不要求覆盖全部语法。
- 重点验证：
  1) include_symtab=True 时能返回 symtab dict（并包含 children 结构）
  2) include_vm_trace=True 时能返回 vm_trace.steps，并且包含 base_chain/frames 信息

运行方式（PowerShell）：
  python scripts\verify_vm_trace_and_symtab.py
"""

from __future__ import annotations

import json
import os
import sys

# allow importing web.app from repo root
ROOT = os.path.dirname(os.path.dirname(__file__))
sys.path.insert(0, ROOT)

from lexer import tokenize_with_errors

# load local parser.py (avoid stdlib)
import importlib.util

PARSER_PATH = os.path.join(ROOT, "parser.py")
_spec = importlib.util.spec_from_file_location("user_parser", PARSER_PATH)
_user_parser = importlib.util.module_from_spec(_spec)
assert _spec and _spec.loader
_spec.loader.exec_module(_user_parser)
parse_tokens_with_errors = getattr(_user_parser, "parse_tokens_with_errors")

from semantic import analyze
from codegen import CodeGenerator
from symtable import build_symtable_tree
from vm import VM


SRC = """program example;
const
  max := 100,
  pi := 314;
var x, y, sum;

procedure multiply(a,b);
var result;
begin
  result := a * b;
  write(result)
end;

begin
  read(x,y);
  sum := x + y;
  if sum > max then
    write(sum)
  else
    call multiply(x,y);
end
"""


def main():
    toks, lex_errs = tokenize_with_errors(SRC)
    assert not lex_errs, f"lexer errs: {lex_errs}"

    prog, parse_errs = parse_tokens_with_errors(toks, SRC, auto_recover=True)
    assert prog is not None, f"parse failed: {parse_errs}"
    assert not parse_errs, f"parse errs: {parse_errs}"

    sem_errs = analyze(prog, source=SRC, fold_consts=True)
    assert not sem_errs, f"semantic errs: {sem_errs}"

    # symtab
    root_st = getattr(prog.block, "symtable", None)
    st_tree = build_symtable_tree(root_st)
    assert isinstance(st_tree, dict), "symtab tree not dict"
    # should have children because there is a procedure
    assert "children" in st_tree, "symtab missing children"

    # vm trace
    code = CodeGenerator().generate(prog)
    vm = VM(code, inputs=[3, 5])
    out, trace = vm.run_with_trace()
    assert isinstance(out, list)
    assert isinstance(trace, list)
    assert len(trace) > 0, "trace empty"

    # evidence of stack/frames
    any_frame = any((step.get("frames") or {}).get("current") is not None for step in trace)
    assert any_frame, "trace has no frame header"

    # evidence of base chain on at least one memory op
    any_bc = any((step.get("frames") or {}).get("base_chain") is not None for step in trace)
    assert any_bc, "trace has no base_chain info"

    print("OK")
    print("output:", out)
    print("symtab(level):", st_tree.get("level"))
    if st_tree.get("children"):
        print("symtab children:", len(st_tree.get("children")))


if __name__ == "__main__":
    main()
