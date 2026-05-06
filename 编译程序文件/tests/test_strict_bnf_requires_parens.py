import sys, os
import importlib.util

ROOT = os.path.dirname(os.path.dirname(__file__))
sys.path.insert(0, ROOT)

from lexer import tokenize

# Explicitly load local parser.py to avoid clashing with stdlib 'parser'
_parser_path = os.path.join(ROOT, 'parser.py')
_spec = importlib.util.spec_from_file_location('user_parser', _parser_path)
_mod = importlib.util.module_from_spec(_spec)
assert _spec and _spec.loader
_spec.loader.exec_module(_mod)
parse_tokens_with_errors = getattr(_mod, 'parse_tokens_with_errors')


def test_strict_bnf_requires_parens_for_procedure_and_call():
    # strict_bnf=True 时，必须写 ()，否则应报错。
    src = """program p;
procedure outer;
begin
  call outer
end
"""

    toks = tokenize(src)
    prog, errs = parse_tokens_with_errors(toks, source=src, auto_recover=False, strict_bnf=True)

    assert prog is None or errs
    # 至少包含“过程声明缺少括号”或“过程调用缺少括号”之一
    codes = {e.get('code') for e in (errs or [])}
    assert ('PAR_PROC_REQUIRES_PARENS' in codes) or ('PAR_CALL_REQUIRES_PARENS' in codes)


def test_classic_allows_omitting_parens_for_procedure_and_call():
    # strict_bnf=False（兼容模式）时，允许省略 ()（保持原行为）。
    src = """program p;
procedure outer;
begin
end;
begin
  call outer
end
"""

    toks = tokenize(src)
    prog, errs = parse_tokens_with_errors(toks, source=src, auto_recover=False, strict_bnf=False)

    assert prog is not None
    assert errs == []
