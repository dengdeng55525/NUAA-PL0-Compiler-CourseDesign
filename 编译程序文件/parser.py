from typing import List, Tuple, Optional
from lexer import Token, LexerError
import pl0ast as ast
from symtable import SymbolTable
from diagnostics import span_from_token, span_cover, Span

# =========================================================
# 解析器（Parser）说明（重要）
# ---------------------------------------------------------
# 1) 本文件实现的是 PL/0 的“语法分析（Syntax Analyzer）”阶段。
#    输入：词法分析器输出的一串 tokens（Token 列表）。
#    输出：抽象语法树 AST（pl0ast.py 里的各节点）。
#
# 2) 解析方式：递归下降（recursive descent）。
#    每个 parse_* 方法基本对应一条或几条 BNF 产生式：
#      - parse()           : <prog>
#      - parse_block()     : <block>
#      - parse_statement() : <statement>
#      - parse_condition() : <lexp>
#      - parse_expression(): <exp>
#      - parse_term()      : <term>
#      - parse_factor()    : <factor>
#
# 3) 自动恢复（auto_recover=True）：
#    解析器会在“某些非常常见且可推断”的语法错误处做轻量恢复，
#    目的：减少级联报错，让后续阶段（语义分析/代码生成）尽量还能继续。
#    这里的恢复策略必须尽量“低风险”：
#      - 只在上下文足够明确时插入/跳过 token
#      - 尽量不改变 program 的结构意义（例如避免随意插入复杂语句）
#
# 4) 同步集（sync set）：
#    当遇到不可恢复的错误时，expect() 会跳过 token 直到遇到：
#      - 期望的 token 类型之一
#      - 或属于同步集（语句/声明边界），用于重新对齐解析
#    这样做的目标是“报错不多也不少”：既能指出错误位置，也要避免一错到底。
# =========================================================

# 人类可读的 token 类型提示（中文）
# 用途：diagnostics 展示 expected token 时，把类型翻译成更友好的中文。
TOKEN_HINTS = {
    'ID': '标识符（如 x）',
    'NUMBER': '数字（如 123）',
    'ASSIGN': "赋值操作符 ':='",
    'SEMI': "分号 ';'",
    'DOT': "句号 '.'",
    'LPAREN': "左括号 '('",
    'RPAREN': "右括号 ')'",
    'PLUS': "加号 '+'",
    'MINUS': "减号 '-'",
    'TIMES': "乘号 '*'",
    'DIV': "除号 '/'",
    'BEGIN': "关键字 begin",
    'END': "关键字 end",
    'PROGRAM': "关键字 program",
    'VAR': "关键字 var",
    'CONST': "关键字 const",
    'PROCEDURE': "关键字 procedure",
    'IF': "关键字 if",
    'THEN': "关键字 then",
    'ELSE': "关键字 else",
    'WHILE': "关键字 while",
    'DO': "关键字 do",
    'CALL': "关键字 call",
    'READ': "关键字 read",
    'WRITE': "关键字 write",
    'EQ': "等号 '='",
    'LT': "小于号 '<'",
    'GT': "大于号 '>'",
}

class ParserError(Exception):
    """语法错误对象。

    设计目标：
    - 既能像 Exception 一样抛出/打印（兼容旧接口 parse_tokens）
    - 也能结构化序列化（to_dict）供 Web 前端展示（包含 snippet/caret）

    字段说明：
    - message: 中文错误信息
    - token:   触发错误的 token（可能为 None）
    - expected: 调用 expect() 时传入的“期望 token 类型集合”，用于提示
    - recovery_action: 若启用自动恢复，则记录“做了什么恢复动作”，便于解释
      例：{'kind':'insert','token_type':'SEMI','token_value':';','reason':'...'}
    """

    def __init__(self, message: str, token: Token = None, expected=None):
        super().__init__(message)
        self.message = message
        self.token = token
        self.expected = expected
        self.code = 'PAR001'
        self.severity = 'error'
        # 若是自动恢复类错误，允许在这里挂载恢复动作信息
        self.recovery_action = None  # e.g. {'kind':'insert','token_type':'THEN','token_value':'then'}
        # derive basic position info from token if available
        if token is not None:
            try:
                self.line = token.line
                self.col = token.col
                self.token_type = token.type
                self.token_value = token.value
            except Exception:
                self.line = None
                self.col = None
                self.token_type = None
                self.token_value = None
        else:
            self.line = None
            self.col = None
            self.token_type = None
            self.token_value = None

    def __str__(self):
        # 注意：这里只用于打印，Web 展示走 to_dict() 会更详细。
        loc = ''
        if getattr(self, 'line', None) is not None and getattr(self, 'col', None) is not None:
            loc = f' at {self.line}:{self.col}'
        return f"{self.message}{loc}"

    def to_dict(self, source: str = None):
        """将 ParserError 序列化为 dict（给前端用）。

        如果提供了 source，会补充：
        - snippet: 错误所在行的源码文本
        - caret:   需要画 ^ 的列偏移（0-based），前端据此定位
        """
        d = {
            'type': 'parser',
            'code': getattr(self, 'code', 'PAR001'),
            'severity': getattr(self, 'severity', 'error'),
            'message': self.message,
            'line': self.line,
            'col': self.col,
            'end_line': None,
            'end_col': None,
            'token_type': self.token_type,
            'token_value': self.token_value,
            'expected': self.expected,
            'notes': [],
        }
        # 自动恢复信息（解释：为什么我“插入/跳过”了 token）
        if getattr(self, 'recovery_action', None):
            ra = self.recovery_action
            try:
                if isinstance(ra, dict):
                    if ra.get('kind') == 'insert':
                        d['notes'].append(f"自动恢复：插入 {ra.get('token_type')}({ra.get('token_value')})")
                    elif ra.get('kind') == 'skip':
                        d['notes'].append(f"自动恢复：跳过 token {ra.get('token_type')}({ra.get('token_value')})")
                    if ra.get('reason'):
                        d['notes'].append(f"原因：{ra.get('reason')}")
            except Exception:
                pass
        # friendly descriptions for expected tokens
        if self.expected:
            try:
                d['expected_display'] = [TOKEN_HINTS.get(t, t) for t in (self.expected if isinstance(self.expected, (list, tuple)) else [self.expected])]
            except Exception:
                d['expected_display'] = [str(self.expected)]
        # snippet/caret：前端画“出错行 + ^ 指针”的核心信息
        if source is not None and self.line is not None and self.col is not None:
            lines = source.splitlines()
            if 1 <= self.line <= len(lines):
                line_text = lines[self.line-1].rstrip('\n')
                caret = max(0, self.col-1)
                d['snippet'] = line_text
                d['caret'] = caret
        return d

