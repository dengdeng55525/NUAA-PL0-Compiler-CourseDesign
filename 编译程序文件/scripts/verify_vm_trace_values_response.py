"""Verify that /api/compile-like pipeline includes vm_trace step 'values'.

User-visible symptom: VM Trace text does not show Values.
This script checks the backend JSON structure directly, bypassing any frontend caching.

Run:
  python scripts/verify_vm_trace_values_response.py

Expected:
  - prints that step0 has key 'values'
  - prints a non-null values payload when include_symtab+include_vm_trace
"""

from __future__ import annotations

import os
import sys

ROOT = os.path.dirname(os.path.dirname(__file__))
sys.path.insert(0, ROOT)

from web.app import process_source


def main() -> int:
    src = """program p;
var x;
begin
  x := 1;
  write(x)
end
"""
    res = process_source(
        src,
        inputs=[],
        auto_recover=False,
        enable_opt=False,
        diag_v2=True,
        compile_mode='classic',
        view_mode='structured',
        include_symtab=True,
        include_vm_trace=True,
    )

    vt = res.get('vm_trace') or {}
    steps = vt.get('steps') or []
    print('vm_trace.step_count =', vt.get('step_count'))
    print('returned steps =', len(steps))
    if not steps:
        print('ERROR: no steps')
        return 1

    s0 = steps[0]
    print('step0 keys =', sorted(list(s0.keys())))
    print('step0 values =', s0.get('values'))

    if 'values' not in s0:
        print('ERROR: values key missing')
        return 2

    if s0.get('values') is None:
        print('WARN: values is None (likely missing debug vars mapping)')
        return 3

    print('OK')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())

