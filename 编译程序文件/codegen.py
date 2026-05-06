from typing import List, Tuple
import pl0ast as ast

## ==============================
## 代码生成（Code Generator / Back End）
## ==============================
##
## 作用：
## - 把前端输出的 AST（pl0ast.Program）翻译成“假想栈式目标机”的指令序列 IR。
## - 该目标机由 vm.py 实现，指令统一为三元组 (OP, L, A)。
##
## 输入：
## - AST（Program / Block / Statement / Expression ...）
##
## 输出：
## - List[Instruction]，其中 Instruction = Tuple[str, int, int]
##
## 关键约定（必须与 vm.py 保持一致）：
## 1) 栈帧（活动记录 AR）布局
##    - 本项目约定每个过程栈帧的前 3 个槽位：
##      [B+0]=DL(dynamic link), [B+1]=RA(return addr), [B+2]=SL(static link)
##    - 因此第一个用户变量/形参从 addr=3 开始。
##
## 2) 静态层差 L
##    - LOD/STO/RED 使用 L 表示“沿静态链向外走 L 层后再访问 addr”。
##    - resolve_var_location() 根据符号表 level 计算 L。
##
## 3) 过程调用与参数传递
##    - 生成 call 时：先把每个实参表达式求值并压栈
##    - 再压入 nargs（参数个数）
##    - 再执行 CAL，vm.py 的 CAL 会把参数搬移到新栈帧的 [B+3 ...]
##
## 4) 调用目标回填（patch）
##    - 过程体可能在主程序之后生成，因此 CAL 先占位，最后统一回填入口地址。

# Instruction tuple: (OP, L, A)
Instruction = Tuple[str, int, int]

class CodeGenError(Exception):
    """代码生成阶段错误（通常表示 AST/符号表状态不一致）。"""
    pass

