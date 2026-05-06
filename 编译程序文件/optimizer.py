"""Low-risk optimizer pass."""

## ==============================
## 优化器（Optimizer / Peephole）
## ==============================
##
## 本项目的优化器采取“低风险（low-risk）”策略：
## - 目标不是做激进优化，而是用尽量少的规则体现“编译器后端可以有优化阶段”。
## - 最重要约束：必须保证语义不变（尤其是 I/O 顺序不能变）。
##
## 输入/输出：
## - 输入：栈机 IR（List[(op, L, A)]）
## - 输出：优化后的 IR（同结构）
##
## 为什么叫 peephole（窥孔优化）：
## - 只看很短窗口（2~3 条）就决定是否改写。
##
## 当前实现包含的安全变换（每条都有严格前提）：
## 1) 跳转穿透（jump-threading）
## 2) 删除无意义 JMP（JMP 到下一条，且不破坏基本块入口 leader）
## 3) 常量分支折叠（LIT; JPC）
## 4) 立即数常量折叠（LIT/LIT/OPR 或 LIT/OPR 一元）
## 5) 不可达代码删除（DCE），并重映射跳转目标
##
## 关于 CAL 的保守建模：
## - DCE 的 reachability 会把 CAL 同时视为：
##   1) 能到达被调过程入口
##   2) 也能回到 call 之后的下一条
## - 这是为了避免过程体被误判为不可达而删除。

from __future__ import annotations

from typing import Dict, List, Optional, Set, Tuple

Instruction = Tuple[str, int, int]


def _build_successors(code: List[Instruction]) -> Dict[int, Set[int]]:
    """构建每条指令的控制流后继集合 succ[i]。

    这一步是 reachability（可达性）分析的基础。

    规则（与 vm.py 语义一致）：
    - JMP: 只有一个后继：跳转目标 A
    - JPC: 两个后继：
        1) 条件为假 -> 跳转 A
        2) 条件为真 -> 顺序执行 i+1
    - CAL: 为了避免过程体被 DCE 误删，保守地认为有两个后继：
        1) 被调过程入口 A
        2) 返回后落到 i+1
    - OPR 0 0: return/halt，这条没有顺序后继
    - 其它指令：顺序后继 i+1
    """
    n = len(code)
    succ: Dict[int, Set[int]] = {i: set() for i in range(n)}
    for i, (op, l, a) in enumerate(code):
        if op == 'JMP':
            if 0 <= a < n:
                succ[i].add(a)
        elif op == 'JPC':
            if i + 1 < n:
                succ[i].add(i + 1)
            if 0 <= a < n:
                succ[i].add(a)
        elif op == 'CAL':
            # Call has two successors in terms of reachability:
            # - the callee entry point (a)
            # - the fallthrough return site (i+1)
            # This is crucial to keep procedure bodies reachable for DCE.
            if 0 <= a < n:
                succ[i].add(a)
            if i + 1 < n:
                succ[i].add(i + 1)
        elif op == 'OPR' and a == 0:
            continue
        else:
            if i + 1 < n:
                succ[i].add(i + 1)
    return succ


def _reachable(code: List[Instruction]) -> Set[int]:
    """从入口 0 计算可达指令集合（DFS）。"""
    if not code:
        return set()
    succ = _build_successors(code)
    seen: Set[int] = set()
    stack = [0]
    while stack:
        i = stack.pop()
        if i in seen:
            continue
        if not (0 <= i < len(code)):
            continue
        seen.add(i)
        for j in succ.get(i, ()):
            if j not in seen:
                stack.append(j)
    return seen


def _final_jump_target(code: List[Instruction], target: int) -> int:
    """跟随 JMP 链得到最终落点（带环检测，避免死循环）。"""
    n = len(code)
    cur = target
    seen: Set[int] = set()
    while 0 <= cur < n:
        if cur in seen:
            break
        seen.add(cur)
        op, l, a = code[cur]
        if op == 'JMP' and l == 0 and a != cur:
            cur = a
            continue
        break
    return cur


