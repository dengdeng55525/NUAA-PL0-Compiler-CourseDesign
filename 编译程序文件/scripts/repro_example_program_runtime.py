"""Repro: run the user's 'example' program through the same backend pipeline.

It reports tokens/errors, generated IR, and VM output for given inputs.
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

SRC = """program example;
const
    max := 100,
    pi := 314;
var
    x, y, sum;

procedure multiply(a, b);
var result;
begin
    result := a * b;
    write(result)
end;

begin
    read(x, y);
    sum := x + y;

    if sum > max then
        write(sum)
    else
        call multiply(x, y);

    while x < 10 do
    begin
        x := x + 1;
        if odd x then
            write(x)
    end
end
"""


def main() -> None:
    toks, lex_errs = tokenize_with_errors(SRC)
    print("lex_errs:", len(lex_errs))
    prog, parse_errs = parse_tokens_with_errors(toks, SRC, auto_recover=False)
    print("parse_errs:", len(parse_errs))

    from semantic import analyze
    sem_errs = analyze(prog, source=SRC, fold_consts=True)
    print("sem_errs:", len(sem_errs))

    code = CodeGenerator().generate(prog)
    print("IR length:", len(code))
    for i, ins in enumerate(code):
        print(f"{i:04d}: {ins}")

    out = VM(code, inputs=[3, 5]).run()
    print("VM output:", out)


if __name__ == "__main__":
    main()
