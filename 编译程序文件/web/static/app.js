const KEYWORDS = ['program','const','var','procedure','begin','end','if','then','else','while','do','call','read','write','odd'];

const sourceTA = document.getElementById('source');
const highlightPre = document.getElementById('highlight');

// ---- theme + import wiring ----
function applyTheme(theme){
  document.body.dataset.theme = theme;
  try{ localStorage.setItem('theme', theme); }catch(e){}
  const btn = document.getElementById('theme_toggle');
  if(btn){
    btn.textContent = (theme === 'dark') ? '代码框亮色' : '代码框暗色';
  }
}

(function initTheme(){
  let theme = 'dark';
  try{
    const saved = localStorage.getItem('theme');
    if(saved === 'dark' || saved === 'light') theme = saved;
  }catch(e){}
  applyTheme(theme);
})();

const themeToggleBtn = document.getElementById('theme_toggle');
if(themeToggleBtn){
  themeToggleBtn.addEventListener('click', ()=>{
    const cur = document.body.dataset.theme || 'light';
    applyTheme(cur === 'dark' ? 'light' : 'dark');
  });
}

const fileInput = document.getElementById('file_pl0');
const importBtn = document.getElementById('import_pl0');
if(importBtn && fileInput){
  importBtn.addEventListener('click', ()=> fileInput.click());
  fileInput.addEventListener('change', async ()=>{
    const f = fileInput.files && fileInput.files[0];
    if(!f) return;
    const text = await f.text();
    sourceTA.value = text.replace(/\r\n/g,'\n');
    syncHighlight();
    // auto run after import (small delay to let UI paint)
    setTimeout(()=>{
      const runBtn = document.getElementById('run');
      if(runBtn) runBtn.click();
    }, 50);
    // allow importing the same file again
    fileInput.value = '';
  });
}

function escapeHtml(s){
  return s.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
}

// 构建高亮 DOM，不使用 innerHTML
function buildHighlightDOM(text, errorIntervals){
  // errorIntervals: array of [startPos, endPos) absolute indices
  highlightPre.innerHTML = '';
  const re = /(\r\n|\n)|(\b\d+\b)|(\b[a-zA-Z][a-zA-Z0-9]*\b)|(:=|<>|<=|>=|[+\-*\/=<>;,\.:\(\)])/g;
  let lastIndex = 0;
  let m;
  while((m = re.exec(text)) !== null){
    const idx = m.index;
    if(idx > lastIndex){
      const between = text.slice(lastIndex, idx);
      highlightPre.appendChild(document.createTextNode(between));
    }
    const tok = m[0];
    const node = document.createElement('span');
    node.textContent = tok;
    // determine class
    if(m[1]){ // newline
      highlightPre.appendChild(document.createTextNode(tok));
      lastIndex = re.lastIndex;
      continue;
    } else if(m[2]){ // number
      node.className = 'num';
    } else if(m[3]){ // identifier or keyword
      const low = tok.toLowerCase();
      if(KEYWORDS.includes(low)) node.className = 'kw'; else node.className = 'id';
    } else if(m[4]){ // operator
      node.className = 'op';
    }
    // check overlap with error intervals
    const startPos = idx;
    const endPos = idx + tok.length;
    let isErr = false;
    if(Array.isArray(errorIntervals)){
      for(const it of errorIntervals){
        if(it[0] < endPos && startPos < it[1]){ isErr = true; break; }
      }
    }
    if(isErr) node.classList.add('errtoken');
    highlightPre.appendChild(node);
    lastIndex = re.lastIndex;
  }
  if(lastIndex < text.length){
    highlightPre.appendChild(document.createTextNode(text.slice(lastIndex)));
  }
}

function computeErrorIntervals(errors){
  if(!errors) return [];
  const intervals = [];
  const lines = sourceTA.value.split('\n');
  for(const err of errors){
    if(!err.line || !err.col) continue;
    let pos = 0;
    for(let i=0;i<err.line-1 && i<lines.length;i++) pos += lines[i].length + 1;
    const col0 = Math.max(0, err.col-1);
    let length = 1;
    if(err.token_value) length = String(err.token_value).length;
    if(err.snippet && typeof err.caret === 'number'){
      // try to highlight the token around caret
      length = 1;
    }
    intervals.push([pos + col0, pos + col0 + length]);
  }
  return intervals;
}

function syncHighlight(){
  const val = sourceTA.value;
  buildHighlightDOM(val, []);
}

// sync scroll positions (keep highlight exactly aligned with textarea)
sourceTA.addEventListener('scroll', ()=>{
  highlightPre.scrollTop = sourceTA.scrollTop;
  highlightPre.scrollLeft = sourceTA.scrollLeft;
});
sourceTA.addEventListener('input', ()=>{
  syncHighlight();
});
// init
syncHighlight();

