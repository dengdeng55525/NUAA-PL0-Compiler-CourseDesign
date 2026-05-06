import re
from typing import List, NamedTuple, Optional, Tuple

## ==============================
## 词法分析器（Lexer / Lexical Analyzer）
## ==============================
##
## 作用：把源代码字符串扫描成 token 流（Token Stream）。
##
## 输入：
## - text: 源代码字符串（PL/0 源程序）
##
## 输出：
## - tokenize(): List[Token]（严格模式：遇到第一个非法字符直接抛 LexerError）
## - tokenize_with_errors(): (List[Token], List[LexerError])（宽松模式：收集错误并继续）
##
## 位置约定：
## - line 从 1 开始
## - col  从 1 开始
##   这样与编辑器/前端显示一致，便于画 caret (^)。
##
## 设计原则：
## - 词法阶段尽量“简单确定”，不做语法级推断。
## - 但在 LexerError 中提供 expected/suggestions（启发式），让用户更容易定位问题。

class Token(NamedTuple):
    """词法单元（Token）。

    字段：
    - type: 记号类别（如 ID/NUMBER/BEGIN/PLUS/...）
    - value: 原始文本（如 "abc" / "123" / "+"）
    - line/col: 源码位置（从 1 开始）

    说明：
    - Parser 只依赖 Token(type/value/pos) 构造 AST 与报错位置。
    - 这里用 NamedTuple，让 token 轻量且不可变。
    """

    type: str
    value: str
    line: int
    col: int

class LexerError(Exception):
    """词法错误（Lexical Error）。

    统一诊断字段：
    - message/line/col: 错误文本与位置
    - snippet/caret: 出错行文本 + ^ 的列偏移（caret 为 0-based）
    - expected: 启发式提示（不是严格 FIRST/FOLLOW，只用于用户友好）

    注意：
    - LexerError 不会尝试“修复源码”，它只负责把错误报告出来。
    - 修复逻辑如果存在，应当放在更高层（前端或 parser 的 auto_recover）。
    """

    def __init__(self, message: str, line: int, col: int, snippet: str = None, caret: int = None, expected: Optional[List[str]] = None):
        super().__init__(message)
        self.message = message
        self.line = line
        self.col = col
        self.snippet = snippet
        self.caret = caret
        self.expected = expected or []

        # diagnostics fields（统一格式）
        self.code = 'LEX001'
        self.severity = 'error'

    def to_dict(self, source: str = None):
        """序列化为 dict（给 Web 前端统一展示）。

        若 snippet/caret 缺失且提供了 source，则会从 source 中补全。
        """
        d = {
            'type': 'lexer',
            'code': getattr(self, 'code', 'LEX001'),
            'severity': getattr(self, 'severity', 'error'),
            'message': self.message,
            'line': self.line,
            'col': self.col,
            'end_line': None,
            'end_col': None,
            'snippet': self.snippet,
            'caret': self.caret,
            'expected': self.expected,
            'expected_display': self.expected,
            'notes': [],
            'auto_recovered': False,
        }
        if source is not None and (self.snippet is None) and self.line is not None and self.col is not None:
            lines = source.splitlines()
            if 1 <= self.line <= len(lines):
                line_text = lines[self.line-1].rstrip('\\n')
                caret = max(0, self.col-1)
                d['snippet'] = line_text
                d['caret'] = caret
        return d

# KEYWORDS：把识别出的 ID 转成关键字 token（统一用大写类型名）
# 例如：'begin' -> Token(type='BEGIN', value='begin', ...)
KEYWORDS = {
    'program','const','var','procedure','begin','end','if','then','else',
    'while','do','call','read','write','odd'
}

# TOKEN_SPEC：按优先级匹配的 token 正则表。
# ASSIGN(:=) 必须放在 COLON(:) 之前，否则会被拆成 ':' 和 '='。
TOKEN_SPEC = [
    ('NUMBER',   r"\d+"),
    ('ID',       r"[A-Za-z][A-Za-z0-9]*"),
    ('ASSIGN',   r":="),
    ('NE',       r"<>") ,
    ('LE',       r"<="),
    ('GE',       r">="),
    ('LT',       r"<"),
    ('GT',       r">"),
    ('EQ',       r"="),
    ('PLUS',     r"\+"),
    ('MINUS',    r"-"),
    ('TIMES',    r"\*"),
    ('DIV',      r"/"),
    ('LPAREN',   r"\("),
    ('RPAREN',   r"\)"),
    ('COMMA',    r","),
    ('SEMI',     r";"),
    ('DOT',      r"\."),
    ('COLON',    r":"),
    ('WS',       r"[ \t\r\n]+"),
    ('MISMATCH', r".")
]

