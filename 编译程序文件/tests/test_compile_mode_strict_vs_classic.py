import sys, os

ROOT = os.path.dirname(os.path.dirname(__file__))
sys.path.insert(0, ROOT)

from web.app import process_source


def test_strict_mode_blocks_on_lexer_error():
    src = "program p; begin @ end"  # illegal char
    r = process_source(src, inputs=[], compile_mode='strict', auto_recover=True)
    assert (r.get('lexer_errors') or [])
    assert r.get('parser_errors') == []


def test_strict_mode_disables_auto_recover_for_missing_semicolon():
    # missing semicolon after assignment
    src = "program p; var x; begin x := 1 write(x) end"
    r_strict = process_source(src, inputs=[], compile_mode='strict', auto_recover=True)
    # strict should report parser error, and not auto recover to produce code
    assert (r_strict.get('parser_errors') or [])
    assert r_strict.get('code') is None

    r_classic = process_source(src, inputs=[], compile_mode='classic', auto_recover=True)
    # classic mode may recover; we only assert it tries to parse and gives diagnostics
    assert r_classic.get('tokens') is not None


def test_strict_mode_runs_only_when_clean():
    src = "program p; var x; begin x := 1; write(x) end"
    r = process_source(src, inputs=[], compile_mode='strict', auto_recover=True)
    assert r.get('lexer_errors') == []
    assert r.get('parser_errors') == []
    assert r.get('semantic_errors') == []
    assert r.get('code') is not None
    assert r.get('output') is not None