// hide undo by default
const undoBtn = document.getElementById('undo_fix');
if(undoBtn){
  undoBtn.style.display = 'none';
}

// compile/run logic
// Parse input numbers, accepting both half-width ',' and full-width '，'
function parseInputs(raw){
  const s0 = (raw || '').trim();
  if(!s0) return [];
  // Accept both half-width ',' and full-width '，'
  const s = s0.replace(/，/g, ',');
  return s
    .split(',')
    .map(x => x.trim())
    .filter(x => x.length > 0)
    .map(x => {
      // allow leading +/-, and ignore surrounding spaces
      const n = Number(x);
      return Number.isFinite(n) && Number.isInteger(n) ? n : null;
    })
    .filter(x => x !== null);
}

document.getElementById('run').addEventListener('click', async ()=>{
  const source = sourceTA.value;
  const inputsRaw = document.getElementById('inputs').value;
  const inputs = parseInputs(inputsRaw);

  const compileModeSel = document.getElementById('compile_mode');
  const compile_mode = compileModeSel ? compileModeSel.value : 'classic';

  const autoRecoverCheckbox = document.getElementById('auto_recover');
  const auto_recover = !!(autoRecoverCheckbox && autoRecoverCheckbox.checked);

  const enableOptCheckbox = document.getElementById('enable_opt');
  const enable_opt = !!(enableOptCheckbox && enableOptCheckbox.checked);

  const showOptVizCb = document.getElementById('show_opt_viz');
  const show_opt_viz = !!(showOptVizCb && showOptVizCb.checked);

  const diagV2Checkbox = document.getElementById('diag_v2');
  const diag_v2 = !!(diagV2Checkbox && diagV2Checkbox.checked);

  const outputViewSel = document.getElementById('output_view');
  const view_mode = outputViewSel ? outputViewSel.value : 'structured';
  const includeStatsCb = document.getElementById('include_stats');
  const include_stats = !!(includeStatsCb && includeStatsCb.checked);

  const includeSymtabCb = document.getElementById('include_symtab');
  const include_symtab = !!(includeSymtabCb && includeSymtabCb.checked);

  const includeVMTraceCb = document.getElementById('include_vm_trace');
  const include_vm_trace = !!(includeVMTraceCb && includeVMTraceCb.checked);

  // clear
  document.getElementById('err_list').textContent = '';
  document.getElementById('tokens').textContent = '';
  document.getElementById('ast').textContent = '';
  document.getElementById('code').textContent = '';
  document.getElementById('output').textContent = '';
  document.getElementById('trace').textContent = '';

  const statsNode = document.getElementById('stats');
  if(statsNode) statsNode.textContent = '';
  const optvizNode = document.getElementById('optviz');
  if(optvizNode) optvizNode.textContent = '';
  const symtabNode = document.getElementById('symtab');
  if(symtabNode) symtabNode.textContent = '';
  const vmtraceNode = document.getElementById('vmtrace');
  if(vmtraceNode) vmtraceNode.textContent = '';

  try{
    const resp = await fetch('/api/compile',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({
      source,inputs,auto_recover,enable_opt,diag_v2,
      show_opt_viz,
      compile_mode,
      view_mode, include_stats,
      include_symtab,
      include_vm_trace,
    })});
    const js = await resp.json();
    renderErrors(js, source);
    document.getElementById('trace').textContent = js.error && js.error.traceback ? js.error.traceback : '';

    renderOutputs(js, {view_mode, include_stats, show_opt_viz, include_symtab, include_vm_trace});

    // mark error tokens in highlight if any
    const allErrors = [];
    if(js.lexer_errors) allErrors.push(...js.lexer_errors);
    if(js.parser_errors) allErrors.push(...js.parser_errors);
    const intervals = computeErrorIntervals(allErrors);
    buildHighlightDOM(source, intervals);

  }catch(e){
    document.getElementById('err_list').textContent = e.toString();
  }
});

