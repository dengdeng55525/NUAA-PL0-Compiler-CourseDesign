from typing import Dict, Optional

## ==============================
## 符号表（Symbol Table）
## ==============================
##
## 作用：
## - 在编译器各阶段建立“名字 -> 含义(属性)”的映射，用于：
##   - 语法阶段：记录声明（const/var/proc）并做基础一致性检查
##   - 语义阶段：检查未声明/重复声明/非法左值/调用参数个数等
##   - 代码生成：为变量分配栈帧地址 addr，并计算静态层差 L（LOD/STO/RED 等指令要用）
##
## 结构：
## - 采用经典的“作用域链”模型：每个 SymbolTable 有 parent 指针
## - resolve(name) 从当前表开始向外层逐级查找（模拟静态作用域）
##
## 重要概念：
## - level: 静态层级（0=全局，1=一层嵌套过程，...）
## - addr : 目标机栈帧内相对地址（由 codegen 阶段分配）

class Symbol:
    """\
    符号表条目（Symbol）。

    字段：
    - name: 标识符名
    - kind: 'const' / 'var' / 'proc'
    - value:
        - const: 常量值（int）
        - proc:  形参列表（list[str]），用于 call 参数个数检查
        - var :  通常为 None
    - level: 定义所在的静态层级
    - addr:  栈帧内地址（CodeGen 分配）
    - def_line/def_col: 定义位置（用于“重复定义：先前在 ... 定义”的友好报错）

    说明：
    - 本项目没有类型系统，因此符号信息较轻量。
    - 如果后续要扩展类型，可在 Symbol 上补充 type 字段。
    """

    def __init__(self, name: str, kind: str, value=None, level=0, addr: Optional[int]=None, def_line: Optional[int]=None, def_col: Optional[int]=None):
        self.name = name
        self.kind = kind  # 'const', 'var', 'proc'
        self.value = value
        self.level = level
        self.addr = addr
        # definition position
        self.def_line = def_line
        self.def_col = def_col

    def to_dict(self) -> dict:
        """以 JSON 友好的 dict 形式导出一个符号条目（只读展示用）。"""
        d = {
            'name': self.name,
            'kind': self.kind,
            'level': self.level,
            'addr': self.addr,
            'value': self.value,
            'def': {'line': self.def_line, 'col': self.def_col},
        }
        return d

class SymbolTable:
    """\
    作用域符号表（带 parent 链）。

    level 的用途：
    - 用于计算静态层差：L = current_level - symbol.level
      其中 L 会编码进目标机指令 LOD/STO/RED 的 L 字段。

    约束：
    - 同一作用域（同一张表）内不允许重复定义同名符号。
      发现重复时 raise KeyError(existing_symbol)，由调用者决定如何报错。
    """

    def __init__(self, parent: Optional['SymbolTable']=None, level: int=0):
        self.parent = parent
        self.level = level
        self.symbols: Dict[str, Symbol] = {}
        # children: 仅用于可视化/调试（不参与语义/生成）。
        # Parser 在构造 block 时可以把子作用域表挂到父表上，形成树。
        self.children: list['SymbolTable'] = []

    def define_const(self, name: str, value: int, def_line: Optional[int]=None, def_col: Optional[int]=None):
        """定义常量符号。

        - 若当前作用域已存在同名符号：抛 KeyError(旧符号)
        - 否则写入 self.symbols
        """
        if name in self.symbols:
            # raise with existing symbol so caller can report previous location
            raise KeyError(self.symbols[name])
        s = Symbol(name, 'const', value, self.level, None, def_line, def_col)
        self.symbols[name] = s
        return s

    def define_var(self, name: str, addr: Optional[int] = None, def_line: Optional[int]=None, def_col: Optional[int]=None):
        """定义变量符号。

        addr 通常由 codegen 在更后阶段补齐；这里允许先存 None。
        """
        if name in self.symbols:
            raise KeyError(self.symbols[name])
        s = Symbol(name, 'var', None, self.level, addr, def_line, def_col)
        self.symbols[name] = s
        return s

    def define_proc(self, name: str, level: Optional[int] = None, addr: Optional[int] = None, params: Optional[list]=None, def_line: Optional[int]=None, def_col: Optional[int]=None):
        """定义过程符号。

        params: 形参名列表（可选）。若提供，会放入 symbol.value 以便语义阶段做参数个数检查。
        addr:   过程入口地址（通常由 codegen 回填）。
        """
        if name in self.symbols:
            raise KeyError(self.symbols[name])
        lvl = self.level if level is None else level
        s = Symbol(name, 'proc', None, lvl, addr, def_line, def_col)
        # store parameter list in symbol.value for later semantic checks
        if params is not None:
            s.value = params
        self.symbols[name] = s
        return s

    def resolve(self, name: str) -> Optional[Symbol]:
        """在当前作用域及其外层作用域中查找符号。

        返回：
        - 找到：Symbol
        - 找不到：None
        """
        if name in self.symbols:
            return self.symbols[name]
        if self.parent:
            return self.parent.resolve(name)
        return None

    def to_dict(self, *, include_parent: bool = False, include_children: bool = True) -> dict:
        """\
        将当前作用域导出为 dict。

        - include_parent: 是否在输出中包含 parent 的基本信息（避免递归输出整条链，默认只展示本层）
        - include_children: 是否递归输出 child scopes
        """
        out = {
            'level': self.level,
            'symbols': [s.to_dict() for s in self.symbols.values()],
        }
        if include_parent:
            out['parent'] = {'level': self.parent.level} if self.parent else None
        if include_children:
            out['children'] = [c.to_dict(include_parent=False, include_children=True) for c in (self.children or [])]
        return out


def build_symtable_tree(root: Optional[SymbolTable]) -> Optional[dict]:
    """\
    从根作用域开始，导出“符号表树”。

    说明：
    - 若 Parser/前端没有把 children 关联起来，仍然会返回根表的平面信息。
    - 该函数只用于展示，不会影响编译/执行。
    """
    if root is None:
        return None
    try:
        return root.to_dict(include_parent=False, include_children=True)
    except Exception:
        # fallback: best-effort minimal export
        return {
            'level': getattr(root, 'level', None),
            'symbols': [
                {
                    'name': getattr(s, 'name', None),
                    'kind': getattr(s, 'kind', None),
                    'level': getattr(s, 'level', None),
                    'addr': getattr(s, 'addr', None),
                    'value': getattr(s, 'value', None),
                }
                for s in getattr(root, 'symbols', {}).values()
            ],
            'children': [],
        }

if __name__ == '__main__':
    st = SymbolTable()
    st.define_var('x', 3)
    print(st.resolve('x'))
