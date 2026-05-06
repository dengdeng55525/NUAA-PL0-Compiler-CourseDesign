"""Repro: optimizer may break program behavior when it removes/rewrites code *before* procedures.

The compiler's codegen layout is:
- main body
- JMP over procs
- procedure bodies
- final OPR 0 0

If peephole removes the JMP-over-procs as "JMP to next" after earlier removals,
main will fall through into procedure bodies and exit early, changing outputs.

This script compiles a small program with a procedure, runs with optimizer on/off,
and compares output.
"""

from __future__ import annotations

import importlib.util
import os
import sys

ROOT = os.path.dirname(os.path.dirname(__file__))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from lexer import tokenize_with_errors
from codegen import CodeGenerator
from optimizer import peephole
from vm import VM

PARSER_PATH = os.path.join(ROOT, "parser.py")
_spec = importlib.util.spec_from_file_location("user_parser", PARSER_PATH)
_user_parser = importlib.util.module_from_spec(_spec)
assert _spec and _spec.loader
_spec.loader.exec_module(_user_parser)
parse_tokens_with_errors = getattr(_user_parser, "parse_tokens_with_errors")

SRC = """program p;
var x,y;
procedure mul(a,b);
var r;
begin
  r := a*b;
  write(r)
end;
begin
  read(x,y);
  call mul(x,y);
  write(x)
end
"""


def compile_code(opt: bool):
    toks, lex_errs = tokenize_with_errors(SRC)
    assert not lex_errs
    prog, parse_errs = parse_tokens_with_errors(toks, SRC, auto_recover=False)
    assert not parse_errs
    from semantic import analyze
    sem_errs = analyze(prog, source=SRC, fold_consts=True)
    assert not sem_errs
    code = CodeGenerator().generate(prog)
    if opt:
        code = peephole(code)
    return code


def main() -> None:
    code0 = compile_code(opt=False)
    out0 = VM(code0, inputs=[5, 3]).run()
    print("no opt out:", out0)

    code1 = compile_code(opt=True)
    out1 = VM(code1, inputs=[5, 3]).run()
    print("opt out:", out1)

    if out0 != out1:
        print("DIFF!\nno-opt len=", len(code0), "opt len=", len(code1))


if __name__ == "__main__":
    main()