function renderOutputs(js, opts){
  const view_mode = (opts && opts.view_mode) ? opts.view_mode : 'structured';
  const include_stats = !!(opts && opts.include_stats);
  const show_opt_viz = !!(opts && opts.show_opt_viz);
  const include_symtab = !!(opts && opts.include_symtab);
  const include_vm_trace = !!(opts && opts.include_vm_trace);

  // stats
  const statsNode = document.getElementById('stats');
  if(statsNode){
    if(include_stats && js.stats){
      statsNode.textContent = JSON.stringify(js.stats, null, 2);
    }else{
      statsNode.textContent = '';
    }
  }

  // tokens
  const tokensNode = document.getElementById('tokens');
  if(tokensNode){
    if(view_mode === 'structured'){
      tokensNode.textContent = JSON.stringify(js.tokens, null, 2);
    }else if(view_mode === 'flat'){
      const toks = (js.tokens_view && js.tokens_view.flat) ? js.tokens_view.flat : (js.tokens || []);
      tokensNode.textContent = (toks || []).map(t=>{
        const ty = t.type ?? t['type'];
        const val = t.value ?? t['value'];
        const ln = t.line ?? t['line'];
        const col = t.col ?? t['col'];
        return `${ty}(${val}) @${ln}:${col}`;
      }).join('\n');
    }else if(view_mode === 'line'){
      const byLine = (js.tokens_view && js.tokens_view.by_line) ? js.tokens_view.by_line : [];
      tokensNode.textContent = (byLine || []).map(row=>{
        const ln = row.line;
        const toks = row.tokens || [];
        const text = (typeof row.text === 'string') ? row.text : '';
        const head = text ? `${ln}: ${text}` : `${ln}:`;
        const tail = toks.map(t=>`${t.type}(${t.value})@${t.col}`).join('  ');
        return head + (tail ? `\n    ${tail}` : '');
      }).join('\n');
    }
  }

  // AST
  document.getElementById('ast').textContent = JSON.stringify(js.ast, null, 2);

  // IR/code
  const codeNode = document.getElementById('code');
  if(codeNode){
    if(view_mode === 'structured'){
      codeNode.textContent = JSON.stringify(js.code, null, 2);
    }else{
      const lines = (js.ir_view && Array.isArray(js.ir_view.lines)) ? js.ir_view.lines : [];
      codeNode.textContent = lines.join('\n');
    }
  }

  // runtime output
  document.getElementById('output').textContent = JSON.stringify(js.output, null, 2);

  // optimizer visualization
  const optvizNode = document.getElementById('optviz');
  if(optvizNode){
    if(show_opt_viz && js.opt_viz){
      renderOptimizerViz(optvizNode, js.opt_viz);
    }else{
      optvizNode.textContent = '';
    }
  }

  // symtab
  const symtabNode = document.getElementById('symtab');
  if(symtabNode){
    if(include_symtab && js.symtab){
      symtabNode.textContent = renderSymtabPretty(js.symtab);
    }else{
      symtabNode.textContent = '';
    }
  }

  // vm trace
  const vmtraceNode = document.getElementById('vmtrace');
  if(vmtraceNode){
    if(include_vm_trace && js.vm_trace){
      vmtraceNode.textContent = renderVMTracePretty(js.vm_trace);
    }else{
      vmtraceNode.textContent = '';
    }
  }
}

function renderSymtabPretty(tree){
  // Pretty text format (easy to read): one scope per block with indentation
  const lines = [];
  const walk = (node, indent)=>{
    if(!node) return;
    const lvl = node.level;
    lines.push(`${'  '.repeat(indent)}Scope(level=${lvl})`);

    const syms = Array.isArray(node.symbols) ? node.symbols : [];
    if(syms.length){
      for(const s of syms){
        const name = s.name;
        const kind = s.kind;
        const addr = (typeof s.addr !== 'undefined' && s.addr !== null) ? ` addr=${s.addr}` : '';
        let val = '';
        if(kind === 'const') val = ` value=${s.value}`;
        if(kind === 'proc'){
          if(Array.isArray(s.value)) val = ` params=[${s.value.join(', ')}]`;
        }
        lines.push(`${'  '.repeat(indent+1)}- ${kind} ${name}${addr}${val}`);
      }
    }

    const children = Array.isArray(node.children) ? node.children : [];
    for(const ch of children){
      walk(ch, indent+1);
    }
  };
  walk(tree, 0);
  return lines.join('\n');
}

