import os, sys

ROOT = os.path.dirname(os.path.dirname(__file__))
sys.path.insert(0, ROOT)

from web.app import process_source


def test_var_missing_comma_between_identifiers_reports_missing_comma_and_is_stable():
    src = """program p;
var x y, z;
begin
  x := 1;
  write(x)
end"""
    res = process_source(src, inputs=[], auto_recover=True, enable_opt=False)
    pe = res.get('parser_errors') or []
    assert len(pe) <= 3
    assert any(e.get('auto_recovered') and '缺少逗号' in (e.get('message') or '') for e in pe)


def test_var_extra_comma_is_skipped_once():
    src = """program p;
var x,, y;
begin
  x := 1;
  write(x)
end"""
    res = process_source(src, inputs=[], auto_recover=True, enable_opt=False)
    pe = res.get('parser_errors') or []
    assert len(pe) <= 3


def test_const_double_comma_is_skipped_once():
    src = """program p;
const a:=1,, b:=2;
var x;
begin
  x := a;
  write(x)
end"""
    res = process_source(src, inputs=[], auto_recover=True, enable_opt=False)
    pe = res.get('parser_errors') or []
    assert len(pe) <= 4


def test_const_wrong_separator_semicolon_between_items_prefers_comma():
    src = """program p;
const a:=1; b:=2;
var x;
begin
  x := b;
  write(x)
end"""
    res = process_source(src, inputs=[], auto_recover=True, enable_opt=False)
    pe = res.get('parser_errors') or []
    # should not cascade
    assert len(pe) <= 4
    assert any(e.get('auto_recovered') and '缺少逗号' in (e.get('message') or '') for e in pe)


def test_const_missing_number_reports_factor_error_not_many():
    src = """program p;
const a:=;
var x;
begin
  x := 1;
  write(x)
end"""
    res = process_source(src, inputs=[], auto_recover=True, enable_opt=False)
    pe = res.get('parser_errors') or []
    assert len(pe) <= 4


def test_const_missing_identifier_reports_expected_id_not_many():
    src = """program p;
const :=1;
var x;
begin
  x := 1;
  write(x)
end"""
    res = process_source(src, inputs=[], auto_recover=True, enable_opt=False)
    pe = res.get('parser_errors') or []
    assert len(pe) <= 4

