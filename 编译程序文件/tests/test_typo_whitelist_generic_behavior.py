import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from web.app import process_source


def test_doo_in_while_line_can_be_fixed_by_replacement():
    # This is a backend-level validation that replacing 'doo' with 'do' resolves the grammar issue.
    # Frontend is expected to do this replacement (not insert a new 'do').
    src = """program p;
var x;
begin
  x := 0;
  while x < 1 doo
  begin
    x := x + 1
  end
end"""

    res = process_source(src, inputs=[], auto_recover=True)
    errs = res.get('parser_errors') or []
    assert len(errs) > 0

    fixed = src.replace(' doo\n', ' do\n')
    res2 = process_source(fixed, inputs=[], auto_recover=True)
    errs2 = res2.get('parser_errors') or []

    # after typo corrected, no parser errors expected
    assert errs2 == []
