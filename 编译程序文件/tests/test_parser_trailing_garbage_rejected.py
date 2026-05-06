import os, sys

ROOT = os.path.dirname(os.path.dirname(__file__))
sys.path.insert(0, ROOT)

from web.app import process_source


def test_trailing_garbage_after_end_is_rejected_and_not_run():
    # 用户反馈：end 后面随便输入(((( 仍然能运行。
    # 严格要求：<prog> -> program <id> ; <block>，block 解析完必须 EOF。
    src = """program example;
const
  max := 100,
  min := 1;
var x, y, result;

procedure multiply(a, b);
var temp;
begin
  temp := a * b;
  result := temp
end;

begin
  read(x, y);
  if x > y then
    call multiply(x, y)
  else
    call multiply(y, x);
  write(result);
end(((at
"""

    res = process_source(src, inputs=[3, 5], auto_recover=True, enable_opt=False, compile_mode='classic')

    pe = res.get('parser_errors') or []
    assert pe, 'should have parser errors'
    assert any(e.get('code') == 'PAR_TRAILING_TOKENS' for e in pe), pe

    # must not get code/output
    assert res.get('code') is None
    assert res.get('output') is None

