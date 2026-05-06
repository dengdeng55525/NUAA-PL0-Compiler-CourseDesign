"""Inspect optimizer effect around the main JMP-over-procs barrier.

It prints the unoptimized and optimized IR with indices so we can see which
instruction got removed and why the program falls through into procedure code.
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


def dump(label, code):
    print("\n==", label, "len=", len(code))
    for i, ins in enumerate(code):
        print(f"{i:04d} {ins}")


def main() -> None:
    code0 = compile_code(opt=False)
    code1 = compile_code(opt=True)
    dump("NO-OPT", code0)
    dump("OPT", code1)


if __name__ == "__main__":
    main()

