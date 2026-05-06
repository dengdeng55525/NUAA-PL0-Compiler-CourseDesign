"""Quick repro: compare classic vs strict compile modes in the web backend pipeline.

Run this script with the project root as cwd.
It loads web/app.py and calls process_source directly (no server needed).
"""

from __future__ import annotations

import importlib.util
import os

ROOT = os.path.dirname(os.path.dirname(__file__))
APP_PATH = os.path.join(ROOT, "web", "app.py")

_spec = importlib.util.spec_from_file_location("web_app", APP_PATH)
_web_app = importlib.util.module_from_spec(_spec)
assert _spec and _spec.loader
_spec.loader.exec_module(_web_app)

process_source = getattr(_web_app, "process_source")

SRC = """program p;
var x;
begin
  if x > 0 the
    write(x)
end
"""


def main() -> None:
    for mode in ("classic", "strict"):
        res = process_source(
            SRC,
            inputs=[],
            auto_recover=True,  # user requests it
            enable_opt=True,
            diag_v2=True,
            view_mode="structured",
            include_stats=True,
            compile_mode=mode,
        )
        meta = res.get("meta")
        print("=" * 80)
        print("mode:", mode)
        print("meta:", meta)
        print("lexer_errors:", len(res.get("lexer_errors") or []))
        print("parser_errors:", len(res.get("parser_errors") or []))
        print("semantic_errors:", len(res.get("semantic_errors") or []))
        print("has code:", bool(res.get("code")))
        print("has output:", bool(res.get("output")))


if __name__ == "__main__":
    main()
