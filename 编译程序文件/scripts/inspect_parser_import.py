import os, sys
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)
import importlib
m = importlib.import_module('parser')
print('parser.__file__=', getattr(m, '__file__', None))
print('has parse_tokens_with_errors?', hasattr(m, 'parse_tokens_with_errors'))
print('keys sample:', [k for k in sorted(m.__dict__.keys()) if not k.startswith('_')][:30])

