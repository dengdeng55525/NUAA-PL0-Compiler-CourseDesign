# 添加工程根到 sys.path，确保能导入项目根目录的模块
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from flask import Flask, request, jsonify, render_template
from typing import Any, Optional
import json
import traceback
import time

from lexer import tokenize, tokenize_with_errors, LexerError
# from parser import parse_tokens, parse_tokens_with_errors, ParserError  # avoid stdlib clash
import importlib.util

# Explicitly load local parser.py to avoid clashing with stdlib 'parser'
PARSER_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'parser.py')
_spec = importlib.util.spec_from_file_location('user_parser', PARSER_PATH)
_user_parser = importlib.util.module_from_spec(_spec)
assert _spec and _spec.loader
_spec.loader.exec_module(_user_parser)
parse_tokens = getattr(_user_parser, 'parse_tokens')
parse_tokens_with_errors = getattr(_user_parser, 'parse_tokens_with_errors')
ParserError = getattr(_user_parser, 'ParserError')

from codegen import CodeGenerator
from vm import VM
import pl0ast

app = Flask(__name__, template_folder='templates', static_folder='static')

# Helper: convert pl0ast dataclass instances to dict recursively
from dataclasses import is_dataclass, asdict

def ast_node_to_dict(node: Any):
    # Handle dataclasses
    if is_dataclass(node):
        d = asdict(node)
        # recursively convert any pl0ast nodes inside
        def conv(x):
            if isinstance(x, list):
                return [conv(i) for i in x]
            if is_dataclass(x):
                return ast_node_to_dict(x)
            return x
        return {k: conv(v) for k, v in d.items()}
    # handle lists/tuples/dicts
    if isinstance(node, list):
        return [ast_node_to_dict(n) for n in node]
    if isinstance(node, tuple):
        return tuple(ast_node_to_dict(n) for n in node)
    if isinstance(node, dict):
        return {k: ast_node_to_dict(v) for k, v in node.items()}
    return node


def _group_tokens_by_line(tokens: list[dict], source: Optional[str] = None):
    """Group token dicts by 1-based line number; optionally attach original line text."""
    by_line: dict[int, list[dict]] = {}
    for t in (tokens or []):
        try:
            ln = int(t.get('line') or 0)
        except Exception:
            ln = 0
        if ln <= 0:
            ln = 0
        by_line.setdefault(ln, []).append({
            'type': t.get('type'),
            'value': t.get('value'),
            'col': t.get('col'),
        })

    src_lines = None
    if isinstance(source, str):
        src_lines = source.split('\n')

    out = []
    for ln in sorted(by_line.keys()):
        item = {'line': ln, 'tokens': by_line[ln]}
        if src_lines is not None and ln >= 1 and ln - 1 < len(src_lines):
            item['text'] = src_lines[ln - 1]
        out.append(item)
    return out


def _ir_lines_from_code(code: Optional[list[dict]]):
    """Render IR/instructions to aligned human-readable lines."""
    if not code:
        return []
    lines: list[str] = []
    for i, ins in enumerate(code):
        op = ins.get('op')
        l = ins.get('l')
        a = ins.get('a')
        lines.append(f"{i:04d} {op} {l} {a}")
    return lines


def _build_stats(source: str, tokens: Optional[list[dict]], code: Optional[list[dict]], res: dict):
    src = source or ''
    src_lines = src.split('\n')
    token_total = len(tokens or [])
    by_type: dict[str, int] = {}
    for t in (tokens or []):
        tt = str(t.get('type'))
        by_type[tt] = by_type.get(tt, 0) + 1

    instr_total = len(code or [])
    by_op: dict[str, int] = {}
    for ins in (code or []):
        op = str(ins.get('op'))
        by_op[op] = by_op.get(op, 0) + 1

    lex_n = len(res.get('lexer_errors') or [])
    parse_n = len(res.get('parser_errors') or [])
    sem_n = len(res.get('semantic_errors') or [])
    internal_n = 1 if res.get('error') and (res.get('error') or {}).get('type') in ('internal', 'runtime') else 0

    stats = {
        'source': {
            'line_count': len(src_lines) if src else 0,
            'char_count': len(src),
            'nonempty_line_count': sum(1 for ln in src_lines if ln.strip()) if src else 0,
            'max_line_length': max((len(ln) for ln in src_lines), default=0) if src else 0,
        },
        'tokens': {
            'total': token_total,
            'by_type': by_type,
            'unique_types': len(by_type),
        },
        'ir': {
            'instr_count': instr_total,
            'by_op': by_op,
            'unique_ops': len(by_op),
        },
        'diagnostics': {
            'total': lex_n + parse_n + sem_n + internal_n,
            'lexer': lex_n,
            'parser': parse_n,
            'semantic': sem_n,
            'internal_or_runtime': internal_n,
        },
    }
    return stats


