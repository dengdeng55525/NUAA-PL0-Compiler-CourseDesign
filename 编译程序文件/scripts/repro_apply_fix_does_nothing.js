/**
 * 用法：
 * 1) 启动 web 服务：python web/app.py
 * 2) 打开浏览器： http://127.0.0.1:5000
 * 3) 打开 DevTools Console，把本文件内容粘贴运行
 *
 * 目的：验证“应用修复”按钮对应的 applyAutoFix 逻辑在前端不再静默失败。
 */

(function () {
  const src = `program p;
const
  a = 1;
var x;
begin
  x := a;
  write(x)
end`;

  const ta = document.getElementById('source');
  if (!ta) throw new Error('textarea#source not found');
  ta.value = src;

  // 触发一次编译
  const runBtn = document.getElementById('run');
  if (!runBtn) throw new Error('#run not found');
  runBtn.click();

  console.log('[repro] triggered compile. Now click “应用修复” on PAR_CONST_REQUIRES_ASSIGN, it should replace = -> :=');
})();