class Parser:
    """PL/0 递归下降解析器。

    关键状态：
    - tokens: Token 流（lexer 输出）
    - pos:    当前读取位置（下一个将被 peek/next 读取的 token 索引）
    - current_symtable: 当前作用域的符号表（用于语义前置检查，如“未声明标识符”）

    说明：
    - 本解析器在语法阶段就做了一些“轻量语义检查”（如变量未声明）。
      这样前端体验会更好，但它仍然以解析 AST 为主要任务。
    """

    def __init__(self, tokens: List[Token], auto_recover: bool = True, *, strict_bnf: bool = False):
        self.tokens = tokens
        self.pos = 0
        self.errors: List[ParserError] = []
        # 符号表：根表和当前表
        self.global_symtable = SymbolTable(parent=None, level=0)
        self.current_symtable = self.global_symtable
        # 已报告错误集合，避免重复（使用行,列,信息作为 key）
        self._reported_keys = set()
        # 是否启用自动恢复启发式（例如缺分号自动修复）
        self.auto_recover = auto_recover
        # 是否严格遵守课程要求 BNF（要求.txt）。
        # strict_bnf=True 时：
        # - procedure 必须写成 procedure <id>(...);
        # - call 必须写成 call <id>(...)
        # - 允许空括号 ()
        self.strict_bnf = bool(strict_bnf)

    def report_error(self, message: str, token: Optional[Token] = None, expected=None, *, code: str = 'PAR001', recovery_action=None):
        """记录错误并避免重复。token 可为 None。

        这里的“去重”很关键：
        - 自动恢复可能会导致同一点被多次触发
        - 我们希望用户看到的是“必要的错误”，而不是重复错误
        """
        line = getattr(token, 'line', None) if token is not None else None
        col = getattr(token, 'col', None) if token is not None else None
        key = (line, col, message)
        if key in self._reported_keys:
            return
        self._reported_keys.add(key)
        perr = ParserError(message, token=token, expected=expected)
        perr.code = code
        perr.recovery_action = recovery_action
        self.errors.append(perr)

    def peek(self) -> Token:
        """查看当前 token（不前进）。到达末尾则返回 EOF token。"""
        if self.pos < len(self.tokens):
            return self.tokens[self.pos]
        return Token('EOF', '', -1, -1)

    def next(self) -> Token:
        """消费当前 token 并前进一格。"""
        t = self.peek()
        self.pos += 1
        return t

    def expect(self, *types, sync: Optional[Tuple[str,...]] = None) -> Token:
        """断言下一个 token 属于指定 types之一。

        - 成功：消费并返回 token。
        - 失败：
          1) 若开启 auto_recover，会尝试基于上下文做“插入/跳过”恢复。
          2) 否则记录错误，并采用同步集跳过 token 让解析继续。

        sync 参数：自定义同步集。
        - 不传则使用 default_sync：常见语句边界 (SEMI/END/ELSE/DOT/RPAREN/COMMA)
        - 传了则更“精确地”与当前产生式同步（减少误吞）。
        """
        t = self.peek()
        if t.type in types:
            return self.next()

        # --- context-aware recovery: const/var list separator ---
        # 目标：解决最常见的列表分隔符错误（逗号/分号混用、漏逗号）。
        # 注意：恢复必须谨慎——只对“强特征模式”做推断。
        if self.auto_recover:
            try:
                prev = self.tokens[self.pos - 1] if self.pos - 1 >= 0 else None
                # After reading a const value: NUMBER
                # 场景：const max := 1  pi := 2;  （漏了逗号）
                # 触发点：此处通常 expect('SEMI')（const 声明末尾），但现在看到了 ID 且后面是 (:=|=)
                # 推断：这不是“语句开始”，而是 const 的下一项，所以应插入 COMMA。
                if 'SEMI' in types:
                    if prev is not None and prev.type == 'NUMBER' and t.type == 'ID':
                        nxt = self.tokens[self.pos + 1] if self.pos + 1 < len(self.tokens) else Token('EOF','',-1,-1)
                        if nxt.type in ('ASSIGN','EQ'):
                            self.report_error(
                                "语法错误：缺少逗号 ','（自动恢复）",
                                token=t,
                                expected=('COMMA',),
                                code='PAR_MISSING_COMMA',
                                recovery_action={'kind':'insert','token_type':'COMMA','token_value':',','reason':'const 声明列表中出现新的常量项，推断缺少逗号分隔'}
                            )
                            # 返回“虚拟 token”：不消耗输入流，相当于在当前位置插入一个 COMMA
                            return Token('COMMA', ',', getattr(t, 'line', -1), getattr(t, 'col', -1))

                # If we are in const list and see SEMI but it should behave like COMMA between items.
                # Pattern: ... NUMBER ; ID := NUMBER ...  => treat ';' as a wrong separator and recover by inserting COMMA.
                # 场景：const max := 1; pi := 2;  （中间误用分号）
                # 注意：我们不直接“改写”原 token，而是返回一个虚拟 COMMA，让上层逻辑继续。
                if t.type == 'SEMI':
                    nxt = self.tokens[self.pos + 1] if self.pos + 1 < len(self.tokens) else Token('EOF','',-1,-1)
                    nxt2 = self.tokens[self.pos + 2] if self.pos + 2 < len(self.tokens) else Token('EOF','',-1,-1)
                    if nxt.type == 'ID' and nxt2.type in ('ASSIGN','EQ'):
                        self.report_error(
                            "语法错误：缺少逗号 ','（自动恢复）",
                            token=t,
                            expected=('COMMA',),
                            code='PAR_MISSING_COMMA',
                            recovery_action={'kind':'insert','token_type':'COMMA','token_value':',','reason':'const 列表项之间误用了分号，应当使用逗号'}
                        )
                        return Token('COMMA', ',', getattr(t, 'line', -1), getattr(t, 'col', -1))

                # var list: if we expected SEMI (end of var decl) but next token is ID, it likely misses COMMA.
                # 场景：var x y;  （漏逗号）
                # 这个分支的处理稍“强硬”：会把下一个 ID 吃掉以避免它掉到 statement 里造成级联。
                if 'SEMI' in types and t.type == 'ID' and prev is not None and prev.type == 'ID':
                    # consume the identifier to prevent it from being parsed as a statement later
                    name_tok = self.next()
                    self.report_error(
                        "语法错误：缺少逗号 ','（自动恢复）",
                        token=name_tok,
                        expected=('COMMA',),
                        code='PAR_MISSING_COMMA',
                        recovery_action={'kind':'insert','token_type':'COMMA','token_value':',','reason':'var 声明列表的标识符之间缺少逗号分隔（已跳过下一个标识符以避免级联）'}
                    )
                    return Token('COMMA', ',', getattr(name_tok, 'line', -1), getattr(name_tok, 'col', -1))
            except Exception:
                pass

        if self.auto_recover:
            # 语句起始 token 集（FIRST(statement) 的常用近似）
            stmt_start = ('ID','IF','WHILE','CALL','READ','WRITE','BEGIN')
            # 声明起始 token 集（用于 block 内识别）
            decl_start = ('PROCEDURE','VAR','CONST')
            # 扩展的缺分号场景：
            # 1) 期待 ';'
            # 2) 但当前 token 却是“新的语句/声明/块边界”的开始
            # 推断：上一条语句可能缺少 ';'，插入一个。
            if 'SEMI' in types and t.type in (stmt_start + decl_start + ('END','DOT','EOF')):
                self.report_error(
                    "语法错误：缺少分号 ';'（自动恢复）",
                    token=t,
                    expected=('SEMI',),
                    code='PAR_MISSING_SEMI',
                    recovery_action={'kind':'insert','token_type':'SEMI','token_value':';','reason':'语句/声明后遇到新语句或块边界'}
                )
                return Token('SEMI', ';', getattr(t, 'line', -1), getattr(t, 'col', -1))
            # 如果期待右括号但发现语句开始或分号等，插入 RPAREN
            # 场景：write(x;  / call f(a,b  end
            # 推断：参数列表/括号表达式还未闭合。
            if 'RPAREN' in types and t.type in (stmt_start + ('SEMI','COMMA','END','DOT','EOF')):
                self.report_error(
                    "语法错误：缺少右括号 ')'（自动恢复）",
                    token=t,
                    expected=('RPAREN',),
                    code='PAR_MISSING_RPAREN',
                    recovery_action={'kind':'insert','token_type':'RPAREN','token_value':')','reason':'表达式/实参列表未闭合就遇到语句边界'}
                )
                return Token('RPAREN', ')', getattr(t, 'line', -1), getattr(t, 'col', -1))
            # 缺少 THEN（if 条件后直接开始语句）
            # 两类恢复：
            # - typo：the/thn -> then（把这个 ID 当成 then 并跳过原 token）
            # - missing：直接插入 then
            if 'THEN' in types:
                if t.type == 'ID' and str(getattr(t, 'value', '')).lower() in ('the', 'thn', 'then'):
                    # 这里消费掉错误拼写 token，返回一个“虚拟 THEN”。
                    # 等价于“把 t 改成 then”，且能避免后面把 the 当作标识符继续解析。
                    typo_tok = self.next()
                    self.report_error(
                        "语法错误：缺少关键字 then（自动恢复）",
                        token=typo_tok,
                        expected=('THEN',),
                        code='PAR_TYPO_THEN',
                        recovery_action={'kind':'skip','token_type':'ID','token_value':getattr(typo_tok,'value',None),'reason':'疑似 then 关键字拼写错误：将其视为 then 并跳过该 token'}
                    )
                    return Token('THEN', 'then', getattr(typo_tok, 'line', -1), getattr(typo_tok, 'col', -1))
                if t.type in stmt_start:
                    self.report_error(
                        "语法错误：缺少关键字 then（自动恢复）",
                        token=t,
                        expected=('THEN',),
                        code='PAR_MISSING_THEN',
                        recovery_action={'kind':'insert','token_type':'THEN','token_value':'then','reason':'if 条件后直接出现了语句'}
                    )
                    return Token('THEN', 'then', getattr(t, 'line', -1), getattr(t, 'col', -1))

            # 缺少 DO（while 条件后直接开始语句）
            # 同 THEN：提供 typo 修复与缺失插入。
            if 'DO' in types:
                if t.type == 'ID' and str(getattr(t, 'value', '')).lower() in ('do', 'doo', 'od'):
                    typo_tok = self.next()
                    self.report_error(
                        "语法错误：缺少关键字 do（自动恢复）",
                        token=typo_tok,
                        expected=('DO',),
                        code='PAR_TYPO_DO',
                        recovery_action={'kind':'skip','token_type':'ID','tokenValue':getattr(typo_tok,'value',None),'reason':'疑似 do 关键字拼写错误：将其视为 do 并跳过该 token'}
                    )
                    return Token('DO', 'do', getattr(typo_tok, 'line', -1), getattr(typo_tok, 'col', -1))
                if t.type in stmt_start:
                    self.report_error(
                        "语法错误：缺少关键字 do（自动恢复）",
                        token=t,
                        expected=('DO',),
                        code='PAR_MISSING_DO',
                        recovery_action={'kind':'insert','token_type':'DO','tokenValue':'do','reason':'while 条件后直接出现了语句'}
                    )
                    return Token('DO', 'do', getattr(t, 'line', -1), getattr(t, 'col', -1))

        # record an error in Chinese
        expected = types
        msg = f"语法错误：期望其中之一 {expected}，但找到了 {t.type}"
        self.report_error(msg, token=t, expected=expected)

        # 使用 FIRST/FOLLOW 风格的同步集来恢复，避免过度跳过导致次级错误
        # 默认同步集包括语句边界与括号/逗号等：
        # - ';'  : 语句结束
        # - 'end': 复合语句结束
        # - 'else': if 的分支边界
        # - '.'  : 程序结束
        # - ')' ',' : 参数/表达式列表边界
        default_sync = ('SEMI','END','ELSE','DOT','RPAREN','COMMA')
        if sync is None:
            sync = default_sync

        # 向前扫描直到找到：
        # 1) 期望的 token（则把 pos 移到那里并消费它）
        # 2) 或遇到同步点（停止扫描，让上层逻辑从边界处继续）
        scan_pos = self.pos
        while scan_pos < len(self.tokens) and self.tokens[scan_pos].type not in types and self.tokens[scan_pos].type not in sync:
            scan_pos += 1
        if scan_pos < len(self.tokens) and self.tokens[scan_pos].type in types:
            # 找到期望的 token，前进到该位置并返回它
            self.pos = scan_pos
            return self.next()
        # 否则推进到同步点（但不跨过同步 token）以便恢复
        while self.peek().type not in sync and self.peek().type != 'EOF':
            self.next()
        # 如果当前 token 是同步 token，则直接返回一个 ERROR 占位，解析器的调用方会继续
        cur = self.peek()
        return Token('ERROR', '', cur.line if cur else -1, cur.col if cur else -1)

    def parse(self) -> ast.Program:
        """<prog> → program <id> ; <block>

        注意：严格按 要求.txt 的 BNF，这里没有 '.'。
        因此：
        - 程序结束不应出现 DOT。
        - 若用户输入了 '.'，统一报错并跳过（避免级联）。

        另外：
        - 解析完 <block> 后必须到达 EOF。
          若仍有任何多余 token（例如 end(((( / end ;;;; / end foo ...），
          统一报错为“程序末尾存在多余内容”，并阻止进入后续阶段。
        """
        prog_tok = self.expect('PROGRAM')
        name_tok = self.expect('ID')
        name = name_tok.value if name_tok and name_tok.type == 'ID' else 'unknown'
        self.expect('SEMI')
        block = self.parse_block()

        # <prog> 不允许出现 '.'。
        if self.peek().type == 'DOT':
            dot_tok = self.next()
            self.report_error(
                "语法错误：程序末尾不允许使用 '.'",
                token=dot_tok,
                expected=('EOF',),
                code='PAR_DOT_FORBIDDEN'
            )

        # 解析完 <block> 后，必须是 EOF，否则就是“尾部垃圾 token”。
        t = self.peek()
        if t.type != 'EOF':
            self.report_error(
                f"语法错误：程序末尾存在多余内容（遇到 {t.type}）",
                token=t,
                expected=('EOF',),
                code='PAR_TRAILING_TOKENS'
            )

        prog = ast.Program(name, block)
        prog.span = span_cover(span_from_token(prog_tok), span_from_token(name_tok))
        return prog

    def parse_block(self, params: Optional[List[str]] = None) -> ast.Block:
         """解析 <block>。

         <block> → [<condecl>][<vardecl>][<proc>]<body>

         作用域规则：
         - 每个 block（主程序块、过程块）都会创建一个新的符号表作用域。
         - params（过程形参）会作为本 block 的局部变量提前加入符号表。

         这一层同时负责：
         - const/var/procedure 的声明解析
         - 将声明写入符号表（便于后续 statement 中的引用检查）
         """
         # create scope
         start_tok = self.peek()
         parent = self.current_symtable
         new_level = parent.level + 1 if parent else 0
         block_sym = SymbolTable(parent=parent, level=new_level)
         self.current_symtable = block_sym
         # 如果传入了参数列表，将参数定义为局部变量
         if params:
             for p in params:
                 try:
                     self.current_symtable.define_var(p, None)
                 except KeyError:
                     # 如果参数名重复，记录错误
                     self.report_error(f"重复的参数名 {p}")

         consts = []
         vars = []
         procs = []

         # -------------------------
         # const 声明区：
         # <condecl> → const <const>{,<const>};
         # <const> → <id>:=<integer>
         # -------------------------
         if self.peek().type == 'CONST':
             self.next()
             while True:
                 name_tok = self.expect('ID', sync=('EQ','ASSIGN','COMMA','SEMI'))
                 name = name_tok.value if name_tok else 'unknown'

                 # const 在 PL/0 里要求 ':='；这里对 '=' 做显式报错/可选恢复
                 # 说明：
                 # - 严格语法：只允许 ':='
                 # - 但为了用户体验：遇到 '=' 我们可以选择“跳过它并按 ':='继续”
                 op_tok = self.peek()
                 if op_tok.type == 'ASSIGN':
                     self.next()
                 elif op_tok.type == 'EQ':
                     if self.auto_recover:
                         self.next()  # consume '='
                         self.report_error(
                             "语法错误：const 声明应使用 ':=' 而不是 '='（自动恢复）",
                             token=op_tok,
                             expected=('ASSIGN',),
                             code='PAR_CONST_REQUIRES_ASSIGN',
                             recovery_action={'kind':'skip','token_type':'EQ','token_value':'=','reason':"PL/0 const 声明规范为 ':='；已跳过 '=' 并按 ':=' 继续解析"}
                         )
                     else:
                         self.report_error(
                             "语法错误：const 声明应使用 ':=' 而不是 '='",
                             token=op_tok,
                             expected=('ASSIGN',),
                             code='PAR_CONST_REQUIRES_ASSIGN'
                         )
                         # try to synchronize: consume '=' to avoid infinite loop
                         if op_tok.type == 'EQ':
                             self.next()
                 else:
                     # neither ':=' nor '='
                     self.expect('ASSIGN', sync=('NUMBER','ID','SEMI'))

                 num_tok = self.expect('NUMBER')
                 try:
                     val = int(num_tok.value)
                 except Exception:
                     val = 0

                 # define const in symbol table
                 # 注意：重复定义要报错，但解析要继续。
                 try:
                     self.current_symtable.define_const(name, val, def_line=getattr(name_tok,'line',None), def_col=getattr(name_tok,'col',None))
                 except KeyError as e:
                     prev = e.args[0] if e.args else None
                     if hasattr(prev, 'def_line') and prev.def_line:
                         self.report_error(f"重复定义符号 {name}（先前在 {prev.def_line}:{prev.def_col} 定义）", token=name_tok)
                     else:
                         self.report_error(f"重复定义符号 {name}", token=name_tok)
                 consts.append(ast.ConstDecl(name, val))

                 # --- recovery: wrong ';' used between const items ---
                 # 这段是 parse_block 内对 const 列表的“更强特化”的处理：
                 # 当写成：const a:=1; b:=2; 时，第一处 ';' 实际应为 ','。
                 # 这里选择：消费掉该 ';' 并继续 while True 解析下一项（相当于把 ';' 当作 ',' 用）。
                 if self.auto_recover and self.peek().type == 'SEMI':
                     # lookahead: ; ID (:=|=)
                     try:
                         semi_tok = self.peek()
                         if self.pos + 2 < len(self.tokens):
                             nxt = self.tokens[self.pos + 1]
                             nxt2 = self.tokens[self.pos + 2]
                             if nxt.type == 'ID' and nxt2.type in ('ASSIGN','EQ'):
                                 # consume ';' as an incorrect separator and keep parsing const list
                                 self.next()
                                 self.report_error(
                                     "语法错误：缺少逗号 ','（自动恢复）",
                                     token=semi_tok,
                                     expected=('COMMA',),
                                     code='PAR_MISSING_COMMA',
                                     recovery_action={'kind':'skip','token_type':'SEMI','token_value':';','reason':'const 列表项之间误用了分号，应当使用逗号（已跳过该分号继续解析）'}
                                 )
                                 continue
                     except Exception:
                         pass

                 # 正常 const 列表分隔：逗号继续，否则必须分号结束 condecl
                 if self.peek().type == 'COMMA':
                     self.next()
                     continue
                 self.expect('SEMI')
                 break

         # -------------------------
         # var 声明区：
         # <vardecl> → var <id>{,<id>};
         # -------------------------
         if self.peek().type == 'VAR':
             self.next()
             while True:
                 id_tok = self.expect('ID', sync=('COMMA','SEMI'))
                 name = id_tok.value if id_tok else 'unknown'
                 # define var in symbol table without address yet
                 try:
                     self.current_symtable.define_var(name, None, def_line=getattr(id_tok,'line',None), def_col=getattr(id_tok,'col',None))
                 except KeyError:
                     # try to pull previous symbol info
                     try:
                         prev = self.current_symtable.symbols.get(name)
                         if prev and getattr(prev, 'def_line', None):
                             self.report_error(f"重复定义变量 {name}（先前在 {prev.def_line}:{prev.def_col} 定义）", token=id_tok)
                         else:
                             self.report_error(f"重复定义变量 {name}", token=id_tok)
                     except Exception:
                         self.report_error(f"重复定义变量 {name}", token=id_tok)
                 vars.append(name)
                 if self.peek().type == 'COMMA':
                     self.next(); continue
                 self.expect('SEMI')
                 break

         # -------------------------
         # procedure 声明区：
         # <proc> → procedure <id>([<id>{,<id>}] ); <block> { ; <proc> }
         # 注意：这里实现的是“可嵌套定义”的过程。
         # -------------------------
         while self.peek().type == 'PROCEDURE':
             self.next()
             pname_tok = self.expect('ID', sync=('LPAREN', 'SEMI'))
             pname = pname_tok.value if pname_tok else 'unknown'
             params = []

             # 严格 BNF：procedure <id>(...) 必须带括号
             if self.strict_bnf and self.peek().type != 'LPAREN':
                 self.report_error(
                     "语法错误：过程声明缺少参数括号 '()'（严格 BNF）",
                     token=self.peek(),
                     expected=('LPAREN',),
                     code='PAR_PROC_REQUIRES_PARENS'
                 )

             if self.peek().type == 'LPAREN':
                 # 过程形参列表：只允许 id，用逗号分隔
                 self.next()
                 # 允许空参数列表：procedure p();
                 if self.peek().type != 'RPAREN':
                     while True:
                         p_tok = self.expect('ID', sync=('COMMA', 'RPAREN'))
                         pname_param = p_tok.value if p_tok else 'unknown'
                         params.append(pname_param)
                         if self.peek().type == 'COMMA':
                             self.next()
                             continue
                         break
                 self.expect('RPAREN')

             # 过程头后的分号（语法要求）
             self.expect('SEMI')

             # 尝试在当前符号表中定义过程符号；若重复定义仍需继续解析过程体以保持同步
             # 注意：此时 procedure 的“入口地址”等还未在这里填，后续 codegen 会处理。
             try:
                 proc_sym = self.current_symtable.define_proc(
                     pname, None, None,
                     def_line=getattr(pname_tok, 'line', None),
                     def_col=getattr(pname_tok, 'col', None)
                 )
                 proc_sym.value = params
             except KeyError:
                 # 重复定义：报告并继续解析过程体以保持解析同步
                 prev = None
                 try:
                     prev = self.current_symtable.symbols.get(pname)
                 except Exception:
                     prev = None
                 if prev and getattr(prev, 'def_line', None):
                     self.report_error(f"重复定义过程 {pname}（先前在 {prev.def_line}:{prev.def_col} 定义）", token=pname_tok)
                 else:
                     self.report_error(f"重复定义过程 {pname}", token=pname_tok)

             # 不论 define_proc 是否成功，都必须解析该过程的嵌套块并加入 procs 列表
             pblock = self.parse_block(params=params)
             procs.append(ast.Procedure(pname, params, pblock))
             # 过程声明之间可能有分号，消费它以继续
             if self.peek().type == 'SEMI':
                 self.next()

         # <body> 本质上就是一个 <statement>，在 PL/0 中通常是 begin...end
         body = self.parse_statement()
         block = ast.Block(consts, vars, procs, body)
         # attach symbol table to this block for downstream phases
         block.symtable = self.current_symtable
         block.span = span_cover(span_from_token(start_tok), getattr(body, 'span', None))

         # --- SymbolTable tree wiring (for visualization only) ---
         # 将子过程的 symtable 作为 children 挂到本层 symtable 上，形成“符号表树”。
         # 说明：
         # - 这不改变 resolve/level 的语义；parent 链仍是语义/CG 的依据。
         # - children 仅用于 Web 端可视化展示嵌套层次。
         try:
             if getattr(block, 'symtable', None) is not None:
                 for p in procs:
                     pst = getattr(p.block, 'symtable', None)
                     if pst is not None:
                         # avoid duplicates if parse_block 被多次调用/复用
                         if not hasattr(block.symtable, 'children'):
                             block.symtable.children = []
                         if pst not in block.symtable.children:
                             block.symtable.children.append(pst)
         except Exception:
             pass

         # restore parent
         self.current_symtable = parent
         return block

    def parse_statement(self) -> ast.Statement:
        """解析 <statement>。

        <statement> →
            <id> := <exp>
          | if <lexp> then <statement> [else <statement>]
          | while <lexp> do <statement>
          | call <id>([<exp>{,<exp>}])
          | <body>
          | read (<id>{,<id>})
          | write (<exp>{,<exp>})

        这里同时做“一点点语义检查”：
        - 赋值左值必须是已声明变量
        - call 必须是已声明过程
        - read 参数必须是变量
        """
        t = self.peek()
        # 在语句位置遇到语句终止/边界符号时，直接视为空语句返回，避免误报。
        # 注意：RPAREN 不能在这里被当作“合法边界”，否则会掩盖未闭合括号等严重结构错误。
        if t.type in ('END', 'ELSE', 'DOT', 'EOF'):
            return ast.Begin([])

        # 如果遇到多余的分号，自动跳过（可配置）
        # 场景：begin ; ; x:=1 end
        if t.type == 'SEMI':
            # 合并连续多余分号为一次报告
            if self.auto_recover:
                # count consecutive semicolons and consume them
                start_tok = self.peek()
                cnt = 0
                while self.peek().type == 'SEMI':
                    self.next(); cnt += 1
                # report a single error mentioning how many extra semicolons were skipped
                if cnt == 1:
                    msg = "语法错误：多余的分号 ';'（自动恢复）"
                else:
                    msg = f"语法错误：多余的分号 ';'（自动恢复），共 {cnt} 个"
                self.report_error(msg, token=start_tok)
                return ast.Begin([])
            else:
                self.report_error(f"语法错误：不可识别的语句开始于 {t.type}", token=t)
                self.next()
                return ast.Begin([])

        # assignment: <id> := <exp>
        if t.type == 'ID':
            name_tok = self.next()
            name = name_tok.value
            # check lhs declared and is variable (not const or proc)
            sym = self.current_symtable.resolve(name)
            if sym is None:
                self.report_error(f"未声明的标识符 {name}", token=name_tok)
            else:
                if sym.kind != 'var':
                    self.report_error(f"标识符 {name} 不能作为左值 (不是变量)", token=name_tok)
            self.expect('ASSIGN')
            expr = self.parse_expression()
            node = ast.Assign(name, expr)
            node.span = span_cover(span_from_token(name_tok), getattr(expr, 'span', None))
            return node

        # if <lexp> then <statement> [else <statement>]
        if t.type == 'IF':
            if_tok = self.next()
            cond = self.parse_condition()
            then_tok = self.expect('THEN')
            then_stmt = self.parse_statement()
            otherwise = None
            else_tok = None
            if self.peek().type == 'ELSE':
                else_tok = self.next()
                otherwise = self.parse_statement()
            node = ast.If(cond, then_stmt, otherwise)
            end_span = getattr(otherwise, 'span', None) if otherwise else getattr(then_stmt, 'span', None)
            node.span = span_cover(span_from_token(if_tok), end_span)
            return node

        # while <lexp> do <statement>
        if t.type == 'WHILE':
            w_tok = self.next()
            cond = self.parse_condition()
            do_tok = self.expect('DO')
            body = self.parse_statement()
            node = ast.While(cond, body)
            node.span = span_cover(span_from_token(w_tok), getattr(body, 'span', None))
            return node

        # call <id>(args)
        if t.type == 'CALL':
            c_tok = self.next()
            name_tok = self.expect('ID', sync=('LPAREN','SEMI','RPAREN'))
            name = name_tok.value if name_tok else 'unknown'
            # check that procedure exists
            sym = self.current_symtable.resolve(name)
            if sym is None or sym.kind != 'proc':
                self.report_error(f"未声明的过程 {name}", token=name_tok)

            # 严格 BNF：call <id>(...) 必须带括号
            if self.strict_bnf and self.peek().type != 'LPAREN':
                self.report_error(
                    "语法错误：过程调用缺少参数括号 '()'（严格 BNF）",
                    token=self.peek(),
                    expected=('LPAREN',),
                    code='PAR_CALL_REQUIRES_PARENS'
                )

            args = []
            if self.peek().type == 'LPAREN':
                self.next()
                # 允许空实参列表：call p();
                if self.peek().type != 'RPAREN':
                    while True:
                        args.append(self.parse_expression())
                        if self.peek().type == 'COMMA':
                            self.next(); continue
                        break
                self.expect('RPAREN')

            # 参数数量校验（如果 proc 符号记录了参数列表）
            if sym is not None and sym.kind == 'proc' and getattr(sym, 'value', None) is not None:
                expected_n = len(sym.value)
                if len(args) != expected_n:
                    self.report_error(f"过程 {name} 期望 {expected_n} 个参数，但给出 {len(args)} 个", token=name_tok)
            node = ast.Call(name, args)
            node.span = span_cover(span_from_token(c_tok), span_from_token(name_tok))
            return node

        # compound: begin <statement>{;<statement>} end
        if t.type == 'BEGIN':
            b_tok = self.next()
            stmts = []
            while True:
                stmts.append(self.parse_statement())
                if self.peek().type == 'SEMI':
                    self.next();
                    continue
                # 复合语句内部常见错误：漏分号。
                # 若后面直接又来了一个“语句起始 token”，则推断漏 ';'。
                if self.auto_recover and self.peek().type in ('ID','IF','WHILE','CALL','READ','WRITE','BEGIN'):
                    self.report_error("语法错误：缺少分号 ';'（自动恢复）", token=self.peek(), expected=('SEMI',))
                    continue
                break
            end_tok = self.expect('END')
            node = ast.Begin(stmts)
            node.span = span_cover(span_from_token(b_tok), span_from_token(end_tok))
            return node

        # read (<id>{,<id>})
        if t.type == 'READ':
            r_tok = self.next()
            self.expect('LPAREN')
            names = []
            while True:
                id_tok = self.expect('ID', sync=('COMMA','RPAREN'))
                name = id_tok.value if id_tok else 'unknown'
                # check declared and is var
                sym = self.current_symtable.resolve(name)
                if sym is None:
                    self.report_error(f"未声明的标识符 {name}", token=id_tok)
                else:
                    if sym.kind != 'var':
                        self.report_error(f"标识符 {name} 不能作为 read 的参数 (不是变量)", token=id_tok)
                names.append(name)
                if self.peek().type == 'COMMA':
                    self.next(); continue
                break
            self.expect('RPAREN')
            node = ast.Read(names)
            node.span = span_from_token(r_tok)
            return node

        # write (<exp>{,<exp>})
        if t.type == 'WRITE':
            w_tok = self.next()
            # sync：如果 write 后面缺 '('，也尽量能在表达式/右括号处对齐
            self.expect('LPAREN', sync=('ID','NUMBER','RPAREN'))
            exprs = []
            while True:
                 exprs.append(self.parse_expression())
                 if self.peek().type == 'COMMA':
                     self.next(); continue
                 break
            # sync：')' 后面通常接 ';' 或 'end'
            self.expect('RPAREN', sync=('SEMI','END'))
            node = ast.Write(exprs)
            node.span = span_from_token(w_tok)
            return node

    def parse_condition(self) -> ast.Condition:
        """解析 <lexp>（条件表达式）。

        <lexp> → <exp> <lop> <exp> | odd <exp>

        说明：
        - odd <exp> 是一元条件（判断奇偶），这里用 Condition(odd=True) 表示。
        - 其它关系运算用 op 表示（EQ/NE/LT/LE/GT/GE）。
        """
        # condition ::= odd <expression> | <expression> <relop> <expression>
        if self.peek().type == 'ODD':
            odd_tok = self.next()
            left = self.parse_expression()
            cond = ast.Condition(left, 'ODD', left, odd=True)
            cond.span = span_cover(span_from_token(odd_tok), getattr(left, 'span', None))
            return cond
        left = self.parse_expression()
        # sync：关系运算符出错时，尽量在 THEN/DO/BEGIN 等边界处恢复
        op_tok = self.expect('EQ','NE','LT','LE','GT','GE', sync=('ID','NUMBER','LPAREN','SEMI','THEN','DO','BEGIN'))
        op = op_tok.type if op_tok else 'EQ'
        right = self.parse_expression()
        cond = ast.Condition(left, op, right, odd=False)
        cond.span = span_cover(getattr(left, 'span', None), getattr(right, 'span', None))
        return cond

    def parse_expression(self) -> ast.Expression:
        """解析 <exp>。

        <exp> → [+|-]<term>{<aop><term>}
        <aop> → +|-

        实现细节：
        - signs 数组保存每个 term 前面的符号/运算符（第一个 term 可能是显式 +/-，否则默认为 '+')
        - terms 数组保存 term 列表
        """
        signs = []
        terms = []
        if self.peek().type in ('PLUS','MINUS'):
            signs.append(self.next().type)
        else:
            signs.append('+')
        terms.append(self.parse_term())
        while self.peek().type in ('PLUS','MINUS'):
            signs.append(self.next().type)
            terms.append(self.parse_term())
        expr = ast.Expression(terms, signs)
        # span: from first term to last term
        if terms:
            expr.span = span_cover(getattr(terms[0], 'span', None), getattr(terms[-1], 'span', None))
        return expr

    def parse_term(self) -> ast.Term:
        """解析 <term>。

        <term> → <factor>{<mop><factor>}
        <mop> → *|/
        """
        ops = []
        factors = []
        factors.append(self.parse_factor())
        while self.peek().type in ('TIMES','DIV'):
            ops.append(self.next().type)
            factors.append(self.parse_factor())
        term = ast.Term(factors, ops)
        if factors:
            term.span = span_cover(getattr(factors[0], 'span', None), getattr(factors[-1], 'span', None))
        return term

    def parse_factor(self) -> ast.Factor:
        """解析 <factor>。

        <factor>→ <id> | <integer> | ( <exp> )

        说明：
        - ID：这里不在 factor 阶段强制检查“是否声明”，语义检查更多在 statement 层做。
          （当然也可以做，但要避免重复报错。）
        """
        t = self.peek()
        if t.type == 'ID':
            tok = self.next()
            f = ast.Factor('id', tok.value)
            f.span = span_from_token(tok)
            return f
        if t.type == 'NUMBER':
            tok = self.next()
            f = ast.Factor('number', int(tok.value))
            f.span = span_from_token(tok)
            return f
        if t.type == 'LPAREN':
            ltok = self.next()
            e = self.parse_expression()
            rtok = self.expect('RPAREN')
            f = ast.Factor('expr', e)
            f.span = span_cover(span_from_token(ltok), span_from_token(rtok))
            return f


