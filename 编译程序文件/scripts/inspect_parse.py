import sys, os, json
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from lexer import tokenize_with_errors
from parser import parse_tokens_with_errors

if len(sys.argv) < 2:
    print('Usage: python scripts/inspect_parse.py <source.pl0>')
    sys.exit(1)

path = sys.argv[1]
src = open(path, 'r', encoding='utf-8').read()
# tokenise with lexer errors
tokens, lex_errs = tokenize_with_errors(src)
print('Lexer errors:')
print(json.dumps([e.to_dict(src) for e in lex_errs], ensure_ascii=False, indent=2))
print('\nParser errors (auto_recover=False):')
prog, errs = parse_tokens_with_errors(tokens, src, auto_recover=False)
print(json.dumps(errs, ensure_ascii=False, indent=2))
print('\nParser errors (auto_recover=True):')
prog2, errs2 = parse_tokens_with_errors(tokens, src, auto_recover=True)
print(json.dumps(errs2, ensure_ascii=False, indent=2))