def _format_ir(code: list[tuple[str,int,int]]) -> list[str]:
    return [f"{i:04d} {op} {l} {a}" for i, (op, l, a) in enumerate(code or [])]


def _label_for_instr(ins: tuple[str,int,int]) -> str:
    op, l, a = ins
    return f"{op} {l} {a}"


def _compute_optimizer_viz(before: list[tuple[str,int,int]], after: list[tuple[str,int,int]]) -> dict:
    """Best-effort optimizer visualization.

    We don't attempt perfect instruction identity tracking (hard without debug IDs).
    Instead we provide:
    - before/after IR listings
    - counts of length change
    - jump target changes summary
    - a per-index diff (same index) annotated as add/del/chg

    This is stable/robust and easy to understand.
    """
    bef = before or []
    aft = after or []

    before_lines = _format_ir(bef)
    after_lines = _format_ir(aft)

    # jump target change summary (by index, if both sides have instruction at index)
    jump_changes = []
    n = min(len(bef), len(aft))
    for i in range(n):
        op0, l0, a0 = bef[i]
        op1, l1, a1 = aft[i]
        if op0 in ('JMP','JPC') and op1 == op0 and l0 == l1 and a0 != a1:
            jump_changes.append(f"{i:04d}: {op0} target {a0} -> {a1}")

    # per-index diff
    diff_lines: list[dict] = []
    m = max(len(bef), len(aft))
    for i in range(m):
        b = bef[i] if i < len(bef) else None
        a = aft[i] if i < len(aft) else None
        if b is None and a is not None:
            diff_lines.append({'kind':'add','text': f"{i:04d} {_label_for_instr(a)}"})
        elif a is None and b is not None:
            diff_lines.append({'kind':'del','text': f"{i:04d} {_label_for_instr(b)}"})
        elif a is not None and b is not None:
            if a == b:
                continue
            diff_lines.append({'kind':'chg','text': f"{i:04d} {_label_for_instr(b)}   =>   {_label_for_instr(a)}"})

    summary_parts = [
        f"IR length: {len(bef)} -> {len(aft)}",
    ]
    if jump_changes:
        summary_parts.append(f"jump remap: {len(jump_changes)} change(s)")

    # Explain which optimizer passes may have triggered:
    notes = [
        "可能的优化步骤：",
        "1) 跳转穿透（jump-threading）：JMP/JPC 目标若落在 JMP 链上，则直接改写到最终落点。",
        "2) 小范围常量折叠（constant folding）：仅在 LIT/LIT/OPR 紧邻时才折叠（不改变 I/O）。",
        "3) 不可达代码删除（DCE）：删除从入口永远到达不了的指令，并重映射跳转目标。",
        "说明：地址变化大多数来自 DCE 的重排/重映射，不代表语义改变。",
    ]

    return {
        'header': 'Optimizer visualization',
        'summary': "\n".join(summary_parts + ([""] + jump_changes if jump_changes else []) + ([""] + notes)),
        'diff_lines': diff_lines[:400],
        'before': before_lines[:400],
        'after': after_lines[:400],
    }


