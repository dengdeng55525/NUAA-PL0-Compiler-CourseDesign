"""Repro: run the example program with inputs [5,3] and inspect output.

Expected output should be [15, 7, 9] for the user's program:
- else branch prints 5*3=15
- loop increments x from 5 to 10 and prints odd x: 7, 9

If output is [], something is wrong with input parsing or runtime wiring.
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


def run_with(inputs: list[int]) -> list[int]:
    toks, lex_errs = tokenize_with_errors(SRC)
    assert not lex_errs
    prog, parse_errs = parse_tokens_with_errors(toks, SRC, auto_recover=False)
    assert not parse_errs
    from semantic import analyze
    sem_errs = analyze(prog, source=SRC, fold_consts=True)
    assert not sem_errs
    code = CodeGenerator().generate(prog)
    return VM(code, inputs=inputs).run()


def main() -> None:
    print("out(3,5)=", run_with([3, 5]))
    print("out(5,3)=", run_with([5, 3]))
    print("out(100,200)=", run_with([100, 200]))


if __name__ == "__main__":
    main()
