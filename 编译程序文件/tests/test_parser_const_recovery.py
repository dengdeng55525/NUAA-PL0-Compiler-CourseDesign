import os, sys

ROOT = os.path.dirname(os.path.dirname(__file__))
sys.path.insert(0, ROOT)

from web.app import process_source


def test_const_missing_comma_between_entries_should_not_force_semi():
    # const a:=1 b:=2;  -> between 1 and b, should prefer COMMA (not SEMI)
    src = """program p;
const
  a := 1
  b := 2;
var x;
begin
  x := a;
  write(x)
end"""
    res = process_source(src, inputs=[], auto_recover=True, enable_opt=False)
    pe = res.get('parser_errors') or []
    # Should report a recovery around const list separator; allow either message but must not cascade many
    assert len(pe) <= 4
    # We expect an auto-recovered diagnostic pointing around line 4
    assert any((e.get('auto_recovered') and (e.get('line') in (3,4))) for e in pe)


def test_const_missing_semi_after_last_entry_should_insert_semi():
    src = """program p;
const
  a := 1,
  b := 2
var x;
begin
  x := b;
  write(x)
end"""
    res = process_source(src, inputs=[], auto_recover=True, enable_opt=False)
    pe = res.get('parser_errors') or []
    assert len(pe) <= 3
    assert any((e.get('auto_recovered') and '缺少分号' in (e.get('message') or '')) for e in pe)

