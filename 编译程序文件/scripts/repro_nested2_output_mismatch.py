"""\
复现并定位：nested2.pl0 输出为何不是预期的 [1,10,2,20,20]。

运行：
  python scripts\repro_nested2_output_mismatch.py

脚本会打印：
- IR
- output_list
- 关键 trace（CAL/WRT/RET）
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
    src = open(os.path.join(ROOT, 'examples', 'nested2.pl0'), encoding='utf-8').read()

    toks, lex_errs = tokenize_with_errors(src)
    assert not lex_errs, lex_errs

    parser = load_parser()
    prog, perrs = parser.parse_tokens_with_errors(toks, src, auto_recover=False)
    assert prog is not None and perrs == [], perrs

    serrs = analyze(prog, source=src, fold_consts=True)
    assert serrs == [], serrs

    code = CodeGenerator().generate(prog)

    print('=== IR ===')
    for i, (op, l, a) in enumerate(code):
        print(f'{i:04d} {op} {l} {a}')

    vm = VM(code, inputs=[])
    out, tr = vm.run_with_trace()

    print('\nEXPECTED: [1, 10, 2, 20, 20]')
    print('ACTUAL  :', out)

    print('\n=== TRACE key steps ===')
    for i, st in enumerate(tr):
        ins = st.get('instr') or {}
        op = ins.get('op')
        if op in ('CAL', 'WRT') or (op == 'OPR' and ins.get('a') == 0):
            msg = f"#{i} {op} {ins.get('l')} {ins.get('a')} PC {st['pc_before']}->{st['pc_after']} BP {st['bp_before']}->{st['bp_after']} SP {st['sp_before']}->{st['sp_after']}"
            if op == 'WRT' and st.get('io'):
                msg += f" write={st['io'].get('value')}"
            if op == 'CAL':
                cur = (st.get('frames') or {}).get('current')
                if cur:
                    msg += f" AR@B={cur['B']} DL={cur['DL']} RA={cur['RA']} SL={cur['SL']}"
            print(msg)


if __name__ == '__main__':
    main()

