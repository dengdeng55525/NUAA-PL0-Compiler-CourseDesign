import json

from web.app import process_source


def test_default_response_compatible_no_view_fields_by_default():
    src = """program p;
var x;
begin
  x := 1;
  write(x)
end"""

    res = process_source(src)

    # legacy fields must exist
    assert 'tokens' in res
    assert 'ast' in res
    assert 'code' in res
    assert 'lexer_errors' in res
    assert 'parser_errors' in res
    assert 'semantic_errors' in res

    # view-model / stats should not be present by default
    assert 'tokens_view' not in res
    assert 'ir_view' not in res
    assert 'stats' not in res


def test_flat_view_and_stats_fields_present_when_enabled():
    src = """program p;
var x;
begin
  x := 1;
  write(x)
end"""

    res = process_source(src, view_mode='flat', include_stats=True)

    assert 'tokens_view' in res
    assert res['tokens_view']['mode'] == 'flat'
    assert isinstance(res['tokens_view'].get('flat'), list)

    assert 'ir_view' in res
    assert isinstance(res['ir_view'].get('lines'), list)

    assert 'stats' in res
    assert res['stats']['tokens']['total'] == len(res['tokens'])

    # IR lines count equals generated code length if compilation succeeded
    if res.get('code') is not None:
        assert res['stats']['ir']['instr_count'] == len(res['code'])
        assert len(res['ir_view']['lines']) == len(res['code'])


def test_line_view_groups_tokens_by_line():
    src = """program p;
var x;
begin
  x := 1;
  write(x)
end"""

    res = process_source(src, view_mode='line', include_stats=False)

    assert res['tokens_view']['mode'] == 'line'
    by_line = res['tokens_view'].get('by_line')
    assert isinstance(by_line, list)

    # Should contain at least the 'program' line
    assert any(row.get('line') == 1 for row in by_line)

    # Each row must have tokens list
    for row in by_line:
        assert 'tokens' in row
        assert isinstance(row['tokens'], list)
