"""Verify frontend pretty renderer would include 'Values:' lines.

This script executes the backend to obtain vm_trace JSON, then re-implements
(in Python) a tiny subset of the renderVMTracePretty behavior we care about:
- if any step contains non-empty values.scopes[*].vars, we should see 'Values:'

Run:
  python scripts/verify_vm_trace_values_pretty.py
"""

from __future__ import annotations

import os
import sys

ROOT = os.path.dirname(os.path.dirname(__file__))
sys.path.insert(0, ROOT)

from web.app import process_source


def main() -> int:
    src = """program sum;
var x,y;
begin
  read(x,y);
  x := x + y;
  write(x)
end
"""

    res = process_source(
        src,
        inputs=[3, 5],
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
    if not steps:
        print('ERROR: no steps')
        return 1

    # Find first step where any variables are discoverable
    for i, s in enumerate(steps):
        vals = (s or {}).get('values') or {}
        scopes = vals.get('scopes') or []
        for sc in scopes:
            vars_ = sc.get('vars') or {}
            if vars_:
                print('FOUND vars at step', i, 'level', sc.get('level'), vars_)
                print("EXPECTED pretty output contains: 'Values:'")
                return 0

    print('WARN: no vars found in any step values view (likely missing addr mapping or only global vars not assigned addr)')
    print('values sample step0=', steps[0].get('values'))
    return 2


if __name__ == '__main__':
    raise SystemExit(main())

