"""\
用 HTTP 直接调用 /api/compile 验证 vm_trace 是否返回（不依赖浏览器）。

运行：
  python scripts\repro_web_vmtrace_request.py

注意：
- 需要先启动 web/app.py（http://127.0.0.1:5000）。
"""

from __future__ import annotations

import json
import urllib.request

SRC = """program sum;
var x,y;
begin
  read(x,y);
  x := x + y;
  write(x)
end
"""


def post(payload: dict) -> dict:
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        "http://127.0.0.1:5000/api/compile",
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=5) as resp:
        return json.loads(resp.read().decode("utf-8"))


def main():
    res = post({
        "source": SRC,
        "inputs": [3, 5],
        "auto_recover": True,
        "enable_opt": True,
        "diag_v2": True,
        "show_opt_viz": True,
        "compile_mode": "classic",
        "view_mode": "structured",
        "include_stats": True,
        "include_symtab": True,
        "include_vm_trace": True,
    })

    assert "vm_trace" in res, "missing vm_trace field"
    vt = res.get("vm_trace")
    assert isinstance(vt, dict) and "steps" in vt, f"bad vm_trace: {type(vt)}"
    print("vm_trace.step_count:", vt.get("step_count"))
    print("first step keys:", list((vt.get("steps") or [{}])[0].keys()))


if __name__ == "__main__":
    main()
