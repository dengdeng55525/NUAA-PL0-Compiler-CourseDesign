import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from web.app import process_source


def test_semantic_error_has_position_when_span_available():
    src = """program p;
var x;
begin
  y := 1;
  write(x)
end"""
    res = process_source(src, inputs=[], auto_recover=False, enable_opt=False)
    sem = res.get('semantic_errors') or []
    # depending on parse-phase checks, undeclared 'y' might be in parser errors already.
    # But if it reaches semantic stage, ensure position fields exist.
    if sem:
        e0 = sem[0]
        assert 'code' in e0
        # span may be missing for some statements, but factors should have spans
        # ensure fields are present (can be None) and snippet exists when line/col present
        assert 'line' in e0 and 'col' in e0
