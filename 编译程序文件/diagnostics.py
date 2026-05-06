"""Unified diagnostics (errors/warnings) for all compiler phases."""

## ==============================
## 统一诊断（Diagnostics）模块
## ==============================
##
## 目的：
## - 把“词法/语法/语义/优化/代码生成/运行时”等阶段产生的错误与警告
##   统一成一种 JSON(dict) 结构，便于前端 (web/app.py) 用同一套 UI 展示。
##
## 为什么要统一？
## - 如果每个阶段都各自返回不同结构，前端会充满 if/else 特判，维护困难。
## - 统一结构后，前端只需要渲染同一种数据模型。
##
## 核心数据结构（dict）字段约定：
## - type/phase: 产生诊断的阶段（lexer/parser/semantic/optimizer/codegen/runtime/internal）
## - code:       诊断编码（便于检索/测试，例如 PAR_MISSING_SEMI）
## - severity:   error / warning / info
## - message:    面向用户的中文信息
## - line/col:   源码位置（从 1 开始）
## - end_line/end_col: 可选范围（高亮用）
## - snippet/caret: 出错行 + ^ 指示器（caret 为 0-based 列偏移，仅用于显示）
## - expected/expected_display: 可选提示
## - notes:      附加说明（例如“自动恢复：插入 THEN(then)”）
## - auto_recovered: 是否属于自动恢复类提示（前端可选择弱化显示）
##
## 注意：
## - snippet/caret 只用于 UI 展示，不会影响编译逻辑。
## - Span 是一种轻量位置描述，便于 AST 节点和诊断共享定位信息。

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Literal, Optional

Phase = Literal['lexer', 'parser', 'semantic', 'optimizer', 'codegen', 'runtime', 'internal']
Severity = Literal['error', 'warning', 'info']


@dataclass
class Span:
    """源码范围（Span）。

    字段：
    - line/col: 起始位置（1-based）
    - end_line/end_col: 可选结束位置（1-based）

    说明：
    - 目前项目主要依赖起点定位；end_* 作为可选信息，用于高亮范围。
    """

    line: int
    col: int
    end_line: Optional[int] = None
    end_col: Optional[int] = None


def snippet_from_source(source: Optional[str], line: Optional[int], col: Optional[int]):
    """从 source 中提取指定 (line,col) 的行文本与 caret 列。

    返回：
    - (snippet, caret)
      - snippet: 行文本（去除末尾换行）
      - caret:   0-based 列偏移（用于打印 ^）

    若 source 或位置缺失，则返回 (None, None)。
    """
    if not source or not line or not col:
        return None, None
    lines = source.splitlines()
    if 1 <= line <= len(lines):
        s = lines[line - 1].rstrip('\\n')
        return s, max(0, col - 1)
    return None, None


def make_diag(
    *,
    phase: Phase,
    code: str,
    message: str,
    severity: Severity = 'error',
    span: Optional[Span] = None,
    token_type: Optional[str] = None,
    token_value: Optional[str] = None,
    expected: Optional[List[str]] = None,
    expected_display: Optional[List[str]] = None,
    source: Optional[str] = None,
    notes: Optional[List[str]] = None,
    auto_recovered: bool = False,
) -> Dict[str, Any]:
    """构造一条统一诊断 dict。

    说明：
    - 编译器各阶段都可以调用它，生成统一结构。
    - 只要提供 span 和 source，就能自动生成 snippet/caret。

    注意：
    - make_diag 不会抛异常，它只负责“结构化记录”。
    """
    line = span.line if span else None
    col = span.col if span else None
    snippet, caret = snippet_from_source(source, line, col)
    return {
        'type': phase,  # keep compatibility with existing UI
        'code': code,
        'severity': severity,
        'message': message,
        'line': line,
        'col': col,
        'end_line': getattr(span, 'end_line', None) if span else None,
        'end_col': getattr(span, 'end_col', None) if span else None,
        'token_type': token_type,
        'token_value': token_value,
        'expected': expected,
        'expected_display': expected_display,
        'snippet': snippet,
        'caret': caret,
        'notes': notes or [],
        'auto_recovered': auto_recovered,
    }


def span_from_token(token: Any) -> Optional[Span]:
    """从 token（具有 line/col 属性）构造 Span（best-effort）。"""
    if token is None:
        return None
    try:
        line = int(getattr(token, 'line', None))
        col = int(getattr(token, 'col', None))
        return Span(line=line, col=col)
    except Exception:
        return None


def span_cover(a: Optional[Span], b: Optional[Span]) -> Optional[Span]:
    """返回一个覆盖 a..b 的 Span（best-effort）。

    说明：
    - 本项目对 span 的需求主要是“起点定位”，因此这里用 (line,col) 的字典序来比较。
    - end_line/end_col 会尽量填充为较后的位置。
    """
    if a is None:
        return b
    if b is None:
        return a
    # start = min(a, b)
    if (b.line, b.col) < (a.line, a.col):
        start = b
        end = a
    else:
        start = a
        end = b
    return Span(line=start.line, col=start.col, end_line=end.end_line or end.line, end_col=end.end_col or end.col)