function renderVMTracePretty(vmtrace){
  const lines = [];

  if(!vmtrace){
    return 'VM Trace: (no data)';
  }
  const steps = Array.isArray(vmtrace.steps) ? vmtrace.steps : [];
  const stepCount = (typeof vmtrace.step_count === 'number') ? vmtrace.step_count : steps.length;

  // 若后端返回了 note/原因，优先展示
  lines.push(`VM Trace: steps=${stepCount}`);
  if(vmtrace.note) lines.push(String(vmtrace.note));

  if(steps.length === 0){
    // 给出“为什么空”的可能原因：
    // - 未勾选 include_vm_trace
    // - 编译未通过（未进入 VM.run）
    // - 或后端截断/禁用
    lines.push('');
    lines.push('（未生成逐步追踪）可能原因：');
    lines.push('1) 你没有勾选“可视化程序栈/静态链（VM Trace）”');
    lines.push('2) 代码存在词法/语法/语义错误，未进入运行阶段');
    lines.push('3) 后端为了性能做了截断/禁用（当前 steps 上限=2000）');
    return lines.join('\n');
  }

  lines.push('');

  const fmtInstr = (ins)=>{
    if(!ins) return '';
    return `${ins.op} ${ins.l} ${ins.a}`;
  };

  for(let i=0;i<steps.length;i++){
    const s = steps[i] || {};
    const ins = s.instr;
    lines.push(`#${i}  PC ${s.pc_before} -> ${s.pc_after}   BP ${s.bp_before} -> ${s.bp_after}   SP ${s.sp_before} -> ${s.sp_after}`);
    lines.push(`     IR: ${fmtInstr(ins)}${s.note ? ('   // ' + s.note) : ''}`);

    // frame header
    const cur = s.frames && s.frames.current ? s.frames.current : null;
    if(cur){
      lines.push(`     AR@B=${cur.B}: DL=${cur.DL} RA=${cur.RA} SL=${cur.SL}`);
    }else{
      lines.push('     AR: (unavailable)');
    }

    // base chain for LOD/STO/RED/CAL
    const bc = s.frames && s.frames.base_chain ? s.frames.base_chain : null;
    if(bc){
      const path = Array.isArray(bc.path) ? bc.path : [];
      lines.push(`     base(L=${bc.L}, B=${bc.start_B}) path: ${path.join(' -> ')}${bc.ok ? '' : '  [BROKEN]'}`);
    }

    // io
    if(s.io){
      if(s.io.kind === 'read'){
        const t = s.io.target;
        lines.push(`     IO: read ${s.io.value}  -> [base=${t.base} + A=${t.A}] (abs=${t.abs})`);
      }else if(s.io.kind === 'write'){
        lines.push(`     IO: write ${s.io.value}`);
      }
    }

    // values view (name->value)
    if(s.values && Array.isArray(s.values.scopes)){
      const scopes = s.values.scopes;
      if(scopes.length){
        lines.push('     Values:');
        for(const sc of scopes){
          const lvl = sc.level;
          const vars = sc.vars || {};
          const names = Object.keys(vars);
          if(names.length === 0) continue;
          const parts = [];
          for(const n of names){
            parts.push(`${n}=${vars[n]}`);
          }
          lines.push(`       (level=${lvl}) ${parts.join('  ')}`);
        }
      }
    }else{
      // 如果用户开启了 VM Trace 但没开启 SymTable，这里给一个“为何看不到变量名”的提示
      // 注意：不强制，因为用户可能只想看栈/静态链。
      // 我们只在第一步提示一次。
      if(i === 0){
        lines.push('     Values: (未启用变量视图；如需显示变量名和值，请同时勾选“显示符号表（SymTable）”)');
      }
    }

    // stack window
    const w = s.stack_window;
    if(w && Array.isArray(w.values)){
      const start = w.start;
      const vals = w.values;
      const pairs = [];
      for(let k=0;k<vals.length;k++){
        pairs.push(`${start + k}:${vals[k]}`);
      }
      lines.push(`     stack[${start}..${start + vals.length - 1}]: ${pairs.join('  ')}`);
    }

    lines.push('');
  }

  return lines.join('\n');
}

// ------------------------------
// Optimizer visualization renderer
// ------------------------------
// 说明：
// - 后端 web/app.py 在 show_opt_viz=true 时会返回 js.opt_viz
// - 该函数负责把 opt_viz 渲染到 <pre id="optviz"> 中
// - 使用 <span> 来做 add/del/chg 的颜色区分（CSS 在 style.css 里）
function renderOptimizerViz(containerPre, viz){
  // containerPre is a <pre> node.
  containerPre.innerHTML = '';

  const addLine = (text, cls)=>{
    const sp = document.createElement('span');
    sp.className = 'optviz__line' + (cls ? (' ' + cls) : '');
    sp.textContent = text;
    containerPre.appendChild(sp);
  };

  const header = viz && viz.header ? String(viz.header) : 'Optimizer';
  addLine('=== ' + header + ' ===', 'optviz__h');

  const summary = viz && viz.summary ? String(viz.summary) : '';
  if(summary){
    addLine(summary, 'optviz__sub');
    addLine('', '');
  }

  // Diff lines
  const lines = (viz && Array.isArray(viz.diff_lines)) ? viz.diff_lines : [];
  if(lines.length){
    for(const row of lines){
      const kind = row.kind;
      const text = String(row.text || '');
      if(kind === 'add') addLine('+ ' + text, 'optviz__add');
      else if(kind === 'del') addLine('- ' + text, 'optviz__del');
      else if(kind === 'chg') addLine('~ ' + text, 'optviz__chg');
      else addLine('  ' + text, '');
    }
  }else{
    addLine('(no optimizer changes)', 'optviz__sub');
  }

  // Optional: show before/after blocks if provided
  const before = viz && Array.isArray(viz.before) ? viz.before : null;
  const after = viz && Array.isArray(viz.after) ? viz.after : null;
  if(before && after){
    addLine('', '');
    addLine('--- BEFORE ---', 'optviz__h');
    for(const ln of before){ addLine(String(ln), ''); }
    addLine('', '');
    addLine('--- AFTER ---', 'optviz__h');
    for(const ln of after){ addLine(String(ln), ''); }
  }
}

