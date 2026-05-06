"""Semantic analysis pass."""

## ==============================
## 语义分析（Semantic Analyzer）
## ==============================
##
## 位置：
## - Parser 负责“结构正确”（能否形成 AST）
## - Semantic 负责“含义正确”（静态语义规则）
##
## 本项目在语义阶段检查：
## - 标识符必须先声明再使用（undeclared identifier）
## - const 不能作为赋值左值
## - proc 不能当作表达式因子
## - call 的实参个数必须匹配形参
## - read 的目标必须是变量（var）
##
## 输入/输出：
## - 输入：AST (pl0ast.Program)
## - 输出：List[diagnostic_dict]（统一诊断结构，见 diagnostics.make_diag）
##
## 设计原则：
## - 尽量“保守且确定”：只在能确定错误时报告，不做模糊推断。
## - 不抛异常：收集 errors 列表，让一次编译尽可能多发现问题。
##
## 特殊功能：fold_consts
## - 如果表达式里出现 const 标识符（例如 pi），可在 AST 中把 Factor 从 kind='id'
##   改为 kind='number'，让后端 codegen 更简单。
## - 这是一种低风险优化：不改变 I/O 与控制流。

from __future__ import annotations

from typing import Any, Dict, List, Optional

import pl0ast as ast
from symtable import SymbolTable
from diagnostics import make_diag, Span


def analyze(program: ast.Program, source: Optional[str] = None, fold_consts: bool = True) -> List[Dict[str, Any]]:
    """对 AST 做语义检查（不抛异常，返回统一诊断列表）。

    参数：
    - program: Parser 输出的 AST
    - source: 源码文本（可选，用于生成 snippet/caret）
    - fold_consts: 是否进行“常量折叠”（把 const 引用替换为数字字面量）

    前置条件：
    - Parser 应该在每个 Block 上挂载 symtable（SymbolTable）。
      如果缺失，语义阶段无法完成名字解析，会直接返回空诊断。
    """

    root_st = getattr(program.block, "symtable", None)
    if root_st is None:
        return []

    errors: List[Dict[str, Any]] = []

    def sem_err(message: str, *, code: str = 'SEM001', span: Optional[Span] = None, notes: Optional[List[str]] = None):
        """记录一条语义错误（统一诊断结构）。"""
        errors.append(make_diag(phase='semantic', code=code, message=message, severity='error', span=span, source=source, notes=notes))

    def resolve(st: SymbolTable, name: str):
        """名字解析：在符号表链上查找 name -> Symbol（best-effort）。"""
        try:
            return st.resolve(name)
        except Exception:
            return None

    def check_factor(f: ast.Factor, st: SymbolTable):
        # 因子语义：
        # - id 必须能 resolve
        # - proc 不能作为值使用
        # - （可选）const 可折叠成 number
        if f.kind == "id":
            name = str(f.value)
            sym = resolve(st, name)
            if sym is None:
                sem_err(f"未声明的标识符 {name}", code='SEM_UNDECL', span=getattr(f, 'span', None))
                return
            if getattr(sym, "kind", None) == "proc":
                sem_err(f"标识符 {name} 是过程，不能作为表达式因子", code='SEM_PROC_AS_VALUE', span=getattr(f, 'span', None))
                return
            if fold_consts and getattr(sym, "kind", None) == "const":
                # 把 const 引用替换为 number（低风险优化）
                try:
                    f.kind = "number"
                    f.value = int(getattr(sym, "value", 0))
                except Exception:
                    pass
        elif f.kind == "expr":
            check_expr(f.value, st)

    def check_term(term: ast.Term, st: SymbolTable):
        for f in term.factors:
            check_factor(f, st)

    def check_expr(expr: ast.Expression, st: SymbolTable):
        for t in expr.terms:
            check_term(t, st)

    def check_cond(cond: ast.Condition, st: SymbolTable):
        # odd <exp> 或 <exp> <lop> <exp>
        if cond.odd:
            check_expr(cond.left, st)
        else:
            check_expr(cond.left, st)
            check_expr(cond.right, st)

    def check_stmt(stmt: ast.Statement, st: SymbolTable):
        # 语句语义：针对每类 Statement 做相应规则校验。
        if isinstance(stmt, ast.Assign):
            sym = resolve(st, stmt.name)
            if sym is None:
                sem_err(f"未声明的标识符 {stmt.name}", code='SEM_UNDECL', span=getattr(stmt, 'span', None))
            elif getattr(sym, "kind", None) != "var":
                sem_err(
                    f"标识符 {stmt.name} 不能作为左值 (不是变量)",
                    code='SEM_BAD_LHS',
                    span=getattr(stmt, 'span', None),
                    notes=[f"kind={getattr(sym,'kind',None)}"],
                )
            check_expr(stmt.expr, st)
        elif isinstance(stmt, ast.Read):
            for n in stmt.names:
                sym = resolve(st, n)
                if sym is None:
                    sem_err(f"未声明的标识符 {n}", code='SEM_UNDECL', span=getattr(stmt, 'span', None))
                elif getattr(sym, "kind", None) != "var":
                    sem_err(
                        f"标识符 {n} 不能作为 read 的参数 (不是变量)",
                        code='SEM_READ_TARGET',
                        span=getattr(stmt, 'span', None),
                        notes=[f"kind={getattr(sym,'kind',None)}"],
                    )
        elif isinstance(stmt, ast.Call):
            sym = resolve(st, stmt.name)
            if sym is None or getattr(sym, "kind", None) != "proc":
                sem_err(f"未声明的过程 {stmt.name}", code='SEM_UNDECL_PROC', span=getattr(stmt, 'span', None))
            else:
                params = getattr(sym, "value", None)
                if isinstance(params, list) and len(stmt.args) != len(params):
                    sem_err(f"过程 {stmt.name} 期望 {len(params)} 个参数，但给出 {len(stmt.args)} 个", code='SEM_CALL_ARITY', span=getattr(stmt, 'span', None))
            for a in stmt.args:
                check_expr(a, st)
        elif isinstance(stmt, ast.If):
            check_cond(stmt.cond, st)
            check_stmt(stmt.then, st)
            if stmt.otherwise:
                check_stmt(stmt.otherwise, st)
        elif isinstance(stmt, ast.While):
            check_cond(stmt.cond, st)
            check_stmt(stmt.body, st)
        elif isinstance(stmt, ast.Begin):
            for s in stmt.statements:
                check_stmt(s, st)

    # 入口：先检查主程序块
    check_stmt(program.block.body, root_st)
    # 再检查每个过程块（过程有自己的符号表作用域）
    for p in program.block.procs:
        pst = getattr(p.block, "symtable", None)
        if pst is None:
            continue
        check_stmt(p.block.body, pst)

    return errors