class CodeGenerator:
    """把 AST 翻译成栈机 IR 的生成器。

    主要入口：
    - generate(program) -> List[Instruction]

    内部结构：
    - code: 已生成的指令列表
    - next_addr: 下一条指令地址（等价于 len(code)）
    - current_symtable: 当前作用域符号表（用于计算 L）

    - 本文件只负责“生成指令”，不负责“优化”。优化由 optimizer.py 完成。
    """

    def __init__(self):
        self.code: List[Instruction] = []
        self.next_addr = 0
        self.var_offset = 3  # reserve space for RA, DL, SL
        # current symbol table context used for lexical level calculations
        self.current_symtable = None
        # var_table kept for quick addr mapping for current scope (name -> addr)
        self.var_table = {}
        self.pending_calls = []  # list of (instr_index, proc_name)
        self.proc_addresses = {}  # proc_name -> entry_addr
        self.proc_param_slots = {}  # proc_name -> list of addresses in main param area
        self.main_param_area_start = 0
        # --- debug metadata (for VM trace visualization) ---
        # entry address -> lexical level
        self.op_level = {}

    def emit(self, op: str, l: int, a: int):
        """追加一条指令到 code，并推进 next_addr。"""
        self.code.append((op, l, a))
        self.next_addr += 1

    def generate(self, program: ast.Program) -> List[Instruction]:
        """生成整个程序（主程序 + 所有过程体）。

        生成顺序（与 vm.py 的执行入口一致）：
        1) 生成主程序 INT（申请主栈帧空间）
        2) 生成主程序 body
        3) 插入一条 JMP：让主程序执行完后跳过所有过程体
        4) 生成每个 procedure 的指令（每个过程：INT + body + OPR 0 0 返回）
        5) 回填所有 pending_calls（把 CAL 的目标地址改成真实 entry）
        6) 回填第 3 步的 JMP 目标为“所有过程体之后”的地址
        7) 在程序末尾 emit OPR 0 0（主程序返回/停机）

        注意：
        - 第 3 步的 JMP 是关键：否则主程序执行完会顺序落入过程体指令。
        """
        # Build main var table
        self.var_table = {}
        symtable = getattr(program.block, 'symtable', None)
        # set current_symtable to main for resolution
        self.current_symtable = symtable
        # record main entry level at PC=0 (for VM trace values view)
        try:
            if symtable is not None and hasattr(symtable, 'level'):
                self.op_level[0] = int(symtable.level)
        except Exception:
            pass
        if symtable is not None:
            addr = self.var_offset
            for name, sym in symtable.symbols.items():
                if sym.kind == 'var':
                    sym.addr = addr
                    self.var_table[name] = addr
                    addr += 1
            main_nvars = addr
        else:
            addr = self.var_offset
            for i, name in enumerate(program.block.vars):
                self.var_table[name] = self.var_offset + i
            main_nvars = len(program.block.vars) + self.var_offset

        # Emit INT for main
        self.emit('INT', 0, main_nvars)
        # generate main body
        self.gen_statement(program.block.body)

        # IMPORTANT: jump over procedure bodies after main finishes.
        jmp_over_procs_idx = self.next_addr
        self.emit('JMP', 0, 0)  # patched after all procedures are generated

        # generate code for procedures
        for proc in program.block.procs:
            self.generate_proc(proc)

        # patch pending CALLs
        for idx, pname in self.pending_calls:
            if pname not in self.proc_addresses:
                raise CodeGenError(f"Unknown procedure {pname} when patching calls")
            entry = self.proc_addresses[pname]
            op, l, a = self.code[idx]
            self.code[idx] = ('CAL', l, entry)

        # patch main JMP target to program end position
        self.code[jmp_over_procs_idx] = ('JMP', 0, self.next_addr)

        # program return/halt
        self.emit('OPR', 0, 0)
        return self.code

    def generate_proc(self, proc: ast.Procedure):
        """生成单个过程的目标代码。

        过程体隔离（proc barrier）正确实现要点：
        - 过程的“入口地址 entry”必须稳定地指向该过程自己的入口桩（entry JMP）。
        - 之前的实现中：entry=next_addr 后立刻递归生成嵌套过程体，导致 entry 实际落在“第一个嵌套过程”的代码上。
          结果：call outer 会跳进 inner 的代码，出现莫名其妙的额外输出（例如 31/31/31）。
        - 修复方式：
          1) 先生成并保留一条 entry JMP 占位（这条指令本身就是过程入口）
          2) 把 proc_addresses[proc.name] 绑定到 entry JMP 的地址
          3) 再生成所有嵌套过程体
          4) 回填 entry JMP 的目标为 body 起点
          5) 生成 body（INT + statements）+ RET
        """
        # --- reserve a stable entry stub for THIS procedure ---
        entry = self.next_addr
        self.emit('JMP', 0, 0)  # entry stub; patched to body start later
        self.proc_addresses[proc.name] = entry
        # record lexical level for this procedure entry (used by VM trace)
        try:
            st = getattr(proc.block, 'symtable', None)
            if st is not None and hasattr(st, 'level'):
                self.op_level[int(entry)] = int(st.level)
        except Exception:
            pass
        jmp_to_body_idx = entry

        # build local var table for this proc
        prev_sym = self.current_symtable
        self.current_symtable = getattr(proc.block, 'symtable', None)
        self.var_table = {}
        symtable = self.current_symtable

        # assign parameter addresses in callee frame: params are at offsets var_offset + i
        params = proc.params if proc.params else []
        for i, pname in enumerate(params):
            addr = self.var_offset + i
            if symtable and pname in symtable.symbols:
                symtable.symbols[pname].addr = addr
            self.var_table[pname] = addr

        # assign other local vars starting after params
        if symtable is not None:
            addr = self.var_offset + len(params)
            for name, sym in symtable.symbols.items():
                if sym.kind == 'var' and name not in self.var_table:
                    sym.addr = addr
                    self.var_table[name] = addr
                    addr += 1
            local_count = addr - (self.var_offset + len(params))
        else:
            local_count = len(proc.block.vars)

        # --- generate nested procedures first (won't be executed due to entry JMP) ---
        for p in proc.block.procs:
            self.generate_proc(p)

        # --- patch entry stub to body start ---
        body_start = self.next_addr
        self.code[jmp_to_body_idx] = ('JMP', 0, body_start)

        # --- body ---
        self.emit('INT', 0, self.var_offset + local_count)
        self.gen_statement(proc.block.body)

        # return
        self.emit('OPR', 0, 0)

        # restore previous symtable context
        self.current_symtable = prev_sym

    def gen_statement(self, stmt: ast.Statement):
        """按语句类型生成指令。

        - Assign: 先算右值，再 STO
        - Begin: 顺序生成每条子语句
        - Write: 每个表达式：求值 + WRT
        - Read : 每个变量：RED
        - If   : 条件 -> JPC 回填 -> then -> (else 可选)
        - While: 记录循环头地址 -> 条件 -> JPC 回填 -> body -> JMP 回头
        - Call : 实参求值（压栈）-> LIT nargs -> CAL 占位（后续回填）
        """
        if isinstance(stmt, ast.Assign):
            # evaluate expr -> leave value on stack, then STO 0,a where a is var addr
            self.gen_expression(stmt.expr)
            L, addr = self.resolve_var_location(stmt.name)
            if addr is None:
                raise CodeGenError(f"Unknown variable {stmt.name}")
            self.emit('STO', L, addr)
        elif isinstance(stmt, ast.Begin):
            for s in stmt.statements:
                self.gen_statement(s)
        elif isinstance(stmt, ast.Write):
            for e in stmt.exprs:
                self.gen_expression(e)
                self.emit('WRT', 0, 0)
        elif isinstance(stmt, ast.Read):
            for name in stmt.names:
                L, addr = self.resolve_var_location(name)
                if addr is None:
                    raise CodeGenError(f"Unknown variable {name}")
                self.emit('RED', L, addr)
        elif isinstance(stmt, ast.If):
            self.gen_condition(stmt.cond)
            jpc_addr_index = self.next_addr
            self.emit('JPC', 0, 0)
            self.gen_statement(stmt.then)
            if stmt.otherwise:
                jmp_addr_index = self.next_addr
                self.emit('JMP', 0, 0)
                self.code[jpc_addr_index] = ('JPC', 0, self.next_addr)
                self.gen_statement(stmt.otherwise)
                self.code[jmp_addr_index] = ('JMP', 0, self.next_addr)
            else:
                self.code[jpc_addr_index] = ('JPC', 0, self.next_addr)
        elif isinstance(stmt, ast.While):
            start = self.next_addr
            self.gen_condition(stmt.cond)
            jpc_addr_index = self.next_addr
            self.emit('JPC', 0, 0)
            self.gen_statement(stmt.body)
            self.emit('JMP', 0, start)
            self.code[jpc_addr_index] = ('JPC', 0, self.next_addr)
        elif isinstance(stmt, ast.Call):
            # evaluate argument expressions (push them)
            for arg in stmt.args:
                self.gen_expression(arg)
            # push nargs then CAL; VM will copy args into callee frame
            nargs = len(stmt.args)
            self.emit('LIT', 0, nargs)
            call_index = self.next_addr
            # emit CAL with placeholder; patch later
            self.emit('CAL', 0, 0)
            self.pending_calls.append((call_index, stmt.name))
        else:
            # no-op or unrecognized
            pass

    def gen_condition(self, cond: ast.Condition):
        """生成条件表达式。

        odd: 生成 expr 后用 OPR 7 (ODD)
        relop: 生成 left/right 后用对应的 OPR 关系运算
        """
        if cond.odd:
            self.gen_expression(cond.left)
            self.emit('OPR', 0, 7)  # ODD hypothetical
            return
        # evaluate left and right
        self.gen_expression(cond.left)
        self.gen_expression(cond.right)
        op_map = {
            'EQ': 8, 'NE': 9, 'LT': 10, 'GE': 11, 'GT': 12, 'LE': 13
        }
        op_code = op_map.get(cond.op, 8)
        self.emit('OPR', 0, op_code)

    def gen_expression(self, expr: ast.Expression):
        """生成算术表达式。

        生成策略：
        - 先生成第一个 term
        - 如果前导是 MINUS，则生成 OPR 1 (NEG)
        - 对剩余 term：依次生成 term，再根据 signs[i] 生成 ADD/SUB

        这样 AST 的 Expression(signs/terms) 结构就能映射到线性栈机代码。
        """
        # Generate first term
        if not expr.terms:
            return
        # first term
        self.gen_term(expr.terms[0])
        # handle leading sign (unary + / -)
        if expr.signs and expr.signs[0] == 'MINUS':
            self.emit('OPR', 0, 1)  # negate top
        # remaining terms: for each, generate term then apply add/sub
        for i in range(1, len(expr.terms)):
            self.gen_term(expr.terms[i])
            op = expr.signs[i]
            if op == 'PLUS' or op == '+':
                self.emit('OPR', 0, 2)
            else:
                self.emit('OPR', 0, 3)

    def gen_term(self, term: ast.Term):
        """生成项（乘除链）。

        term.factors/term.ops 是交错结构：
          factor0 (op0) factor1 (op1) factor2 ...
        生成时：
        - 依次把 factor 压栈
        - 从第 2 个 factor 开始，在压入后立刻应用上一个 op：
          TIMES -> OPR 4
          DIV   -> OPR 5
        """
        # Correct order: emit code to push each factor, then between factors emit multiply/divide
        for i, f in enumerate(term.factors):
            # emit factor value
            if f.kind == 'number':
                self.emit('LIT', 0, f.value)
            elif f.kind == 'id':
                # const/var resolution
                if self.current_symtable is not None:
                    sym = self.current_symtable.resolve(f.value)
                    if sym is not None and getattr(sym, 'kind', None) == 'const':
                        self.emit('LIT', 0, int(getattr(sym, 'value', 0)))
                    elif sym is not None and getattr(sym, 'kind', None) == 'proc':
                        raise CodeGenError(f"标识符 {f.value} 是过程，不能作为表达式因子")
                    else:
                        L, addr = self.resolve_var_location(f.value)
                        if addr is None:
                            raise CodeGenError(f"Unknown variable {f.value}")
                        self.emit('LOD', L, addr)
                else:
                    L, addr = self.resolve_var_location(f.value)
                    if addr is None:
                        raise CodeGenError(f"Unknown variable {f.value}")
                    self.emit('LOD', L, addr)
            elif f.kind == 'expr':
                self.gen_expression(f.value)
            # after the second and subsequent factors, apply the corresponding mop
            if i > 0:
                op = term.ops[i-1]
                if op == 'TIMES':
                    self.emit('OPR', 0, 4)
                else:
                    self.emit('OPR', 0, 5)

    def resolve_var_location(self, name: str):
        """把变量名解析为 (L, addr)。

        L: 静态层差（当前层级 - 符号定义层级）
        addr: 符号在其栈帧内的相对地址

        例子：
        - 当前在内层过程里访问外层变量 x：L=1
        - 当前过程内访问自己的局部变量 y：L=0

        如果 current_symtable 缺失，则退化使用 self.var_table（旧逻辑兼容）。
        """
        if self.current_symtable is None:
            # fallback: try var_table
            addr = self.var_table.get(name)
            return 0, addr
        sym = self.current_symtable.resolve(name)
        if sym is None:
            return 0, None
        L = self.current_symtable.level - getattr(sym, 'level', 0)
        return L, getattr(sym, 'addr', None)
