import sys, os

ROOT = os.path.dirname(os.path.dirname(__file__))
sys.path.insert(0, ROOT)

from lexer import tokenize_with_errors


def test_keyword_typo_the_is_tokenized_as_id():
    src = """program p;
var x;
begin
  if x > 0 the
    write(x)
end"""

    toks, lex_errs = tokenize_with_errors(src)

    # Ensure 'the' becomes an identifier token (typo)
    assert any(t.type == 'ID' and t.value == 'the' for t in toks)

    # Lexer should not throw errors for 'the'
    assert lex_errs == []
