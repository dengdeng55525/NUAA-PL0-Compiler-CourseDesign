import sys, os
# ensure project root is on sys.path so imports like main_cli work
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from main_cli import compile_and_run

if len(sys.argv) < 2:
    print('Usage: python scripts/run_src.py <source.pl0>')
    sys.exit(1)

path = sys.argv[1]
with open(path, 'r', encoding='utf-8') as f:
    src = f.read()
try:
    out = compile_and_run(src, [])
    print('Program output:')
    print(out)
except Exception as e:
    # print type and message
    print('Error during compile/run:')
    import traceback
    traceback.print_exc()
    sys.exit(2)
