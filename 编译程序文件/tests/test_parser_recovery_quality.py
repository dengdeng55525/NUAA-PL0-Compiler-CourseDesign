import os, sys

ROOT = os.path.dirname(os.path.dirname(__file__))
sys.path.insert(0, ROOT)

from web.app import process_source


def _msgs(res):
    return [e.get('message','') for e in (res.get('parser_errors') or [])]


def test_missing_rparen_should_not_cascade_into_many_errors():
    # missing ')' in write should be recovered by inserting RPAREN; should not explode errors
    src = """program p;
var x;
begin
  x := 1;
  write((x);
end"""
    res = process_source(src, inputs=[], auto_recover=True, enable_opt=False)
    pe = res.get('parser_errors') or []
    assert len(pe) <= 3
    assert any('缺少右括号' in (e.get('message') or '') for e in pe)


def test_missing_semi_between_statements_reported_once_in_begin_block():
    src = """program p;
var x;
begin
  x := 1
  x := 2;
  write(x)
end"""
    res = process_source(src, inputs=[], auto_recover=True, enable_opt=False)
    pe = res.get('parser_errors') or []
    # should report missing semicolon at most once
    miss = [e for e in pe if '缺少分号' in (e.get('message') or '')]
    assert len(miss) <= 1


def test_else_without_if_recovers_to_statement_boundary():
    src = """program p;
var x;
begin
  else
    x := 1;
  write(x)
end"""
    res = process_source(src, inputs=[], auto_recover=True, enable_opt=False)
    pe = res.get('parser_errors') or []
    assert len(pe) <= 3


def test_while_condition_typo_doo_should_report_missing_do_not_many():
    src = """program p;
var x;
begin
  x := 0;
  while x < 1 doo
  begin
    x := x + 1
  end
end"""
    res = process_source(src, inputs=[], auto_recover=True, enable_opt=False)
    pe = res.get('parser_errors') or []
    assert len(pe) <= 3
    assert any(('缺少关键字 do' in (e.get('message') or '')) for e in pe)