def _remap_jumps(code: List[Instruction], remap: Dict[int, int]) -> List[Instruction]:
    """当我们删除/压缩指令后，需要把旧地址映射到新地址。

    remap: old_index -> new_index

    只重写 (JMP/JPC) 且 l==0 的跳转，因为当前项目只使用绝对地址风格跳转。
    """
    out: List[Instruction] = []
    for op, l, a in code:
        if op in ('JMP', 'JPC') and l == 0 and isinstance(a, int) and a in remap:
            out.append((op, l, remap[a]))
        else:
            out.append((op, l, a))
    return out


def _safe_div(a: int, b: int) -> Optional[int]:
    if b == 0:
        return None
    # VM uses int(a / b) which truncates toward 0 in Python
    return int(a / b)


def _fold_opr_unary(a: int, opr: int) -> Optional[int]:
    if opr == 1:  # NEG
        return -a
    if opr == 7:  # ODD
        return a % 2
    return None


def _fold_opr_binary(a: int, b: int, opr: int) -> Optional[int]:
    if opr == 2:  # ADD
        return a + b
    if opr == 3:  # SUB
        return a - b
    if opr == 4:  # MUL
        return a * b
    if opr == 5:  # DIV
        return _safe_div(a, b)
    # relations: push 1/0
    if opr == 8:  # EQ
        return 1 if a == b else 0
    if opr == 9:  # NE
        return 1 if a != b else 0
    if opr == 10:  # LT
        return 1 if a < b else 0
    if opr == 11:  # GE
        return 1 if a >= b else 0
    if opr == 12:  # GT
        return 1 if a > b else 0
    if opr == 13:  # LE
        return 1 if a <= b else 0
    return None


