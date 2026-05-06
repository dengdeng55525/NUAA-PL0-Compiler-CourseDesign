# Ensure project root is on sys.path so imports work when running this file directly
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from main_cli import compile_and_run

def test_sum():
    src = open(os.path.join(os.path.dirname(__file__),'..','examples','sum.pl0'),'r',encoding='utf-8').read()
    out = compile_and_run(src, inputs=[3,5])
    assert out == [8]

if __name__ == '__main__':
    test_sum()
    print('E2E test passed')
