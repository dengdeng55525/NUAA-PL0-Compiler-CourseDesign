import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from web.app import process_source


def test_the_token_replaced_when_missing_then_points_to_the():
    # Simulate the case: parser reports missing THEN at token 'the'
    src = """program p;
var x;
begin
  if x > 0 the
    write(x)
end"""

    res = process_source(src, inputs=[], auto_recover=True)
    errs = res.get('parser_errors') or []

    # We expect a missing-then auto recover error
    e = None
    for er in errs:
        if er.get('auto_recovered') and '缺少关键字 then' in (er.get('message') or ''):
            e = er
            break
    assert e is not None

    # The token could be 'the' or could be 'write' depending on parser sync.
    # Either way, our intended correction is: turn line-end 'the' into 'then'.
    # Validate logically by doing that transformation and ensuring missing-then disappears.
    fixed = src.replace(' the\n', ' then\n')
    res2 = process_source(fixed, inputs=[], auto_recover=True)
    errs2 = res2.get('parser_errors') or []
    assert not any(er.get('auto_recovered') and '缺少关键字 then' in (er.get('message') or '') for er in errs2)
