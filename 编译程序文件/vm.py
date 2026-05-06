from typing import List, Tuple

Instruction = Tuple[str,int,int]

## ==============================
## PL/0 目标机：栈式虚拟机（VM）
## ==============================
##
## 作用：
## - 解释执行 codegen.py 生成的目标机指令序列（IR）。
## - 该 VM 是“假想栈式计算机”，与具体硬件无关，符合 PL/0 课设常见模型。
##
## 指令格式：
## - (OP, L, A)
##   - OP: 操作码（LIT/LOD/STO/CAL/INT/JMP/JPC/OPR/RED/WRT ...）
##   - L : 静态层差（沿静态链 SL 向外走 L 层）
##   - A : 立即数 / 地址 / 子操作码（OPR 的 A 是子操作码）
##
## 运行时状态（经典三寄存器 + 栈）：
## - P: Program Counter，下一个将执行的指令地址
## - B: Base Pointer，当前活动记录（栈帧）的基址
## - T: Top Pointer，栈顶指针（指向最后一个有效元素）
## - stack: 运行栈（同时存：表达式临时值 + 活动记录 AR）
##
## 栈帧（活动记录 AR）布局（与 codegen.py 的 var_offset=3 对应）：
## - 在 CAL 之后，新过程基址为 B=b：
##   stack[B + 0] = DL（动态链，旧 B）
##   stack[B + 1] = RA（返回地址，旧 P）
##   stack[B + 2] = SL（静态链，base(L, oldB)）
##   stack[B + 3 ...] = 参数区（CAL 把实参搬移到这里）
##   stack[...]      = 局部变量区（由 INT 申请空间）
##
## base(L, B) 的含义：
## - 沿静态链 SL 向外走 L 次，得到目标作用域的基址。

## ---------------------------
## OPR 子操作码（本项目约定）
## ---------------------------
##
## 注意：
## - I/O 使用独立指令 RED/WRT，而不是用 OPR=16。这样更清晰也更利于优化器避开 I/O 重排。
## - 关系运算返回 1/0（真/假），与传统 PL/0 语义一致。
##
## 0  : RET/HLT（过程返回；当 B==0 时视为程序结束）
## 1  : NEG（一元负号）
## 2  : ADD
## 3  : SUB
## 4  : MUL
## 5  : DIV
## 7  : ODD
## 8  : EQ
## 9  : NE
## 10 : LT
## 11 : GE
## 12 : GT
## 13 : LE
## ---------------------------
OPR_RET = 0
OPR_NEG = 1
OPR_ADD = 2
OPR_SUB = 3
OPR_MUL = 4
OPR_DIV = 5
OPR_ODD = 7
OPR_EQ = 8
OPR_NE = 9
OPR_LT = 10
OPR_GE = 11
OPR_GT = 12
OPR_LE = 13

class VMError(Exception):
    """VM 执行错误（非法指令/栈溢出/输入不足等）。"""
    pass

