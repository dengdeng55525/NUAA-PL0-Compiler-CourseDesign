from dataclasses import dataclass
from typing import List, Optional, Any

## ==============================
## ast_local.py（历史/对照用 AST 结构）
## ==============================
##
## 说明：
## - 本文件提供了一套不含 Span 的 AST 定义，主要用于早期开发/对照。
## - 当前项目主流程使用 pl0ast.py（带 Span，便于错误定位与前端高亮）。
## - 为了保证兼容与可追溯性，这个文件保留，但不建议在新代码中继续依赖。

# AST Node definitions for PL/0 subset (legacy, without Span)

@dataclass
class Program:
    """程序节点（legacy 版本，不含 Span）。"""
    name: str
    block: 'Block'

@dataclass
class Block:
    """块节点（legacy 版本）。"""
    consts: List['ConstDecl']
    vars: List[str]
    procs: List['Procedure']
    body: 'Statement'

@dataclass
class ConstDecl:
    """常量声明项（legacy 版本）。"""
    name: str
    value: int

@dataclass
class Procedure:
    """过程定义（legacy 版本）。"""
    name: str
    params: List[str]
    block: Block

# Statements
@dataclass
class Statement:
    """语句基类（legacy 版本）。"""
    pass

@dataclass
class Assign(Statement):
    """赋值语句：<id> := <exp>（legacy 版本）。"""
    name: str
    expr: 'Expression'

@dataclass
class If(Statement):
    """条件语句（legacy 版本）。"""
    cond: 'Condition'
    then: Statement
    otherwise: Optional[Statement]

@dataclass
class While(Statement):
    """循环语句（legacy 版本）。"""
    cond: 'Condition'
    body: Statement

@dataclass
class Call(Statement):
    """过程调用（legacy 版本）。"""
    name: str
    args: List['Expression']

@dataclass
class Read(Statement):
    """输入语句（legacy 版本）。"""
    names: List[str]

@dataclass
class Write(Statement):
    """输出语句（legacy 版本）。"""
    exprs: List['Expression']

@dataclass
class Begin(Statement):
    """复合语句（legacy 版本）。"""
    statements: List[Statement]

# Expressions
@dataclass
class Condition:
    """条件表达式（legacy 版本）。"""
    left: 'Expression'
    op: str
    right: 'Expression'
    odd: bool = False

@dataclass
class Expression:
    """算术表达式（legacy 版本）。"""
    terms: List['Term']
    signs: List[str]  # leading sign for first term and operators between

@dataclass
class Term:
    """项（legacy 版本）。"""
    factors: List['Factor']
    ops: List[str]

@dataclass
class Factor:
    """因子（legacy 版本）。"""
    kind: str  # 'id', 'number', 'expr'
    value: Any