# MASTER_RE：把上面所有正则合并成一个大正则，并用命名组(lastgroup)区分类型。
MASTER_RE = re.compile('|'.join('(?P<%s>%s)' % pair for pair in TOKEN_SPEC))

def _make_snippet(text: str, pos: int, line: int, col: int):
    """在文本中提取出错行内容，用于更友好的报错展示。"""
    # Return the line content and a caret index (0-based) relative to line start
    lines = text.splitlines()
    if 1 <= line <= len(lines):
        line_text = lines[line-1].rstrip('\\n')
        caret = max(0, col-1)
        return line_text, caret
    # fallback: return entire text
    return text.splitlines()[0] if text else '', 0


def _suggest_for_context(tokens: List[Token]) -> List[str]:
    """基于“前一个 token”的上下文，给出一个非常粗粒度的 expected 提示。

    说明：
    - 这不是严格语法 FIRST/FOLLOW，只是让词法错误更友好。
    - 不参与编译逻辑，也不会影响 parser 行为。
    """
    if not tokens:
        return ['标识符（字母开头）或数字或关键字（如 program）']
    prev = tokens[-1]
    if prev.type in ('ASSIGN','PLUS','MINUS','TIMES','DIV','LPAREN', 'COMMA'):
        return ['数字（如 123）','标识符（如 x）','左括号 (']
    if prev.type in ('ID','NUMBER','RPAREN'):
        return ["运算符 (+ - * /)", "分号 ';'", "句号 '.'", "右括号 )"]
    if prev.type in ('SEMI','BEGIN'):
        return ['标识符（如 x）','if/while/call/read/write/begin']
    return ['字母/数字/运算符/分号/句号/括号']


def tokenize_with_errors(text: str, filename: Optional[str] = None) -> Tuple[List[Token], List[LexerError]]:
    """宽松模式 tokenize：不在首个错误处停止，而是收集错误并继续扫描。

    返回：
    - tokens: 扫描到的 token 列表（尽可能多）
    - errors: LexerError 列表

    继续扫描策略：
    - WS（空白）：只更新 line/col
    - MISMATCH（无法匹配的字符）：记录错误后跳过该字符
    - 其它 token：正常追加

    这更像真实编译器的体验：尽量发现更多错误，而不是遇到第一个错误就退出。
    """
    tokens: List[Token] = []
    errors: List[LexerError] = []
    line = 1
    col = 1
    for mo in MASTER_RE.finditer(text):
        kind = mo.lastgroup
        value = mo.group()
        start = mo.start()
        if kind == 'WS':
            line_breaks = value.count('\n')
            if line_breaks:
                line += line_breaks
                # compute col: position after last newline
                col = len(value) - value.rfind('\n')
            else:
                col += len(value)
            continue
        elif kind == 'ID':
            tk = value.lower()
            if tk in KEYWORDS:
                kind = tk.upper()
        elif kind == 'NUMBER':
            pass
        elif kind == 'MISMATCH':
            snippet, caret = _make_snippet(text, start, line, col)
            # 中文错误信息
            msg = f"非法字符 {value!r}"
            suggestions = _suggest_for_context(tokens)
            errors.append(LexerError(msg, line, col, snippet, caret, expected=suggestions))
            # skip this character (do not append token)
            col += len(value)
            continue
        tokens.append(Token(kind, value, line, col))
        col += len(value)
    return tokens, errors

# 保留兼容的 tokenize 接口：抛出首个错误（以前的行为）
def tokenize(text: str, filename: Optional[str] = None) -> List[Token]:
    """严格模式 tokenize：遇到首个 MISMATCH 直接抛 LexerError。"""
    tokens: List[Token] = []
    line = 1
    col = 1
    for mo in MASTER_RE.finditer(text):
        kind = mo.lastgroup
        value = mo.group()
        start = mo.start()
        if kind == 'WS':
            line_breaks = value.count('\n')
            if line_breaks:
                line += line_breaks
                # compute col: position after last newline
                col = len(value) - value.rfind('\n')
            else:
                col += len(value)
            continue
        elif kind == 'ID':
            tk = value.lower()
            if tk in KEYWORDS:
                kind = tk.upper()
        elif kind == 'NUMBER':
            pass
        elif kind == 'MISMATCH':
            snippet, caret = _make_snippet(text, start, line, col)
            raise LexerError(f"Unexpected character {value!r}", line, col, snippet, caret)
        tokens.append(Token(kind, value, line, col))
        col += len(value)
    return tokens

if __name__ == '__main__':
    s = "program test; var x; begin x := 1; write(x) end"
    print(tokenize(s))