class VM:
    """\
    栈式虚拟机解释器。

    inputs:
    - RED 指令会按顺序消耗 inputs 列表。
    - 若输入不足，当前实现以 0 作为默认输入（课程设计常见约定）。

    output:
    - WRT 指令会把值追加到 self.output 中，同时 print 到 stdout。
      Web 端通常只读取 output 列表用于显示。
    """

    def __init__(self, code: List[Instruction], inputs: List[int]=None, *, debug_vars: dict = None):
        # code: 目标机指令序列
        self.code = code
        # inputs: RED 指令会按顺序消耗这个列表
        self.inputs = inputs or []
        self.input_pos = 0
        # stack: 运行栈，固定大小（足够课程设计使用）
        self.stack = [0]*1000
        # P/B/T 初始化（run() 会再次初始化）
        self.P = 0
        self.B = 0
        self.T = -1
        # output: 收集所有 WRT 的输出，便于 web/UI 展示与测试
        self.output = []
        # trace: 仅在需要可视化/调试时启用（避免影响性能/逻辑）
        self.trace = []
        # debug_vars: (可选) 变量视图映射，用于把“某层的 addr”翻译成人类可读的变量名
        # 结构约定（由 web/app.py 提供）：
        # {
        #   'scopes': [
        #       {'level': 0, 'names_by_addr': {3:'x',4:'y',...}},
        #       {'level': 1, 'names_by_addr': {3:'a',4:'b',5:'t',...}},
        #       ...
        #   ]
        # }
        self.debug_vars = debug_vars or None
        # 当前正在执行的指令（仅用于 trace 可视化，run() 每步都会更新）
        self._cur_instr = None

    def base(self, L, B):
        """沿静态链查找上 L 层的基址。

        参数：
        - L: 静态层差
        - B: 起始基址（通常是当前 self.B）

        返回：
        - 目标作用域的基址 b
        """
        b = B
        while L>0:
            b = self.stack[b+2]
            L -= 1
        return b

    def _values_view(self, B: int):
        """\
        生成“变量值视图”（按静态层级显示）。

        关键点（修复版）：
        - 每个活动记录(栈帧)对应一个“定义层级 level”。
        - 仅靠 B/SL/DL/RA 无法直接知道当前帧的 level，因此我们从当前指令地址 PC
          反查该过程入口的 level（由后端通过 debug_vars.op_level 提供）。
        - 显示当前层（level=cur_level）的变量时：基址就是当前 B。
        - 显示外层变量（level=cur_level-1, cur_level-2 ...）时：要沿静态链逐层找到对应外层帧基址。
        """
        if not self.debug_vars or B is None or B < 0:
            return None

        try:
            scopes = self.debug_vars.get('scopes') or []
            op_level = self.debug_vars.get('op_level') or {}

            cur_pc = None
            if isinstance(self._cur_instr, dict):
                cur_pc = self._cur_instr.get('pc_before')
            if cur_pc is None:
                return {'B': int(B), 'level': None, 'scopes': []}

            # op_level 的含义："过程入口(entry)地址 -> 该过程的静态层级"
            # 运行到过程体内部时，pc_before 不一定正好等于 entry。
            # 因此我们用“<= 当前 PC 的最近一个 entry”作为当前过程所属层级。
            cur_level = None
            try:
                pc = int(cur_pc)
                best_entry = None
                best_level = None
                for k, v in op_level.items():
                    try:
                        ek = int(k)
                        lv = int(v)
                    except Exception:
                        continue
                    if ek <= pc and (best_entry is None or ek > best_entry):
                        best_entry = ek
                        best_level = lv
                cur_level = best_level
            except Exception:
                cur_level = None

            if cur_level is None:
                # fallback: 没有 mapping 时，按旧行为（只显示当前 B + addr），但仍限制为 scopes 中的 kv
                out_scopes = []
                for s in scopes:
                    lvl = s.get('level')
                    nba = s.get('names_by_addr') or {}
                    kv = {}
                    for addr_str, name in nba.items():
                        try:
                            addr = int(addr_str)
                        except Exception:
                            continue
                        if addr < 3:
                            continue
                        abs_i = B + addr
                        if 0 <= abs_i < len(self.stack):
                            kv[str(name)] = int(self.stack[abs_i])
                    if kv:
                        out_scopes.append({'level': lvl, 'vars': kv})
                return {'B': int(B), 'level': None, 'scopes': out_scopes}

            # 构建：level->names_by_addr
            by_level = {}
            for s in scopes:
                lvl = s.get('level')
                nba = s.get('names_by_addr') or {}
                if lvl is None:
                    continue
                # 同一 level 可能有多条（fallback + symtab），合并
                by_level.setdefault(int(lvl), {}).update({str(k): v for k, v in nba.items()})

            out_scopes = []

            # 从当前帧开始，逐层沿静态链向外走，显示到最外层（或 mapping 能覆盖的层）
            b_cur = int(B)
            lvl_cur = int(cur_level)
            while True:
                nba = by_level.get(lvl_cur) or {}
                kv = {}
                for addr_str, name in nba.items():
                    try:
                        addr = int(addr_str)
                    except Exception:
                        continue
                    if addr < 3:
                        continue
                    abs_i = b_cur + addr
                    if 0 <= abs_i < len(self.stack):
                        kv[str(name)] = int(self.stack[abs_i])
                if kv:
                    out_scopes.append({'level': lvl_cur, 'vars': kv})

                # 到达全局/无法再向外
                if lvl_cur <= 0:
                    break
                # 静态链：stack[b+2]
                sl = int(self.stack[b_cur + 2]) if (0 <= b_cur + 2 < len(self.stack)) else -1
                if sl < 0 or sl >= len(self.stack):
                    break
                b_cur = sl
                lvl_cur -= 1

            return {'B': int(B), 'level': int(cur_level), 'scopes': out_scopes}
        except Exception:
            return None

    # ---------- Trace helpers (read-only; never mutate semantics) ----------
    def _base_chain(self, L: int, B: int):
        """\
        返回 base(L,B) 的静态链回溯路径，用于可视化。

        例：L=2, B=30
        -> [30, stack[32], stack[stack[32]+2]]

        注意：
        - 该函数只读取 stack，不会改变 VM 状态。
        - 若链条中出现非法基址（越界/负数），会提前截断并标记。
        """
        path = [B]
        b = B
        bad = False
        for _ in range(max(0, int(L))):
            try:
                nxt = self.stack[b + 2]
            except Exception:
                bad = True
                break
            if not isinstance(nxt, int) or nxt < 0 or nxt >= len(self.stack):
                bad = True
                path.append(nxt)
                break
            path.append(nxt)
            b = nxt
        return {'L': int(L), 'start_B': int(B), 'path': path, 'ok': (not bad)}

    def _frame_header(self, B: int):
        """\
        提取活动记录(栈帧)头部字段：DL/RA/SL。

        - DL: 动态链（旧 B）
        - RA: 返回地址（旧 P）
        - SL: 静态链（用于 base(L, B)）
        """
        if B is None or B < 0 or B + 2 >= len(self.stack):
            return None
        return {
            'B': int(B),
            'DL': int(self.stack[B + 0]),
            'RA': int(self.stack[B + 1]),
            'SL': int(self.stack[B + 2]),
        }

    def _capture_step(self, *, op: str, l: int, a: int, P_before: int, B_before: int, T_before: int,
                      P_after: int, B_after: int, T_after: int, note: str = ''):
        """记录一步执行快照（用于 Web 可视化）。"""
        # Remember current instruction context for _values_view
        self._cur_instr = {'pc_before': int(P_before), 'instr': {'op': op, 'l': int(l), 'a': int(a)}}
        # 栈顶预览：只截取尾部一小段，避免输出巨大
        start = max(0, T_after - 40)
        stack_slice = self.stack[start:T_after + 1] if T_after >= 0 else []

        step = {
            'instr': {'op': op, 'l': int(l), 'a': int(a)},
            'pc_before': int(P_before),
            'bp_before': int(B_before),
            'sp_before': int(T_before),
            'pc_after': int(P_after),
            'bp_after': int(B_after),
            'sp_after': int(T_after),
            'stack_window': {
                'start': int(start),
                'values': list(stack_slice),
            },
            'frames': {
                'current': self._frame_header(B_after),
                'caller': self._frame_header(self.stack[B_after] if (B_after is not None and B_after >= 0 and B_after < len(self.stack)) else -1),
                'base_chain': self._base_chain(l, B_after) if op in ('LOD', 'STO', 'RED', 'CAL') else None,
            },
            'note': note or '',
            'io': None,
            'values': self._values_view(B_after),
        }

        # I/O 说明：在 trace 里标记读/写发生的值
        if op == 'RED':
            # RED 在执行时就写入变量槽位，我们这里不额外读取（避免误解），只给出“本次读入的值”
            # 读入值在 run() 中计算；由调用者在 note 或 io 中填充
            pass
        elif op == 'WRT':
            pass

        self.trace.append(step)

    def run_with_trace(self):
        """运行并返回 (output, trace)；语义与 run() 完全一致，只是额外记录 trace。"""
        self.trace = []
        out = self.run(trace=True)
        return out, self.trace

    def run(self, trace: bool = False):
        """\
        执行指令，直到遇到主程序返回（OPR 0 0 且 B==0）或 P 越界。

        若 trace=True：
        - 会把每一步执行记录到 self.trace 中，用于 Web 端可视化。
        - 注意：trace 只读取状态，不改变任何执行语义。
        """
        self.P = 0
        self.T = -1
        self.B = 0
        while self.P < len(self.code):
            P_before = self.P
            B_before = self.B
            T_before = self.T

            instr = self.code[self.P]
            op, l, a = instr
            self.P += 1

            note = ''
            io = None

            if op == 'LIT':
                self.T += 1
                self.stack[self.T] = a
            elif op == 'OPR':
                if a == OPR_RET:
                    if self.B == 0:
                        self.P = len(self.code)
                        if trace:
                            self._capture_step(op=op, l=l, a=a, P_before=P_before, B_before=B_before, T_before=T_before,
                                               P_after=self.P, B_after=self.B, T_after=self.T, note='halt(main return)')
                        break
                    self.T = self.B - 1
                    self.P = self.stack[self.B + 1]
                    self.B = self.stack[self.B]
                elif a == OPR_NEG:
                    self.stack[self.T] = -self.stack[self.T]
                elif a == OPR_ADD:
                    self.T -= 1
                    self.stack[self.T] = self.stack[self.T] + self.stack[self.T+1]
                elif a == OPR_SUB:
                    self.T -= 1
                    self.stack[self.T] = self.stack[self.T] - self.stack[self.T+1]
                elif a == OPR_MUL:
                    self.T -= 1
                    self.stack[self.T] = self.stack[self.T] * self.stack[self.T+1]
                elif a == OPR_DIV:
                    self.T -= 1
                    self.stack[self.T] = int(self.stack[self.T] / self.stack[self.T+1])
                elif a == OPR_ODD:
                    self.stack[self.T] = self.stack[self.T] % 2
                elif a == OPR_EQ:
                    self.T -= 1
                    self.stack[self.T] = 1 if self.stack[self.T] == self.stack[self.T+1] else 0
                elif a == OPR_NE:
                    self.T -= 1
                    self.stack[self.T] = 1 if self.stack[self.T] != self.stack[self.T+1] else 0
                elif a == OPR_LT:
                    self.T -= 1
                    self.stack[self.T] = 1 if self.stack[self.T] < self.stack[self.T+1] else 0
                elif a == OPR_GE:
                    self.T -= 1
                    self.stack[self.T] = 1 if self.stack[self.T] >= self.stack[self.T+1] else 0
                elif a == OPR_GT:
                    self.T -= 1
                    self.stack[self.T] = 1 if self.stack[self.T] > self.stack[self.T+1] else 0
                elif a == OPR_LE:
                    self.T -= 1
                    self.stack[self.T] = 1 if self.stack[self.T] <= self.stack[self.T+1] else 0
                else:
                    raise VMError(f"Unknown OPR code {a}")
            elif op == 'LOD':
                b = self.base(l, self.B)
                self.T += 1
                self.stack[self.T] = self.stack[b + a]
            elif op == 'STO':
                b = self.base(l, self.B)
                self.stack[b + a] = self.stack[self.T]
                self.T -= 1
            elif op == 'CAL':
                if self.T < 0:
                    raise VMError('CALL with empty stack for nargs')
                nargs = self.stack[self.T]
                self.T -= 1
                if nargs < 0:
                    raise VMError('Negative nargs')
                b = self.T - nargs + 1
                if b < 0:
                    raise VMError('Stack underflow when forming activation record')
                for i in range(nargs-1, -1, -1):
                    self.stack[b+3 + i] = self.stack[b + i]
                self.stack[b] = self.B
                self.stack[b+1] = self.P
                self.stack[b+2] = self.base(l, self.B)
                self.T = self.T + 3
                self.B = b
                self.P = a
                note = f'call nargs={nargs}'
            elif op == 'INT':
                self.T += a
            elif op == 'JMP':
                self.P = a
            elif op == 'JPC':
                if self.stack[self.T] == 0:
                    self.P = a
                self.T -= 1
            elif op == 'RED':
                b = self.base(l, self.B)
                if self.input_pos < len(self.inputs):
                    val = self.inputs[self.input_pos]; self.input_pos += 1
                else:
                    val = 0
                self.stack[b + a] = val
                io = {'kind': 'read', 'value': int(val), 'target': {'L': int(l), 'A': int(a), 'base': int(b), 'abs': int(b+a)}}
            elif op == 'WRT':
                val = self.stack[self.T]
                self.output.append(val)
                print(val)
                self.T -= 1
                io = {'kind': 'write', 'value': int(val)}
            else:
                raise VMError(f"Unknown op {op}")

            if trace:
                self._capture_step(op=op, l=l, a=a, P_before=P_before, B_before=B_before, T_before=T_before,
                                   P_after=self.P, B_after=self.B, T_after=self.T, note=note)
                if io is not None and self.trace:
                    self.trace[-1]['io'] = io

        return self.output

if __name__ == '__main__':
    code = [
        ('INT', 0, 4),  # 主程序
        ('LIT', 0, 10),  # 实参
        ('LIT', 0, 1),  # 参数个数
        ('CAL', 0, 7),  # 调用过程
        ('JMP', 0, 11),  # 跳过过程体
        ('OPR', 0, 0),  # 主程序停机
        # 过程体：
        ('INT', 0, 4),  # 过程栈帧
        ('LOD', 0, 3),  # 加载参数
        ('LIT', 0, 1),
        ('OPR', 0, 2),  # 参数+1
        ('WRT', 0, 0),  # 输出
        ('OPR', 0, 0)  # 过程返回
             ]
    vm = VM(code)
    print(vm.run())
