"""验证脚本：编译器全流程（Lexer->Parser->Semantic->CodeGen->Optimizer->VM）。

按你的要求：
- 我以后想写脚本验证时，会把脚本写到 scripts/ 目录里再运行。
- 这个脚本用于快速 smoke test：给一段源码和输入，分别在“开/关优化器”下运行，
  打印 IR 长度变化与最终输出，并断言输出一致（优化器不应改变语义）。

用法：
    python scripts/verify_full_compile_pipeline.py

输出示例：
    IR len: 42 -> 41
    out(no-opt)=[...]
    out(opt)   =[...]
    ALL OK
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Tuple

# 确保可以从 scripts/ 目录正确导入项目根目录的模块
import os
import sys

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from lexer import tokenize

# 显式加载本地 parser.py（避免与 Python stdlib parser 冲突）
import importlib.util

_parser_path = os.path.join(PROJECT_ROOT, "parser.py")
_spec = importlib.util.spec_from_file_location("user_parser", _parser_path)
_mod = importlib.util.module_from_spec(_spec)
assert _spec and _spec.loader
_spec.loader.exec_module(_mod)
parse_tokens = getattr(_mod, "parse_tokens")

from semantic import analyze
from codegen import CodeGenerator
from optimizer import peephole
from vm import VM


@dataclass
class Case:
    name: str
    source: str
    inputs: List[int]


def compile_ir(source: str, *, optimize: bool) -> List[Tuple[str, int, int]]:
    tokens = tokenize(source)
    program = parse_tokens(tokens)

    sem_errs = analyze(program, source=source, fold_consts=True)
    if sem_errs:
        raise RuntimeError(f"Semantic errors: {sem_errs}")

    cg = CodeGenerator()
    ir = cg.generate(program)
    if optimize:
        ir = peephole(ir)
    return ir


def run_case(case: Case) -> None:
    print(f"\n=== {case.name} ===")

    ir0 = compile_ir(case.source, optimize=False)
    out0 = VM(ir0, case.inputs).run()

    ir1 = compile_ir(case.source, optimize=True)
    out1 = VM(ir1, case.inputs).run()

    print(f"IR len: {len(ir0)} -> {len(ir1)}")
    print(f"out(no-opt)={out0}")
    print(f"out(opt)   ={out1}")

    if out0 != out1:
        raise AssertionError("Optimizer changed program output!")


def main() -> None:
    cases = [
        Case(
            name="sum_if_odd_and_proc_call",
            source=(
                "program example;\n"
                "const\n"
                "    max := 100,\n"
                "    pi := 314;\n"
                "var\n"
                "    x, y, sum;\n"
                "\n"
                "procedure multiply(a, b);\n"
                "var result;\n"
                "begin\n"
                "    result := a * b;\n"
                "    write(result)\n"
                "end;\n"
                "\n"
                "begin\n"
                "    read(x, y);\n"
                "    sum := x + y;\n"
                "    if sum > max then\n"
                "        write(sum)\n"
                "    else\n"
                "        call multiply(x, y);\n"
                "    while x < 10 do\n"
                "    begin\n"
                "        x := x + 1;\n"
                "        if odd x then\n"
                "            write(x)\n"
                "    end\n"
                "end\n"
            ),
            inputs=[5, 3],
        )
    ]

    for c in cases:
        run_case(c)

    print("\nALL OK")


if __name__ == "__main__":
    main()

