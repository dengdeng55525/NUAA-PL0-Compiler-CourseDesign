import os, sys

ROOT = os.path.dirname(os.path.dirname(__file__))
sys.path.insert(0, ROOT)

from web.app import process_source


def test_vm_trace_values_includes_level2_for_nested_procs():
    # Two nested procedures: outer (level=2) contains inner (level=3)
    src = """program lv2demo;
var x;

procedure outer(a);
var t;

  procedure inner(b);
  begin
    t := t + b;
    write(t)
  end;

begin
  t := a;
  call inner(1);
  call inner(2);
  call inner(3)
end;

begin
  x := 0;
  call outer(10)
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

    assert res.get('error') is None
    assert res.get('output') == [11, 13, 16]

    vt = res.get('vm_trace') or {}
    steps = vt.get('steps') or []
    assert steps

    # We expect at least one step inside outer/inner where level=2 variables show (a/t).
    saw_level2 = False
    for s in steps:
        vals = (s or {}).get('values') or {}
        for sc in vals.get('scopes') or []:
            if sc.get('level') == 2:
                vars_ = sc.get('vars') or {}
                if 't' in vars_ or 'a' in vars_:
                    saw_level2 = True
                    break
        if saw_level2:
            break

    assert saw_level2

