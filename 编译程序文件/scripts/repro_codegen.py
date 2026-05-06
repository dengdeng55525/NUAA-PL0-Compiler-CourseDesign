import os, sys, importlib.util
# ensure project root (parent of scripts/) is available
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))

# Helper to load modules by filename to avoid stdlib name conflicts
def load_module_from_root(name, filename):
    path = os.path.join(ROOT, filename)
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    # ensure ROOT on sys.path so module's own imports work
    old_sys_path = list(sys.path)
    if ROOT not in sys.path:
        sys.path.insert(0, ROOT)
    try:
        sys.modules[name] = mod
        spec.loader.exec_module(mod)
    finally:
        sys.path[:] = old_sys_path
    return mod

lexer = load_module_from_root('local_lexer', 'lexer.py')
parser = load_module_from_root('local_parser', 'parser.py')
codegen = load_module_from_root('local_codegen', 'codegen.py')
vm_mod = load_module_from_root('local_vm', 'vm.py')

tokenize_with_errors = lexer.tokenize_with_errors
tokenize = lexer.tokenize
parse_tokens_with_errors = parser.parse_tokens_with_errors
parse_tokens = parser.parse_tokens
CodeGenerator = codegen.CodeGenerator
CodeGenError = codegen.CodeGenError
VM = vm_mod.VM

SRC = '''program example;
const
    max := 100,
    min := 1;
var
    x, y, result;

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
    
    while x <= max do
    begin
        x := x + 1;
        if odd x then
            write(x)
    end
end
'''


def main():
    toks, lexerrs = tokenize_with_errors(SRC)
    print('TOKENS:')
    for t in toks:
        print(t)
    if lexerrs:
        print('\nLEX ERRORS:')
        for e in lexerrs:
            print(e.message, e.line, e.col)

    prog, perrs = parse_tokens_with_errors(toks, source=SRC)
    print('\nPARSER ERRORS:')
    for e in perrs:
        print(e)

    if prog is None:
        print('Parsing failed, no program')
        return

    print('\nPROGRAM BLOCK VARS:', getattr(prog.block, 'vars', None))
    st = getattr(prog.block, 'symtable', None)
    if st is not None:
        print('MAIN SYMBOLS:')
        for name, sym in st.symbols.items():
            print(name, sym.kind, sym.addr, sym.def_line, sym.def_col)

    # print a simple AST summary
    print('\nAST SUMMARY:')
    print(f"Program: {prog.name}")
    print(f"Consts: {[c.name+':'+str(c.value) for c in prog.block.consts]}")
    print(f"Vars: {prog.block.vars}")
    print(f"Procs: {[p.name for p in prog.block.procs]}")

    cg = CodeGenerator()
    try:
        code = cg.generate(prog)
        print('\nGENERATED CODE:')
        for i, ins in enumerate(code):
            print(i, ins)
        # run it on VM (no inputs provided)
        vm = VM(code)
        out = vm.run()
        print('\nVM OUTPUT:', out)
    except CodeGenError as e:
        print('\nCODEGEN ERROR:', e)
        # show current generator state
        try:
            print('var_table:', cg.var_table)
            print('proc_addresses:', cg.proc_addresses)
        except Exception:
            pass

if __name__ == '__main__':
    main()