// --- diagnostics snippet helpers (required by renderErrors) ---
function getSnippetAndCaret(err, fullSource){
  // Always provide a snippet + caret for consistent UI.
  if(err && typeof err.snippet === 'string'){
    const caret = (typeof err.caret === 'number') ? err.caret : ((err.col ? err.col - 1 : 0));
    return {snippet: err.snippet, caret: Math.max(0, caret)};
  }
  if(!fullSource || !err || !err.line) return {snippet: null, caret: 0};
  const lines = String(fullSource).split('\n');
  const lineIdx = Math.max(0, Math.min(lines.length - 1, (err.line || 1) - 1));
  const lineText = lines[lineIdx] ?? '';
  const caret = Math.max(0, (err.col ? err.col - 1 : 0));
  return {snippet: lineText, caret};
}

function buildSnippetBlock(snippet, caret){
  // Single code block: line + caret indicator (second line) in same <pre>
  const pre = document.createElement('pre');
  const safeSnippet = snippet ?? '';
  const caretPos = Math.max(0, caret || 0);
  let indicator = '';
  for(let i=0;i<caretPos;i++) indicator += (safeSnippet[i]==='\t' ? '\t' : ' ');
  indicator += '^';
  pre.textContent = safeSnippet + '\n' + indicator;
  return pre;
}

// error rendering and goto functions
function renderErrors(js, source){
  const listNode = document.getElementById('err_list');
  listNode.innerHTML = '';

  // --- meta notes / effective options banner ---
  try{
    const meta = js && js.meta;
    const notes = meta && Array.isArray(meta.notes) ? meta.notes : [];
    const effective = meta && meta.effective_options ? meta.effective_options : null;

    if((notes && notes.length) || effective){
      const banner = document.createElement('div');
      banner.className = 'meta_banner';

      if(effective){
        const line = document.createElement('div');
        const mode = meta && meta.compile_mode ? meta.compile_mode : '';
        const parts = [];
        if(mode) parts.push(`mode=${mode}`);
        if(typeof effective.auto_recover === 'boolean') parts.push(`auto_recover=${effective.auto_recover}`);
        if(typeof effective.enable_opt === 'boolean') parts.push(`enable_opt=${effective.enable_opt}`);
        if(typeof effective.diag_v2 === 'boolean') parts.push(`diag_v2=${effective.diag_v2}`);
        if(typeof effective.view_mode === 'string') parts.push(`view_mode=${effective.view_mode}`);
        if(typeof effective.include_stats === 'boolean') parts.push(`include_stats=${effective.include_stats}`);
        line.textContent = `生效选项：${parts.join('  ')}`;
        banner.appendChild(line);
      }

      if(notes && notes.length){
        const ul = document.createElement('ul');
        ul.style.margin = '6px 0 0 18px';
        ul.style.padding = '0';
        for(const n of notes){
          const li = document.createElement('li');
          li.textContent = String(n);
          ul.appendChild(li);
        }
        banner.appendChild(ul);
      }

      listNode.appendChild(banner);
    }
  }catch(e){
    // ignore banner rendering failures
  }

  const makeItem = (err, idx)=>{
    const div = document.createElement('div');
    div.className = 'err_item';

    const hdr = document.createElement('div');
    hdr.textContent = `${idx+1}. [${(err.type||'') .toUpperCase()}] ${err.message}`;
    if(err.auto_recovered){
      const badge = document.createElement('span');
      badge.textContent = '自动恢复';
      badge.className = 'badge auto';
      badge.style.marginLeft = '8px';
      hdr.appendChild(badge);
    }
    div.appendChild(hdr);

    if(err.line && err.col){
      const loc = document.createElement('div');
      loc.textContent = `位置: ${err.line}:${err.col}`;
      div.appendChild(loc);
    }

    // unified snippet block (always 1 pre, not 2)
    const sc = getSnippetAndCaret(err, source);
    if(sc.snippet !== null && typeof sc.snippet !== 'undefined'){
      div.appendChild(buildSnippetBlock(sc.snippet, sc.caret));
    }

    if(err.token_type){
      const tinfo = document.createElement('div');
      tinfo.textContent = `token: ${err.token_type} (${err.token_value})`;
      div.appendChild(tinfo);
    }

    if(err.expected){
      const einfo = document.createElement('div');
      const expText = (typeof err.expected_display !== 'undefined')
        ? err.expected_display.join(', ')
        : (Array.isArray(err.expected) ? err.expected.join(', ') : String(err.expected));
      einfo.textContent = `期望: ${expText}`;
      div.appendChild(einfo);
    }

    // buttons row (kept consistent)
    const actions = document.createElement('div');
    actions.style.marginTop = '8px';
    actions.style.display = 'flex';
    actions.style.gap = '10px';
    actions.style.flexWrap = 'wrap';

    // Only allow applying auto-recover fixes when backend actually ran auto-recover.
    const meta = js && js.meta;
    const eff = meta && meta.effective_options ? meta.effective_options : null;
    const backendAutoRecover = eff && typeof eff.auto_recover === 'boolean' ? eff.auto_recover : true;

    if(err.auto_recovered && backendAutoRecover){
      const fixBtn = document.createElement('button');
      fixBtn.textContent = '应用修复';
      fixBtn.onclick = ()=>{ applyAutoFix(err); };
      actions.appendChild(fixBtn);
    }

    if(err.line && err.col){
      const btn = document.createElement('button');
      btn.textContent = '定位到源码';
      btn.onclick = ()=>{ gotoSourcePosition(err.line, err.col); };
      actions.appendChild(btn);
    }

    if(actions.childNodes.length){
      div.appendChild(actions);
    }

    return div;
  };

  const all = [];
  if(js.lexer_errors && js.lexer_errors.length) all.push(...js.lexer_errors);
  if(js.parser_errors && js.parser_errors.length) all.push(...js.parser_errors);
  if(all.length===0 && js.error){
    all.push(js.error);
  }
  if(all.length===0) return;
  all.forEach((e,i)=> listNode.appendChild(makeItem(e,i)));
}