def process_source(source: str, inputs=None, auto_recover: bool = True, enable_opt: bool = True, diag_v2: bool = True,
                   view_mode: str = 'structured', include_stats: bool = False,
                   compile_mode: str = 'classic', show_opt_viz: bool = False,
                   include_vm_trace: bool = False, include_symtab: bool = False):
    """Tokenize, parse, semantic analyze, generate code, run VM.

    compile_mode:
      - 'classic': current behavior (allows auto_recover, etc.)
      - 'strict': one-pass style (parser-driven, no recovery); only run VM if fully clean.

    Note: all other toggles (typo fix, optimizer, diagnostics v2, views, stats...) are optional and available in both modes.
    """
    # --- timing (used by meta.total_time_ms) ---
    start_t = time.perf_counter()

    result = {
        'tokens': None,
        'ast': None,
        'code': None,
        'output': None,
        'error': None,           # 兼容旧客户端：首个错误
        'lexer_errors': [],
        'parser_errors': [],
        'semantic_errors': [],
        # meta: explain which options actually took effect (important when 'strict' forces some behaviors)
        'meta': {
            'compile_mode': None,
            'requested_options': {
                'auto_recover': bool(auto_recover),
                'enable_opt': bool(enable_opt),
                'diag_v2': bool(diag_v2),
                'view_mode': view_mode,
                'include_stats': bool(include_stats),
            },
            'effective_options': {},
            'notes': [],
        }
    }

    # optional view-model fields (only populated when requested)
    if view_mode in ('flat', 'line'):
        result['tokens_view'] = None
        result['ir_view'] = None
    if include_stats:
        result['stats'] = None
    if show_opt_viz:
        result['opt_viz'] = None
    if include_vm_trace:
        result['vm_trace'] = None
    if include_symtab:
        result['symtab'] = None

    mode = (compile_mode or 'classic').lower().strip()
    if mode not in ('classic', 'strict'):
        mode = 'classic'

    # Compute effective options.
    eff_auto_recover = bool(auto_recover)
    if mode == 'strict':
        # Strict mode = parser-driven, no recovery.
        if eff_auto_recover:
            result['meta']['notes'].append("strict 模式下禁用自动恢复（auto_recover 将被忽略）")
        eff_auto_recover = False

    result['meta']['compile_mode'] = mode
    result['meta']['effective_options'] = {
        'auto_recover': eff_auto_recover,
        'enable_opt': bool(enable_opt),
        'diag_v2': bool(diag_v2),
        'view_mode': view_mode,
        'include_stats': bool(include_stats),
    }

    try:
        # --- Phase 1: lex (always) ---
        toks, lex_errs = tokenize_with_errors(source)
        result['tokens'] = [{'type': t.type, 'value': t.value, 'line': t.line, 'col': t.col} for t in toks]
        result['lexer_errors'] = [e.to_dict(source) for e in lex_errs]
        if not diag_v2:
            # best-effort: strip v2-only fields for legacy mode
            for e in result['lexer_errors']:
                for k in ('code','severity','end_line','end_col','notes','auto_recovered'):
                    e.pop(k, None)

        # strict: if lexer has errors, stop further phases (真实编译器：词法错误通常阻断语法)
        if mode == 'strict' and result['lexer_errors']:
            result['error'] = result['lexer_errors'][0]
        else:
            # --- Phase 2: parse ---
            # strict: forbid auto recovery to keep one-pass/standard behavior
            parse_auto = eff_auto_recover
            prog, parse_errs = parse_tokens_with_errors(
                toks,
                source,
                auto_recover=parse_auto,
                strict_bnf=(mode == 'strict')
            )
            result['parser_errors'] = parse_errs
            if not diag_v2:
                for e in result['parser_errors']:
                    for k in ('code','severity','end_line','end_col','notes'):
                        e.pop(k, None)

            # --- Phase 3: semantic ---
            if prog is not None:
                try:
                    from semantic import analyze
                    # strict: do semantic only if parse has no errors
                    if mode == 'strict' and result['parser_errors']:
                        result['semantic_errors'] = []
                    else:
                        sem_errs = analyze(prog, source=source, fold_consts=True)
                        result['semantic_errors'] = sem_errs
                        if sem_errs and result['error'] is None:
                            result['error'] = sem_errs[0]
                except Exception as e:
                    # semantic internal error
                    result['semantic_errors'] = [{'type':'semantic','message':f'语义分析器内部错误: {e}'}]
                    if result['error'] is None:
                        result['error'] = result['semantic_errors'][0]

            # pick first error for legacy field
            if result['error'] is None:
                if result['lexer_errors']:
                    result['error'] = result['lexer_errors'][0]
                elif result['parser_errors']:
                    result['error'] = result['parser_errors'][0]
                elif result['semantic_errors']:
                    result['error'] = result['semantic_errors'][0]

            # --- Phase 4: codegen + run ---
            can_codegen = (prog is not None) and (not result['parser_errors']) and (not result['semantic_errors']) and (not result['lexer_errors'])
            if can_codegen:
                result['ast'] = ast_node_to_dict(prog)

                # --- Symbol table export (read-only) ---
                debug_vars = None
                if include_symtab:
                    try:
                        from symtable import build_symtable_tree
                        root_st = getattr(prog.block, 'symtable', None)
                        st_tree = build_symtable_tree(root_st)
                        result['symtab'] = st_tree

                        # Build a lightweight debug mapping: addr -> name per scope.
                        # NOTE: In this project, variable addresses (addr) are assigned during codegen.
                        # So the symtab exported at this point may not contain addr (often None).
                        # We therefore provide reliable fallbacks based on AST declaration order:
                        # - For a block: params are at addr=3.., then locals follow.
                        scopes = []

                        def _add_scope(level, names_by_addr):
                            scopes.append({'level': level, 'names_by_addr': names_by_addr})

                        def walk(st_dict: dict):
                            if not isinstance(st_dict, dict):
                                return
                            lvl = st_dict.get('level')
                            names_by_addr = {}
                            for s in (st_dict.get('symbols') or []):
                                try:
                                    if s.get('kind') == 'var' and s.get('addr') is not None:
                                        names_by_addr[str(int(s.get('addr')))] = s.get('name')
                                except Exception:
                                    continue
                            _add_scope(lvl, names_by_addr)
                            for ch in (st_dict.get('children') or []):
                                walk(ch)

                        walk(st_tree or {})

                        # ---------- AST-based fallback addr maps (covers main + nested procs) ----------
                        VAR_OFFSET = 3

                        def add_fallback_for_block(level, params, vars_):
                            if level is None:
                                return
                            nba = {}
                            off = VAR_OFFSET
                            for p in (params or []):
                                nba[str(off)] = str(p)
                                off += 1
                            for v in (vars_ or []):
                                nba[str(off)] = str(v)
                                off += 1
                            if nba:
                                scopes.insert(0, {'level': int(level), 'names_by_addr': nba})

                        # main block
                        try:
                            main_lvl = st_tree.get('level') if isinstance(st_tree, dict) else None
                            main_vars = list(getattr(prog.block, 'vars') or [])
                            add_fallback_for_block(main_lvl, [], main_vars)
                        except Exception:
                            pass

                        # nested procedures: recurse AST blocks with explicit level
                        def walk_proc_ast(proc_node, level: int):
                            try:
                                params = list(getattr(proc_node, 'params') or [])
                                vars_ = list(getattr(proc_node.block, 'vars') or [])
                                add_fallback_for_block(level, params, vars_)
                                for child in list(getattr(proc_node.block, 'procs') or []):
                                    walk_proc_ast(child, level + 1)
                            except Exception:
                                return

                        try:
                            base_lvl = st_tree.get('level') if isinstance(st_tree, dict) else 1
                            for p in list(getattr(prog.block, 'procs') or []):
                                walk_proc_ast(p, int(base_lvl) + 1)
                        except Exception:
                            pass

                        debug_vars = {'scopes': scopes}
                    except Exception:
                        result['symtab'] = None
                        debug_vars = None

                cg = CodeGenerator()
                code = cg.generate(prog)

                # Attach debug metadata for VM trace (lexical level by entry address)
                try:
                    if debug_vars is not None and hasattr(cg, 'op_level'):
                        debug_vars['op_level'] = {int(k): int(v) for k, v in (cg.op_level or {}).items()}
                except Exception:
                    pass

                before_opt = None
                if enable_opt and show_opt_viz:
                    before_opt = list(code)

                # optimizer stage (low-risk peephole)
                try:
                    from optimizer import peephole
                    if enable_opt:
                        code = peephole(code)
                except Exception:
                    pass

                if enable_opt and show_opt_viz and before_opt is not None:
                    try:
                        result['opt_viz'] = _compute_optimizer_viz(before_opt, list(code))
                    except Exception:
                        result['opt_viz'] = None

                result['code'] = [{'op': op, 'l': l, 'a': a} for (op, l, a) in (code or [])]

                # runtime is only auto-executed in strict when fully clean (already ensured)
                red_count = sum(1 for (op, l, a) in (code or []) if op == 'RED')
                provided_inputs = inputs or []
                if red_count > 0 and len(provided_inputs) < red_count:
                    err = {
                        'type': 'runtime',
                        'code': 'RUN_INPUT_ARITY',
                        'severity': 'error',
                        'message': f"程序需要 {red_count} 个输入，但只提供了 {len(provided_inputs)} 个；请在输入栏按逗号分隔提供所有输入（例如：3,5）。",
                        'line': None,
                        'col': None,
                        'end_line': None,
                        'end_col': None,
                        'notes': [f"needed={red_count}", f"provided={len(provided_inputs)}"],
                        'auto_recovered': False,
                    }
                    if not diag_v2:
                        for k in ('code', 'severity', 'end_line', 'end_col', 'notes', 'auto_recovered'):
                            err.pop(k, None)
                    result['error'] = err
                    return result

                vm = VM(code, provided_inputs, debug_vars=debug_vars)
                if include_vm_trace:
                    out, trace_data = vm.run_with_trace()
                    result['output'] = out
                    result['vm_trace'] = {
                        'step_count': len(trace_data or []),
                        'steps': (trace_data or [])[:2000],
                        'note': 'steps 截断上限=2000（避免代码很长导致响应过大）'
                    }
                else:
                    out = vm.run()
                    result['output'] = out

    except Exception as e:
        tb = traceback.format_exc()
        err = {
            'type': 'internal',
            'code': 'INT001',
            'severity': 'error',
            'message': str(e),
            'traceback': tb,
            'line': None,
            'col': None,
            'end_line': None,
            'end_col': None,
            'notes': [],
            'auto_recovered': False,
        }
        if not diag_v2:
            for k in ('code', 'severity', 'end_line', 'end_col', 'notes', 'auto_recovered'):
                err.pop(k, None)
        result['error'] = err

    # --- timing ---
    end_t = time.perf_counter()
    try:
        result['meta']['total_time_ms'] = (end_t - start_t) * 1000
    except Exception:
        pass

    # attach view-models/statistics at the end to ensure they reflect final result
    if view_mode in ('flat', 'line'):
        tv = {'mode': view_mode}
        if view_mode == 'flat':
            tv['flat'] = result.get('tokens')
        else:
            tv['by_line'] = _group_tokens_by_line(result.get('tokens') or [], source)
        result['tokens_view'] = tv

        result['ir_view'] = {
            'lines': _ir_lines_from_code(result.get('code'))
        }

    if include_stats:
        try:
            result['stats'] = _build_stats(source, result.get('tokens'), result.get('code'), result)
        except Exception:
            result['stats'] = None

    return result


@app.route('/')
def index():
    return render_template('index.html')


@app.route('/api/compile', methods=['POST'])
def api_compile():
    data = request.get_json(force=True)
    source = data.get('source', '')
    inputs = data.get('inputs', [])

    res = process_source(
        source,
        inputs,
        auto_recover=data.get('auto_recover', True),
        enable_opt=data.get('enable_opt', True),
        diag_v2=data.get('diag_v2', True),
        view_mode=data.get('view_mode', 'structured'),
        include_stats=bool(data.get('include_stats', False)),
        compile_mode=data.get('compile_mode', 'classic'),
        show_opt_viz=bool(data.get('show_opt_viz', False)),
        include_vm_trace=bool(data.get('include_vm_trace', False)),
        include_symtab=bool(data.get('include_symtab', False)),
    )
    return jsonify(res)


if __name__ == '__main__':
    app.run(debug=True)