def peephole(code: List[Instruction]) -> List[Instruction]:
    """主入口：对 IR 应用多轮 peephole + 最终 DCE。

    多轮的意义：某些局部改写会产生新的可优化模式，因此循环几轮直到稳定。
    """
    if not code:
        return []

    cur = list(code)

    # iterate a few rounds to let local rewrites unlock others
    for _round in range(8):
        changed = False

        # 1) jump-threading: rewrite JMP/JPC targets through JMP chains
        for i, (op, l, a) in enumerate(cur):
            if op in ('JMP', 'JPC') and l == 0 and isinstance(a, int):
                new_a = _final_jump_target(cur, a)
                if new_a != a:
                    cur[i] = (op, l, new_a)
                    changed = True

        # 2) remove JMP to next (conservative)
        removed_any = False
        tmp: List[Instruction] = []
        remap: Dict[int, int] = {}

        # Leaders (potential basic-block entries):
        # - start of program
        # - any jump target
        # - any call target
        # - instruction after JPC (since it has fallthrough)
        leaders: Set[int] = {0}
        for idx, (op, l, a) in enumerate(cur):
            if op == 'JMP' and l == 0 and isinstance(a, int) and 0 <= a < len(cur):
                leaders.add(a)
                # NOTE: no (idx+1) leader for JMP; JMP has no fallthrough.
            elif op == 'JPC' and l == 0 and isinstance(a, int):
                if 0 <= a < len(cur):
                    leaders.add(a)
                if idx + 1 < len(cur):
                    leaders.add(idx + 1)
            elif op == 'CAL' and isinstance(a, int) and 0 <= a < len(cur):
                leaders.add(a)
                if idx + 1 < len(cur):
                    leaders.add(idx + 1)

        for i, (op, l, a) in enumerate(cur):
            can_remove = False
            if op == 'JMP' and l == 0 and a == i + 1:
                # Keep JMP-to-next if it jumps to a leader (e.g. proc entry/boundary).
                if (i + 1) not in leaders:
                    can_remove = True
            if can_remove:
                removed_any = True
                continue
            remap[i] = len(tmp)
            tmp.append((op, l, a))
        if removed_any:
            cur = _remap_jumps(tmp, remap)
            changed = True

        # 3) fold constant-branch patterns: LIT; JPC
        tmp2: List[Instruction] = []
        remap2: Dict[int, int] = {}
        i = 0
        while i < len(cur):
            if i + 1 < len(cur):
                op0, l0, a0 = cur[i]
                op1, l1, a1 = cur[i + 1]
                if op0 == 'LIT' and l0 == 0 and op1 == 'JPC' and l1 == 0:
                    if a0 == 0:
                        remap2[i] = len(tmp2)
                        remap2[i + 1] = len(tmp2)
                        tmp2.append(('JMP', 0, a1))
                        changed = True
                        i += 2
                        continue
                    else:
                        changed = True
                        i += 2
                        continue
            remap2[i] = len(tmp2)
            tmp2.append(cur[i])
            i += 1

        if tmp2 != cur:
            for old in range(len(cur) - 1, -1, -1):
                if old in remap2:
                    continue
                nxt = old + 1
                while nxt < len(cur) and nxt not in remap2:
                    nxt += 1
                if nxt < len(cur):
                    remap2[old] = remap2[nxt]
                else:
                    remap2[old] = len(tmp2) - 1 if tmp2 else 0
            cur = _remap_jumps(tmp2, remap2)

        # 4) fold immediate constant OPR sequences
        #    - unary: LIT a ; OPR unary
        #    - binary: LIT a ; LIT b ; OPR binary
        tmp3: List[Instruction] = []
        remap3: Dict[int, int] = {}
        i = 0
        while i < len(cur):
            # unary
            if i + 1 < len(cur):
                op0, l0, a0 = cur[i]
                op1, l1, a1 = cur[i + 1]
                if op0 == 'LIT' and l0 == 0 and op1 == 'OPR' and l1 == 0:
                    r = _fold_opr_unary(int(a0), int(a1))
                    if r is not None:
                        remap3[i] = len(tmp3)
                        remap3[i + 1] = len(tmp3)
                        tmp3.append(('LIT', 0, int(r)))
                        changed = True
                        i += 2
                        continue

            # binary
            if i + 2 < len(cur):
                op0, l0, a0 = cur[i]
                op1, l1, a1 = cur[i + 1]
                op2, l2, a2 = cur[i + 2]
                if (
                    op0 == 'LIT' and l0 == 0
                    and op1 == 'LIT' and l1 == 0
                    and op2 == 'OPR' and l2 == 0
                ):
                    r = _fold_opr_binary(int(a0), int(a1), int(a2))
                    # division by zero -> not safe to fold
                    if r is not None:
                        remap3[i] = len(tmp3)
                        remap3[i + 1] = len(tmp3)
                        remap3[i + 2] = len(tmp3)
                        tmp3.append(('LIT', 0, int(r)))
                        changed = True
                        i += 3
                        continue

            remap3[i] = len(tmp3)
            tmp3.append(cur[i])
            i += 1

        if tmp3 != cur:
            for old in range(len(cur) - 1, -1, -1):
                if old in remap3:
                    continue
                nxt = old + 1
                while nxt < len(cur) and nxt not in remap3:
                    nxt += 1
                if nxt < len(cur):
                    remap3[old] = remap3[nxt]
                else:
                    remap3[old] = len(tmp3) - 1 if tmp3 else 0
            cur = _remap_jumps(tmp3, remap3)

        if not changed:
            break

    # 5) final reachability pass: remove unreachable instructions and rewrite targets
    reach = _reachable(cur)
    if reach != set(range(len(cur))):
        kept: List[Instruction] = []
        remap: Dict[int, int] = {}
        for i, ins in enumerate(cur):
            if i in reach:
                remap[i] = len(kept)
                kept.append(ins)
        cur = _remap_jumps(kept, remap)

    return cur