function gotoSourcePosition(line, col){
  const ta = document.getElementById('source');
  const lines = ta.value.split('\n');
  let pos = 0;
  for(let i=0;i<line-1 && i<lines.length;i++) pos += lines[i].length + 1; // +1 for newline
  pos += Math.max(0, col-1);
  ta.focus();
  ta.setSelectionRange(pos, pos+1);
}

// global last fix storage for undo
let lastFix = null;

document.getElementById('undo_fix').addEventListener('click', ()=>{
  if(!lastFix) return;
  const ta = document.getElementById('source');
  ta.value = lastFix.text;
  // hide undo button
  document.getElementById('undo_fix').style.display = 'none';
  lastFix = null;
  syncHighlight();
  setTimeout(()=> document.getElementById('run').click(), 100);
});

// apply an automatic fix suggested by the parser error
function computeAbsPosFromLineCol(text, line, col){
  const lines = text.split('\n');
  let pos = 0;
  const li = Math.max(1, Math.min(line || 1, lines.length));
  for(let i=0;i<li-1;i++) pos += lines[i].length + 1;
  pos += Math.max(0, (col || 1) - 1);
  return pos;
}

function isSafeFixableAutoRecover(err){
  if(!err || !err.auto_recovered) return false;

  // Prefer stable diagnostic codes over message text.
  const code = String(err.code || '').toUpperCase();
  const msg = String(err.message || '');

  // Known auto-recoverable parser codes
  if(code === 'PAR_MISSING_THEN' || code === 'PAR_TYPO_THEN') return true;
  if(code === 'PAR_MISSING_DO' || code === 'PAR_TYPO_DO') return true;
  if(code === 'PAR_MISSING_RPAREN') return true;
  if(code === 'PAR_MISSING_SEMI') return true;
  if(code === 'PAR_MISSING_COMMA') return true;
  if(code === 'PAR_CONST_REQUIRES_ASSIGN') return true; // '=' -> ':='

  // Fallback to legacy message matching (older backends)
  if(msg.includes('缺少关键字 then')) return true;
  if(msg.includes('缺少关键字 do')) return true;
  if(msg.includes('缺少右括号')) return true;
  if(msg.includes('缺少分号')) return true;
  if(msg.includes('缺少逗号')) return true;
  if(msg.includes("const 声明应使用 ':='")) return true;

  return false;
}

