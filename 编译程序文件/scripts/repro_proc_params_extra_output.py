"""Repro: procedure with params produces extra output.

This script prints parser errors, code, and runtime output.
Run with project root as cwd.
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
from vm import VM

PARSER_PATH = os.path.join(ROOT, "parser.py")
_spec = importlib.util.spec_from_file_location("user_parser", PARSER_PATH)
_user_parser = importlib.util.module_from_spec(_spec)
assert _spec and _spec.loader
_spec.loader.exec_module(_user_parser)
parse_tokens_with_errors = getattr(_user_parser, "parse_tokens_with_errors")

SRC = """program p;
procedure add(a,b);
var t;
begin
  t := a + b;
  write(t)
end;
begin
  begin
    call add(3, 5);
    call add(10, 20)
  end
end
"""


def main() -> None:
    toks, lex_errs = tokenize_with_errors(SRC)
    print("lex_errs:", [e.to_dict(SRC) for e in lex_errs])
    prog, parse_errs = parse_tokens_with_errors(toks, SRC, auto_recover=False)
    print("parse_errs:", parse_errs)

    from semantic import analyze
    sem_errs = analyze(prog, source=SRC, fold_consts=True)
    print("sem_errs:", sem_errs)

    code = CodeGenerator().generate(prog)
    for i, ins in enumerate(code):
        print(f"{i:04d}: {ins}")

    out = VM(code, []).run()
    print("VM output:", out)


if __name__ == "__main__":
    main()
