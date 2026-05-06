import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from optimizer import peephole
from vm import VM

code = [
    ('INT', 0, 3),
    ('LIT', 0, 0),
    ('JPC', 0, 5),
    ('LIT', 0, 1),
    ('WRT', 0, 0),
    ('LIT', 0, 2),
    ('WRT', 0, 0),
    ('OPR', 0, 0),
]

print('orig:', code)
print('orig out:')
print(VM(code, []).run())

opt = peephole(code)
print('opt:', opt)
print('opt out:')
print(VM(opt, []).run())