function applyAutoFix(err){
  const ta = document.getElementById('source');
  let v = ta.value;
  lastFix = {text: v};

  const msg = String(err.message || '');
  const code = String(err.code || '').toUpperCase();
  const typoFixEnabled = !!(document.getElementById('typo_fix') && document.getElementById('typo_fix').checked);

  const insertAt = (absPos, s)=>{
    const p = Math.max(0, Math.min(absPos, v.length));
    v = v.slice(0,p) + s + v.slice(p);
  };

  if(!isSafeFixableAutoRecover(err)){
    lastFix = null;
    return;
  }

  // ---- A) const '=' -> ':='：这是替换，不是插入 ----
  if(code === 'PAR_CONST_REQUIRES_ASSIGN'){
    // Replace the offending '=' token with ':=' at the reported position.
    // We rely on token_value '=' and (line,col) pointing to it.
    const line = err.line || 1;
    const col = err.col || 1;
    const abs = computeAbsPosFromLineCol(v, line, col);
    if(v.slice(abs, abs+1) === '='){
      v = v.slice(0, abs) + ':=' + v.slice(abs+1);
    }else{
      // fallback: replace first '=' on that line near caret
      const lines = v.split('\n');
      const li = Math.max(1, Math.min(line, lines.length)) - 1;
      const caret = Math.max(0, (typeof err.caret === 'number') ? err.caret : (col - 1));
      const s = lines[li];
      const idx = s.indexOf('=', Math.max(0, caret-2));
      if(idx >= 0){
        lines[li] = s.slice(0, idx) + ':=' + s.slice(idx+1);
        v = lines.join('\n');
      }
    }

    ta.value = v;
    document.getElementById('undo_fix').style.display = 'inline-block';
    syncHighlight();
    setTimeout(()=> document.getElementById('run').click(), 100);
    return;
  }

  // ---- 0) 通用：若启用拼写纠错，优先在“错误 token 本身”做 typo→keyword 替换 ----
  // 目的：修复 doo/els/begn 等情况时，应当替换掉 typo，而不是再插入一个关键字。
  if(typoFixEnabled && String(err.token_type || '').toUpperCase() === 'ID'){
    const repTok = replaceTokenTypoWithKeyword(v, err.line || 1, err.col || 1, err.token_value);
    if(repTok){
      v = repTok.text;
      ta.value = v;
      document.getElementById('undo_fix').style.display = 'inline-block';
      syncHighlight();
      setTimeout(()=> document.getElementById('run').click(), 100);
      return;
    }
  }

  // ---- 1) 通用：若启用拼写纠错，且上一行/当前行行尾是 typo，则替换行尾 ----
  if(typoFixEnabled && err.line){
    // 优先上一行（常见：if/while 条件行末的 then/do typo）
    const repPrev = replaceTrailingTypoWithKeyword(v, (err.line || 1) - 1);
    if(repPrev){
      v = repPrev.text;
      ta.value = v;
      document.getElementById('undo_fix').style.display = 'inline-block';
      syncHighlight();
      setTimeout(()=> document.getElementById('run').click(), 100);
      return;
    }
    // 其次当前行（常见：单独一行写了 doo / begn / edn）
    const repCur = replaceTrailingTypoWithKeyword(v, (err.line || 1));
    if(repCur){
      v = repCur.text;
      ta.value = v;
      document.getElementById('undo_fix').style.display = 'inline-block';
      syncHighlight();
      setTimeout(()=> document.getElementById('run').click(), 100);
      return;
    }
  }

  // ---- 2) 结构性修复（插入缺失符号/关键字）----
  if(code === 'PAR_MISSING_SEMI' || msg.includes('缺少分号')){
    const line = err.line || 1;
    const lines = v.split('\n');
    const li = Math.max(1, Math.min(line, lines.length));
    let col = 1;
    if(typeof err.caret === 'number') col = err.caret + 1;
    else col = (lines[li-1]?.length || 0) + 1;
    const pos = computeAbsPosFromLineCol(v, li, col);
    insertAt(pos, ';');
  }
  else if(code === 'PAR_MISSING_RPAREN' || msg.includes('缺少右括号')){
    const line = err.line || 1;
    const col = (typeof err.caret === 'number') ? (err.caret + 1) : (err.col || 1);
    const pos = computeAbsPosFromLineCol(v, line, col);
    insertAt(pos, ')');
  }
  else if(code === 'PAR_MISSING_COMMA' || msg.includes('缺少逗号')){
    // Insert comma at the diagnostic location.
    const pos = computeAbsPosFromLineCol(v, err.line || 1, err.col || 1);
    // Avoid inserting duplicate commas if there is already a comma right before/at the position.
    const before = v[pos-1] || '';
    const at = v[pos] || '';
    if(before !== ',' && at !== ','){
      insertAt(pos, ',');
    }
  }
  else if(code === 'PAR_MISSING_THEN' || code === 'PAR_TYPO_THEN' || msg.includes('缺少关键字 then')){
    const pos = computeAbsPosFromLineCol(v, err.line || 1, err.col || 1);
    insertAt(pos, 'then\n');
  }
  else if(code === 'PAR_MISSING_DO' || code === 'PAR_TYPO_DO' || msg.includes('缺少关键字 do')){
    const pos = computeAbsPosFromLineCol(v, err.line || 1, err.col || 1);
    insertAt(pos, 'do\n');
  }

  ta.value = v;
  document.getElementById('undo_fix').style.display = 'inline-block';
  syncHighlight();
  setTimeout(()=> document.getElementById('run').click(), 100);
}

