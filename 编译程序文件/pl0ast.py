from dataclasses import dataclass
from typing import List, Optional, Any
from diagnostics import Span

## ==============================
## AST（抽象语法树）定义（PL/0 子集）
## ==============================
##
## AST 的位置：
## - Lexer: 源码 -> Token 流
## - Parser: Token 流 -> AST（本文件的数据结构）
## - Semantic: 在 AST 上做静态语义检查（未声明、非法调用、非法左值等）
## - CodeGen:  在 AST 上生成目标机 IR（vm.py 的栈机指令）
## - Optimizer: 对 IR 做低风险优化
## - VM: 解释执行 IR 并输出结果
##
## Span 的意义：
## - span(line/col/...) 用于把 AST 节点映射回源代码位置
## - 前端可以利用 span 做高亮、错误定位、显示“代码片段 + ^”
##
## 命名说明：
## - 文件名用 pl0ast.py 避免与 Python 标准库 ast 冲突。

# AST Node definitions for PL/0 subset (renamed to avoid stdlib ast conflict)

@dataclass
class Program:
    """程序节点。

    对应产生式：
    - <prog> → program <id>；<block> .

    字段：
    - name: 程序名（<id>）
    - block: 程序块（<block>）
    - span: 覆盖 program ... . 的范围（best-effort）
    """
    name: str
    block: 'Block'
    span: Optional[Span] = None

@dataclass
class Block:
    """块节点。

    对应产生式：
    - <block> → [<condecl>][<vardecl>][<proc>]<body>

    字段：
    - consts: 常量声明列表
    - vars:   变量名列表
    - procs:  过程定义列表
    - body:   复合语句/单语句（通常为 begin..end）

    重要约定：
    - Parser 会把该 block 的符号表挂到 block.symtable（动态属性）上，供 semantic/codegen 使用。
    """
    consts: List['ConstDecl']
    vars: List[str]
    procs: List['Procedure']
    body: 'Statement'
    span: Optional[Span] = None

@dataclass
class ConstDecl:
    """常量声明项。

    对应产生式：
    - <const> → <id> := <integer>

    字段：
    - name: 常量名
    - value: 常量值
    """
    name: str
    value: int
    span: Optional[Span] = None

@dataclass
class Procedure:
    """过程定义。

    对应产生式（本项目实现的版本）：
    - procedure <id>([<id>{,<id>}]); <block>

    字段：
    - name: 过程名
    - params: 形参名列表
    - block: 过程体块（拥有独立符号表/作用域）
    """
    name: str
    params: List[str]
    block: Block
    span: Optional[Span] = None

# ------------------------------
# Statements（语句）
# ------------------------------

@dataclass
class Statement:
    """语句基类：用于类型标记。"""
    pass

@dataclass
class Assign(Statement):
    """赋值语句：<id> := <exp>"""
    name: str
    expr: 'Expression'
    span: Optional[Span] = None

@dataclass
class If(Statement):
    """条件语句：if <lexp> then <statement> [else <statement>]"""
    cond: 'Condition'
    then: Statement
    otherwise: Optional[Statement]
    span: Optional[Span] = None

@dataclass
class While(Statement):
    """循环语句：while <lexp> do <statement>"""
    cond: 'Condition'
    body: Statement
    span: Optional[Span] = None

@dataclass
class Call(Statement):
    """过程调用：call <id>([<exp>{,<exp>}])"""
    name: str
    args: List['Expression']
    span: Optional[Span] = None

@dataclass
class Read(Statement):
    """输入语句：read(<id>{,<id>})

    names: 变量名列表（read 的目标必须是 var）
    """
    names: List[str]
    span: Optional[Span] = None

@dataclass
class Write(Statement):
    """输出语句：write(<exp>{,<exp>})"""
    exprs: List['Expression']
    span: Optional[Span] = None

@dataclass
class Begin(Statement):
    """复合语句：begin <statement>{;<statement>} end"""
    statements: List[Statement]
    span: Optional[Span] = None

# ------------------------------
# Expressions（表达式）
# ------------------------------

@dataclass
class Condition:
    """条件表达式（<lexp>）。

    对应产生式：
    - <lexp> → <exp> <lop> <exp> | odd <exp>

    字段：
    - left/right: Expression
    - op: 关系运算 token 类型名（EQ/NE/LT/LE/GT/GE）或 'ODD'
    - odd: True 表示 odd <exp> 形式

    说明：
    - 本项目用一个统一结构表示两类条件，便于 codegen。
    """
    left: 'Expression'
    op: str
    right: 'Expression'
    odd: bool = False
    span: Optional[Span] = None

@dataclass
class Expression:
    """算术表达式（<exp>）。

    对应产生式：
    - <exp> → [+|-]<term>{<aop><term>}

    数据表示：
    - terms: 项（Term）列表
    - signs: 运算符序列
      - signs[0]：第一个 term 的前导符号（'+' 或 '-'，Parser 也可能存 'PLUS'/'MINUS'）
      - signs[i] (i>=1)：第 i 个 term 与前一个 term 的连接操作（PLUS/MINUS）

    好处：
    - codegen 可以按顺序生成每个 term，再按 signs 生成 ADD/SUB。
    """
    terms: List['Term']
    signs: List[str]
    span: Optional[Span] = None

@dataclass
class Term:
    """项（<term>）。

    对应产生式：
    - <term> → <factor>{<mop><factor>}

    字段：
    - factors: 因子列表
    - ops: TIMES/DIV 序列（通常长度为 len(factors)-1）
    """
    factors: List['Factor']
    ops: List[str]
    span: Optional[Span] = None

@dataclass
class Factor:
    """因子（<factor>）。

    对应产生式：
    - <factor>→<id>|<integer>|(<exp>)

    kind:
    - 'id': value 是名字（str）
    - 'number': value 是整数（int）
    - 'expr': value 是 Expression（括号表达式）
    """
    kind: str
    value: Any
    span: Optional[Span] = None
