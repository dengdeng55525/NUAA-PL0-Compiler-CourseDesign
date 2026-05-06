import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from lexer import tokenize

# Explicitly load local parser.py to avoid clashing with stdlib 'parser'
import importlib.util
_parser_path = os.path.join(os.path.dirname(__file__), '..', 'parser.py')
_spec = importlib.util.spec_from_file_location('user_parser', _parser_path)
_mod = importlib.util.module_from_spec(_spec)
assert _spec and _spec.loader
_spec.loader.exec_module(_mod)
parse_tokens_with_errors = getattr(_mod, 'parse_tokens_with_errors')

cases = [
    ("program p; var x; begin x := 1; y := 2; end", 1),  # y 未声明
    ("program p; const a := 1; begin a := 2; end", 1),     # 对常量赋值
    ("program p; var x,x; begin end", 1),                 # 重复定义变量
    ("program p; begin write(1) x := ; end", 2),         # 语法错误多个（缺逗号/分号/表达式）
]

for src, expected_min in cases:
    toks = tokenize(src)
    prog, errs = parse_tokens_with_errors(toks, source=src)
    print('SRC:', src)
    print('Errors found:', len(errs))
    for e in errs:
        print(' -', e['message'], 'line:', e.get('line'), 'col:', e.get('col'))
    assert len(errs) >= expected_min

print('parser error tests passed')
