"""\
运行 examples/param_passing_demo.pl0 的脚本，方便验证“参数传递”是否正确。

用法：
  python scripts\run_param_passing_demo.py 3 5

预期输出（输入 x=3,y=5）：
- add(x,y)            -> 8
- add(x+1,y+2)        -> 11
- swap_print(x,y)     -> 5, 3

因此输出列表应为：[8, 11, 5, 3]
"""

from __future__ import annotations

import os
import sys
import importlib.util

ROOT = os.path.dirname(os.path.dirname(__file__))
sys.path.insert(0, ROOT)

from lexer import tokenize_with_errors
from semantic import analyze
from codegen import CodeGenerator
from vm import VM


def load_parser():
    spec = importlib.util.spec_from_file_location('user_parser', os.path.join(ROOT, 'parser.py'))
    mod = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(mod)
    return mod


def main():
    x = int(sys.argv[1]) if len(sys.argv) > 1 else 3
    y = int(sys.argv[2]) if len(sys.argv) > 2 else 5

    src_path = os.path.join(ROOT, 'examples', 'param_passing_demo.pl0')
    src = open(src_path, encoding='utf-8').read()

    toks, lex_errs = tokenize_with_errors(src)
    if lex_errs:
        # 当前 lexer（按 BNF: id -> l{l|d}）不接受 '_'，但很多同学会自然写成 swap_print。
        # 为了让你能快速演示“参数传递”，这里提供一个兼容处理：
        # - 提示原因
        # - 在 runner 内存里把 swap_print 临时替换为 swapp 再编译运行
        msg = '\n'.join(str(e) for e in lex_errs)
        if any("'_'" in str(e) for e in lex_errs) and 'swap_print' in src:
            print('NOTE: lexer 不支持标识符中的下划线 _（符合 BNF: <id> → l{l|d}）。')
            print('      为了演示参数传递，runner 将临时把 swap_print 替换为 swapp 再编译运行。')
            src = src.replace('swap_print', 'swapp')
            toks, lex_errs = tokenize_with_errors(src)
        if lex_errs:
            raise AssertionError(lex_errs)

    parser = load_parser()
    prog, perrs = parser.parse_tokens_with_errors(toks, src, auto_recover=False)
    assert prog is not None and perrs == [], perrs

    serrs = analyze(prog, source=src, fold_consts=True)
    assert serrs == [], serrs

    code = CodeGenerator().generate(prog)
    vm = VM(code, inputs=[x, y])
    out = vm.run()

    print('input:', [x, y])
    print('output_list:', out)
    print('expected   :', [x + y, (x + 1) + (y + 2), y, x])


if __name__ == '__main__':
    main()

