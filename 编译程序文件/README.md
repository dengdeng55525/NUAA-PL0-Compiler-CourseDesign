# PL/0 编译器
丁俊泽

这是我的编译原理课程设计，一个用 Python 实现的 PL/0 小型编译器项目：

- 前端：Lexer（分词）→ Parser（语法分析）→ Semantic（语义分析）
- 后端：CodeGen（生成栈机 IR）→ Optimizer（低风险 peephole）→ VM（解释执行）
- 附加：Web 前端可以在浏览器里查看 tokens / AST / IR / 运行输出 / 错误信息，并支持部分自动修复（如关键字拼写纠错）。

> 说明：本项目为了避免与 Python 标准库同名模块 `parser` 冲突，`main_cli.py` 与 `web/app.py` 里使用了 `importlib` 显式加载本地 `parser.py`。

## 目录结构（简要）

- `lexer.py`：词法分析
- `parser.py`：语法分析（含错误恢复/严格模式相关逻辑）
- `semantic.py`/`symtable.py`：语义分析与符号表
- `codegen.py`：生成栈机指令（IR）
- `optimizer.py`：低风险 peephole 优化（保证语义不变，尤其不改变 I/O 顺序）
- `vm.py`：PL/0 栈式虚拟机
- `main_cli.py`：命令行编译+运行入口
- `examples/`：示例 PL/0 程序
- `tests/`：pytest 测试
- `scripts/`：辅助脚本（调试/复现/验证流水线）
- `web/`：Flask Web 前端（模板/静态资源/接口）

## 环境要求

- Python 3.10+（建议 3.11/3.12 也可）
- Windows / macOS / Linux 均可（仓库内提供了 Windows PowerShell 的一键脚本）

## 安装

### 1) CLI / 测试（根项目）

根目录代码本身不依赖第三方库；如果你只需要 CLI 编译运行，可以直接使用 Python。

如果你需要跑测试，请安装根目录的测试依赖：

```powershell
py -3 -m pip install -r requirements.txt
```

### 2) Web 前端（Flask）

Web 依赖单独放在 `web/requirements.txt`：

```powershell
py -3 -m pip install -r web/requirements.txt
```

## CLI 使用方法

### 1) 直接运行 `main_cli.py`

```powershell
py -3 main_cli.py examples\sum.pl0
```

`main_cli.compile_and_run(source, inputs)` 会返回 VM 的输出列表（对应 `write(...)` 输出的值）。

### 2) 使用脚本 `scripts/run_src.py`

这个脚本会把输出打印出来，适合快速 smoke test：

```powershell
py -3 scripts\run_src.py examples\sum.pl0
```

### 3) 验证“优化器不改变语义”

```powershell
py -3 scripts\verify_full_compile_pipeline.py
```

该脚本会分别在“关闭优化/开启优化”两种情况下编译并运行同一段程序，断言输出一致。

## Web 前端使用方法

### 方式 A：直接运行

```powershell
py -3 -m pip install -r web/requirements.txt
py -3 web\app.py
```

然后打开： http://127.0.0.1:5000

### 方式 B：Windows 一键启动（推荐）

```powershell
powershell -ExecutionPolicy Bypass -File scripts\run_web.ps1
```

### 关键字拼写纠错白名单

- 文件：`web/static/typo_whitelist.txt`
- 修改后刷新网页即可生效（前端会重新拉取该文件）

## 运行示例

- `examples/sum.pl0`：读入两个数并输出和
- `examples/param_passing_demo.pl0`：过程/参数传递示例
- `examples/nested2.pl0`：嵌套过程与静态链相关示例

## 测试

使用 pytest：

```powershell
py -3 -m pytest -q
```

如遇到导入路径问题：确保命令在项目根目录执行。
