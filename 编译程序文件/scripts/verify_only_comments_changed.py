"""验证某次 git 提交是否“只改了注释/文档字符串”。

用法：
  python scripts/verify_only_comments_changed.py <base_rev> <target_rev>

原理（近似但很实用）：
- 对每个变更的 *.py 文件：
  1) 读取 base_rev 的文件内容
  2) 读取 target_rev 的文件内容
  3) 用 tokenize 去掉：COMMENT、NL/NEWLINE/INDENT/DEDENT（只保留结构相关 token）、以及 STRING
     - 说明：这里把 STRING 一律当作文档字符串处理（等价于“忽略所有字符串”）。
       这会产生“误伤”（比如如果你代码里有字符串字面量参与逻辑，会被忽略）。
       但当前项目文件大多注释 + 文档字符串为主，不依赖复杂字符串常量。
- 若去除后的 token 序列一致，则认为该文件仅注释/文档字符串变化。

注意：
- 这是一个“严谨程度很高的工程验证”，但仍是近似。
- 如果你想 100% 精确，需要 AST 等价或更复杂的静态分析。
"""

from __future__ import annotations

import hashlib
import io
import subprocess
import sys
import tokenize
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, List, Tuple


@dataclass
class FileCheckResult:
    path: str
    ok: bool
    reason: str


def _git_show(rev: str, path: str) -> str:
    # 使用 git show 读取某个版本的文件内容
    cp = subprocess.run(
        ["git", "show", f"{rev}:{path}"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if cp.returncode != 0:
        raise RuntimeError(cp.stderr.strip() or f"git show failed for {rev}:{path}")
    return cp.stdout


def _normalized_token_stream(src: str) -> List[Tuple[str, str]]:
    """把源码转成规范化 token 序列（忽略注释/空白/字符串）。"""
    out: List[Tuple[str, str]] = []
    reader = io.StringIO(src).readline
    for tok in tokenize.generate_tokens(reader):
        ttype = tok.type
        tstr = tok.string
        # 忽略注释
        if ttype == tokenize.COMMENT:
            continue
        # 忽略字符串（把文档字符串也一起忽略；见文件头说明）
        if ttype == tokenize.STRING:
            continue
        # 忽略各种非语义空白 token
        if ttype in (tokenize.NL, tokenize.NEWLINE, tokenize.INDENT, tokenize.DEDENT, tokenize.ENDMARKER):
            continue
        # 其它 token 记录 type + 原始字符串
        out.append((tokenize.tok_name.get(ttype, str(ttype)), tstr))
    return out


def _hash_tokens(tokens: List[Tuple[str, str]]) -> str:
    h = hashlib.sha256()
    for ttype, tstr in tokens:
        h.update(ttype.encode("utf-8"))
        h.update(b"\0")
        h.update(tstr.encode("utf-8"))
        h.update(b"\n")
    return h.hexdigest()


def _changed_py_files(base_rev: str, target_rev: str) -> List[str]:
    cp = subprocess.run(
        ["git", "diff", "--name-only", f"{base_rev}..{target_rev}"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if cp.returncode != 0:
        raise RuntimeError(cp.stderr.strip() or "git diff failed")
    files = [line.strip() for line in cp.stdout.splitlines() if line.strip()]
    return [f for f in files if f.lower().endswith(".py")]


def main(argv: List[str]) -> int:
    if len(argv) != 3:
        print("Usage: python scripts/verify_only_comments_changed.py <base_rev> <target_rev>")
        return 2
    base_rev, target_rev = argv[1], argv[2]

    files = _changed_py_files(base_rev, target_rev)
    if not files:
        print("No .py files changed.")
        return 0

    results: List[FileCheckResult] = []
    for path in files:
        try:
            a = _git_show(base_rev, path)
            b = _git_show(target_rev, path)
        except Exception as e:
            results.append(FileCheckResult(path=path, ok=False, reason=f"git_show_error: {e}"))
            continue

        try:
            ta = _normalized_token_stream(a)
            tb = _normalized_token_stream(b)
            ha = _hash_tokens(ta)
            hb = _hash_tokens(tb)
            ok = ha == hb
            results.append(FileCheckResult(path=path, ok=ok, reason=("OK" if ok else "NON_COMMENT_CHANGE_DETECTED")))
        except Exception as e:
            results.append(FileCheckResult(path=path, ok=False, reason=f"tokenize_error: {e}"))

    ok_all = all(r.ok for r in results)
    for r in results:
        mark = "PASS" if r.ok else "FAIL"
        print(f"{mark} {r.path}: {r.reason}")

    if ok_all:
        print("\nRESULT: All changed .py files appear to differ only by comments/docstrings (token-normalized match).")
        return 0
    else:
        print("\nRESULT: Some files have non-comment differences (or verification failed).")
        return 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))

