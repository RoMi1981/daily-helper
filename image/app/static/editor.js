/**
 * Shared Markdown editor logic — used by new.html, edit.html, settings.html.
 * Every editor must be wrapped in <div class="editor-container">.
 * All functions accept `ctx` (typically `this` from an onclick/oninput) so
 * multiple independent editors can coexist on the same page.
 */

// ── Context helpers ───────────────────────────────────────────────────────

function _container(ctx) {
  if (ctx) {
    const c = ctx.closest('.editor-container');
    if (c) return c;
  }
  // Fallback: single editor on page (new.html / edit.html)
  return document.querySelector('.editor-container');
}

function getEditor(ctx) {
  return _container(ctx).querySelector('textarea');
}

// ── Preview ───────────────────────────────────────────────────────────────

const _previewTimers = new WeakMap();

function schedulePreview(ctx) {
  const c = _container(ctx);
  clearTimeout(_previewTimers.get(c));
  _previewTimers.set(c, setTimeout(() => _doPreview(c), 300));
}

async function _doPreview(container) {
  const ta      = container.querySelector('textarea');
  const preview = container.querySelector('.preview-pane');
  if (!ta || !preview) return;
  const resp = await fetch('/api/preview', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({content: ta.value})
  });
  preview.innerHTML = await resp.text();
  if (window.hljs) {
    preview.querySelectorAll('pre code').forEach(b => hljs.highlightElement(b));
  }
}

// ── Tab switching ─────────────────────────────────────────────────────────

function switchTab(tab, btn) {
  const c = _container(btn);
  c.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
  btn.classList.add('active');
  const ta      = c.querySelector('textarea');
  const preview = c.querySelector('.preview-pane');
  const toolbar = c.querySelector('.toolbar');
  if (tab === 'preview') {
    _doPreview(c);
    ta.style.display      = 'none';
    toolbar.style.display = 'none';
    preview.style.display = 'block';
  } else {
    ta.style.display      = 'block';
    toolbar.style.display = 'flex';
    preview.style.display = 'none';
  }
}

// ── Editor helpers ────────────────────────────────────────────────────────

function insert(before, after, ctx) {
  const ta = getEditor(ctx);
  const start = ta.selectionStart;
  const lineStart = ta.value.lastIndexOf('\n', start - 1) + 1;
  ta.value = ta.value.substring(0, lineStart) + before + ta.value.substring(lineStart);
  ta.selectionStart = ta.selectionEnd = lineStart + before.length + (start - lineStart);
  ta.focus();
}

function wrap(before, after, ctx) {
  const ta = getEditor(ctx);
  const start = ta.selectionStart, end = ta.selectionEnd;
  const sel = ta.value.substring(start, end) || 'Text';
  ta.value = ta.value.substring(0, start) + before + sel + after + ta.value.substring(end);
  ta.selectionStart = start + before.length;
  ta.selectionEnd   = start + before.length + sel.length;
  ta.focus();
}

function insertLine(prefix, ctx) {
  const ta = getEditor(ctx);
  const start = ta.selectionStart;
  const lineStart = ta.value.lastIndexOf('\n', start - 1) + 1;
  const needsNewline = lineStart < start;
  const insertion = (needsNewline ? '\n' : '') + prefix;
  ta.value = ta.value.substring(0, start) + insertion + ta.value.substring(start);
  ta.selectionStart = ta.selectionEnd = start + insertion.length;
  ta.focus();
}

function insertBlock(text, ctx) {
  const ta = getEditor(ctx);
  const start = ta.selectionStart;
  ta.value = ta.value.substring(0, start) + text + ta.value.substring(start);
  ta.selectionStart = ta.selectionEnd = start + text.length;
  ta.focus();
}

function insertCodeBlock(ctx) {
  const lang = prompt('Language (e.g. bash, python, yaml) or leave empty:', 'bash');
  if (lang === null) return;
  const ta = getEditor(ctx);
  const start = ta.selectionStart, end = ta.selectionEnd;
  const sel = ta.value.substring(start, end) || 'code here';
  const block = '\n```' + lang + '\n' + sel + '\n```\n';
  ta.value = ta.value.substring(0, start) + block + ta.value.substring(end);
  ta.selectionStart = start + 4 + lang.length + 1;
  ta.selectionEnd   = start + 4 + lang.length + 1 + sel.length;
  ta.focus();
}

function insertTable(ctx) {
  const cols = parseInt(prompt('Number of columns:', '3'));
  if (!cols || cols < 1) return;
  const rows = parseInt(prompt('Number of rows (without header):', '2'));
  if (!rows || rows < 1) return;
  const header = '| ' + Array(cols).fill('Col').map((s, i) => s + (i + 1)).join(' | ') + ' |';
  const sep    = '| ' + Array(cols).fill('---').join(' | ') + ' |';
  const row    = '| ' + Array(cols).fill('     ').join(' | ') + ' |';
  const table  = '\n' + header + '\n' + sep + '\n' + Array(rows).fill(row).join('\n') + '\n';
  insertBlock(table, ctx);
}

function insertLink(ctx) {
  const text = prompt('Link text:', '');
  if (text === null) return;
  const url = prompt('URL:', 'https://');
  if (!url) return;
  wrap('[' + text, '](' + url + ')', ctx);
}

// ── Entry templates ───────────────────────────────────────────────────────

function loadTemplate(name) {
  if (!name) return;
  const today = new Date().toISOString().slice(0, 10);
  const templates = {
    howto: `## Goal\n\nDescribe what you want to achieve.\n\n## Prerequisites\n\n- ...\n\n## Steps\n\n1. First step\n2. Second step\n3. Third step\n\n## Troubleshooting\n\n- **Problem**: Solution\n`,
    troubleshooting: `## Symptom\n\nDescribe what went wrong.\n\n## Root Cause\n\nExplain the cause.\n\n## Solution\n\n\`\`\`bash\n# fix command\n\`\`\`\n\n## References\n\n- ...\n`,
    cheatsheet: `## Common Commands\n\n| Command | Description |\n|---------|-------------|\n| \`cmd\` | What it does |\n\n## Examples\n\n\`\`\`bash\n# example usage\n\`\`\`\n`,
    meeting: `## Date\n\n${today}\n\n## Attendees\n\n- ...\n\n## Topics\n\n1. ...\n\n## Decisions\n\n- ...\n\n## Action Items\n\n- [ ] Task — @person\n`,
  };
  const ta = getEditor();
  if (ta.value.trim() && !confirm('Replace current content with template?')) {
    document.getElementById('template-select').value = '';
    return;
  }
  ta.value = templates[name] || '';
  document.getElementById('template-select').value = '';
  schedulePreview(ta);
  ta.focus();
}