def parse_tokens(tokens: List[Token]) -> ast.Program:
    """兼容旧接口：有错误就直接 raise 第一个 ParserError。"""
    p = Parser(tokens)
    prog = p.parse()
    # 如果遇到错误，抛出第一个以兼容旧接口
    if p.errors:
        raise p.errors[0]
    return prog


def parse_tokens_with_errors(tokens: List[Token], source: Optional[str] = None, auto_recover: bool = True, *, strict_bnf: bool = False) -> Tuple[Optional[ast.Program], List[dict]]:
    """解析并收集错误，返回 (program_or_none, errors_as_dicts)。

    - tokens: lexer 输出
    - source: 原始源码（可选），用于生成 snippet/caret
    - auto_recover: 是否启用 expect() 的自动恢复

    返回：
    - prog: AST Program（即使有错误也可能返回部分 AST，供后续阶段/可视化使用）
    - errs: 已结构化序列化的错误列表（dict），前端展示用
    """
    p = Parser(tokens, auto_recover=auto_recover, strict_bnf=strict_bnf)
    prog = None
    try:
        prog = p.parse()
    except Exception as e:
        # 捕获意外异常并记录为 internal 错误
        p.errors.append(ParserError(f"内部解析错误: {e}"))
    # 转换错误为字典（中文消息保留）
    errs = []
    for er in p.errors:
        if isinstance(er, ParserError):
            ed = er.to_dict(source)
            # 标注是否为自动恢复产生的错误（启发式）
            if isinstance(er.message, str) and '自动恢复' in er.message:
                ed['auto_recovered'] = True
            else:
                ed['auto_recovered'] = False
            # 如果是自动恢复的缺分号错误，调整 caret 指向上一行末尾以便更直观
            # 说明：
            # - 漏分号通常应该插在“上一行尾部”，但 token 的 line/col 往往是下一行的起点
            # - 这里做一个展示层面的修正：把光标显示挪到上一行末尾
            try:
                if ed.get('auto_recovered') and isinstance(er.message, str) and '缺少分号' in er.message and source:
                    lines = source.splitlines()
                    if ed.get('line') and ed['line'] > 1 and ed['line']-2 < len(lines):
                        prev_idx = ed['line'] - 2
                        prev_line = lines[prev_idx]
                        ed['line'] = prev_idx + 1
                        ed['snippet'] = prev_line
                        ed['caret'] = len(prev_line)
                        # token info suggest insertion position
                        ed['token_type'] = 'SEMI'
                        ed['token_value'] = ';'
            except Exception:
                pass
            errs.append(ed)
        else:
            # fallback
            errs.append({'type': 'parser', 'message': str(er)})
    # attach symbol table if available
    # 注意：这里是兼容性写法，确保 block 上有 symtable 字段给后续 semantic/codegen 用。
    try:
        if prog is not None and hasattr(prog.block, 'symtable'):
            prog.block.symtable = prog.block.symtable
    except Exception:
        pass
    return prog, errs
