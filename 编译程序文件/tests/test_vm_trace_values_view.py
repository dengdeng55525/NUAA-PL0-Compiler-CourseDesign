import os, sys

ROOT = os.path.dirname(os.path.dirname(__file__))
sys.path.insert(0, ROOT)

from web.app import process_source


def test_vm_trace_includes_values_view_when_symtab_enabled():
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

    assert res.get('error') is None
    vt = res.get('vm_trace')
    assert isinstance(vt, dict)
    steps = vt.get('steps')
    assert isinstance(steps, list) and steps

    # At least one step should have a values view.
    any_values = any(isinstance(s.get('values'), dict) and 'scopes' in s.get('values') for s in steps)
    assert any_values

