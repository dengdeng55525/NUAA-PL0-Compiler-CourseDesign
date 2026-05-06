import sys
import os
from lexer import tokenize
import importlib.util

## ==============================
## 命令行入口（CLI）
## ==============================
##
## 作用：
## - 提供一个最小的“编译 + 解释执行”入口，便于脱离 Web 前端验证整个流水线。
##
## 编译流水线（与 web/app.py 类似，但输出方式更偏 CLI）：
##   源码 -> Lexer(tokenize)
##       -> Parser(parse_tokens)
##       -> Semantic(analyze)
##       -> CodeGen(generate)
##       -> Optimizer(peephole) [可选]
##       -> VM.run() 解释执行
##
## 注意：
## - Python 标准库中也存在同名模块 parser。
##   为避免冲突，这里用 importlib 显式加载本目录下的 parser.py。

# Explicitly load local parser.py to avoid clashing with stdlib 'parser'
# 显式加载本地 parser.py，避免与 Python 自带模块 parser 冲突
parser_path = os.path.join(os.path.dirname(__file__), 'parser.py')
spec = importlib.util.spec_from_file_location('user_parser', parser_path)
_mod = importlib.util.module_from_spec(spec)
assert spec and spec.loader
spec.loader.exec_module(_mod)
parse_tokens = getattr(_mod, 'parse_tokens')  # type: ignore

from codegen import CodeGenerator
from vm import VM
from semantic import analyze
from optimizer import peephole


def compile_and_run(source: str, inputs=None, *, fold_consts: bool = True, optimize: bool = True):
    """编译并运行一段 PL/0 源码。

    参数：
    - source: 源码字符串
    - inputs: 输入整数列表（RED 指令按顺序消耗）
    - fold_consts: 语义阶段是否把 const 引用折叠为数字字面量
    - optimize: 是否启用 peephole 优化器

    返回：
    - out: VM 输出列表（write 打印过的值）

    说明：
    - CLI 里语义错误会抛异常（只抛第一个），便于快速定位。
      Web 版本则会结构化输出所有 diagnostics。
    """
    tokens = tokenize(source)
    program = parse_tokens(tokens)

    # semantic analysis (like a real compiler)
    sem_errs = analyze(program, source=source, fold_consts=fold_consts)
    if sem_errs:
        # raise the first semantic error for CLI usage
        raise RuntimeError(sem_errs[0].get('message'))

    cg = CodeGenerator()
    code = cg.generate(program)
    if optimize:
        code = peephole(code)

    vm = VM(code, inputs or [])
    out = vm.run()
    return out

if __name__ == '__main__':
    if len(sys.argv) < 2:
        print('Usage: python main_cli.py <source.pl0>')
        sys.exit(1)
    path = sys.argv[1]
    with open(path, 'r', encoding='utf-8') as f:
        src = f.read()
    compile_and_run(src)