// --- 关键字拼写纠错白名单（默认值，若 txt 加载失败则使用）---
const DEFAULT_KEYWORD_TYPO_WHITELIST = {
  then: ['the', 'thn'],
  do: ['od', 'doo'],
  else: ['els', 'elese'],
  begin: ['begn', 'bgin'],
  end: ['edn'],
  while: ['whlie', 'wile'],
  procedure: ['procdure', 'procedre'],
  program: ['progam', 'prgram'],
  const: ['cnst'],
  var: ['vra'],
  call: ['cal'],
  read: ['raed'],
  write: ['wirte'],
  odd: ['oddd']
};

let KEYWORD_TYPO_WHITELIST = DEFAULT_KEYWORD_TYPO_WHITELIST;
let TYPO_TO_KW = buildTypoToKeywordMap(KEYWORD_TYPO_WHITELIST);

function buildTypoToKeywordMap(whitelist){
  const m = {};
  for(const [kw, typos] of Object.entries(whitelist || {})){
    if(!Array.isArray(typos)) continue;
    for(const t of typos){
      if(!t) continue;
      m[String(t).toLowerCase()] = kw;
    }
  }
  return m;
}

function parseTypoWhitelistText(text){
  // Format: keyword: typo1, typo2
  const out = {};
  const lines = String(text || '').split(/\r?\n/);
  for(const raw of lines){
    const line = raw.trim();
    if(!line) continue;
    if(line.startsWith('#')) continue;
    const idx = line.indexOf(':');
    if(idx <= 0) continue;
    const key = line.slice(0, idx).trim().toLowerCase();
    const rhs = line.slice(idx+1).trim();
    if(!key || !rhs) continue;
    const typos = rhs.split(',').map(s=>s.trim().toLowerCase()).filter(Boolean);
    if(typos.length === 0) continue;
    out[key] = typos;
  }
  return out;
}

async function loadTypoWhitelist(){
  try{
    const resp = await fetch('/static/typo_whitelist.txt', {cache: 'no-store'});
    if(!resp.ok) throw new Error('typo whitelist fetch failed');
    const txt = await resp.text();
    const parsed = parseTypoWhitelistText(txt);
    // only accept if parsed has at least one entry
    if(parsed && Object.keys(parsed).length > 0){
      KEYWORD_TYPO_WHITELIST = parsed;
      TYPO_TO_KW = buildTypoToKeywordMap(KEYWORD_TYPO_WHITELIST);
    }
  }catch(e){
    // fallback to defaults
    KEYWORD_TYPO_WHITELIST = DEFAULT_KEYWORD_TYPO_WHITELIST;
    TYPO_TO_KW = buildTypoToKeywordMap(KEYWORD_TYPO_WHITELIST);
  }
}

// fire-and-forget load
loadTypoWhitelist();

function replaceTrailingTypoWithKeyword(text, lineNo){
  const lines = text.split('\n');
  const li = Math.max(1, Math.min(lineNo || 1, lines.length));
  const line = lines[li-1];
  const m = line.match(/\b([A-Za-z]+)\b\s*$/);
  if(!m) return null;
  const lastWord = m[1];
  const typo = lastWord.toLowerCase();
  const kw = TYPO_TO_KW[typo];
  if(!kw) return null;
  lines[li-1] = line.replace(new RegExp(`\\b${lastWord}\\b\\s*$`), kw);
  return {text: lines.join('\n'), keyword: kw, typo};
}

function replaceTokenTypoWithKeyword(text, line, col, tokenValue){
  const typo = String(tokenValue || '').toLowerCase();
  const kw = TYPO_TO_KW[typo];
  if(!kw) return null;
  const pos = computeAbsPosFromLineCol(text, line || 1, col || 1);
  const end = pos + typo.length;
  return {text: text.slice(0, pos) + kw + text.slice(end), keyword: kw, typo};
}
