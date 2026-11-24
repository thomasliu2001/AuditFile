/* 项目验收文档稽核平台 - 前端逻辑（零依赖） */
const state = {
  docTypes: [],
  dimensions: [],
  checkers: [],
  standardType: '',
  lastAuditResults: [],
};

const $ = (sel, root) => (root || document).querySelector(sel);

function esc(value) {
  return String(value == null ? '' : value).replace(/[&<>"']/g, (c) => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;',
  }[c]));
}

function typeName(code) {
  const t = state.docTypes.find((x) => x.code === code);
  return t ? t.name : code;
}

function dimName(key) {
  const d = state.dimensions.find((x) => x.key === key);
  return d ? d.name : key;
}

function scoreClass(score) {
  if (score >= 90) return 'score-good';
  if (score >= 60) return 'score-mid';
  return 'score-bad';
}

function scoreColor(score) {
  if (score >= 90) return '#12855b';
  if (score >= 60) return '#b06a00';
  return '#cf2b2b';
}

function gradeBadge(grade, score) {
  if (grade === '无法稽核') return '<span class="badge badge-skip">无法稽核</span>';
  const cls = score >= 90 ? 'badge-pass' : (score >= 60 ? 'badge-medium' : 'badge-fail');
  return '<span class="badge ' + cls + '">' + esc(grade) + '</span>';
}

function sevBadge(sev) {
  const map = { high: ['badge-high', '高'], medium: ['badge-medium', '中'], low: ['badge-low', '低'] };
  const item = map[sev] || ['badge-low', sev];
  return '<span class="badge ' + item[0] + '">' + item[1] + '</span>';
}

function statusBadge(status) {
  const map = { pass: ['badge-pass', '通过'], fail: ['badge-fail', '未通过'], skip: ['badge-skip', '跳过'] };
  const item = map[status] || ['badge-skip', status];
  return '<span class="badge ' + item[0] + '">' + item[1] + '</span>';
}

function toast(message, isError) {
  const el = $('#toast');
  el.textContent = message;
  el.className = 'toast show' + (isError ? ' err' : '');
  clearTimeout(el._timer);
  el._timer = setTimeout(() => { el.className = 'toast'; }, 3200);
}

async function api(path, options) {
  const opts = Object.assign({ headers: { 'Content-Type': 'application/json' } }, options || {});
  const res = await fetch(path, opts);
  let payload = null;
  try {
    payload = await res.json();
  } catch (e) {
    throw new Error('服务响应异常（HTTP ' + res.status + '）');
  }
  if (!res.ok || !payload.ok) throw new Error(payload.error || ('请求失败 HTTP ' + res.status));
  return payload.data;
}

/* ------------------------------------------------------------ 弹窗 */

function openModal(title, bodyHtml, footHtml) {
  const root = $('#modal-root');
  root.innerHTML =
    '<div class="modal-mask"><div class="modal">' +
    '<div class="modal-head"><h3>' + esc(title) + '</h3><button class="close-x" data-close>×</button></div>' +
    '<div class="modal-body">' + bodyHtml + '</div>' +
    '<div class="modal-foot">' + (footHtml || '<button class="btn" data-close>关闭</button>') + '</div>' +
    '</div></div>';
  const mask = $('.modal-mask', root);
  mask.addEventListener('click', (e) => {
    if (e.target === mask || e.target.hasAttribute('data-close')) closeModal();
  });
  return root;
}

function closeModal() {
  $('#modal-root').innerHTML = '';
}

/* ------------------------------------------------------------ 路由 */

const views = {
  dashboard: viewDashboard,
  audit: viewAudit,
  directory: viewDirectory,
  standards: viewStandards,
  history: viewHistory,
};

async function route() {
  const name = (location.hash.replace(/^#\//, '') || 'dashboard').split('?')[0];
  const view = views[name] || views.dashboard;
  document.querySelectorAll('.nav a').forEach((a) => {
    a.classList.toggle('active', a.dataset.nav === name);
  });
  const main = $('#main');
  main.innerHTML = '<div class="loading">加载中…</div>';
  try {
    await view(main);
  } catch (err) {
    main.innerHTML = '<div class="err-box">页面加载失败：' + esc(err.message) + '</div>';
  }
}

/* ------------------------------------------------------------ 概览 */

async function viewDashboard(main) {
  const [stats, types] = await Promise.all([api('/api/stats'), api('/api/doc-types')]);
  const typeRows = stats.by_type.length
    ? stats.by_type.map((row) => {
      const score = Number(row.avg_score || 0);
      return '<tr><td>' + esc(row.doc_type_name || row.doc_type) + '</td>' +
        '<td class="num">' + row.runs + '</td>' +
        '<td class="num"><span class="score ' + scoreClass(score) + '">' + score.toFixed(1) + '</span></td>' +
        '<td class="num">' + (row.unqualified || 0) + '</td>' +
        '<td><div class="progress"><span style="width:' + Math.min(100, score) + '%"></span></div></td></tr>';
    }).join('')
    : '<tr><td colspan="5"><div class="empty">暂无稽核数据</div></td></tr>';

  const recentRows = stats.recent.length
    ? stats.recent.map((r) => '<tr>' +
      '<td class="num">#' + r.id + '</td>' +
      '<td>' + esc(r.project_name || '—') + '</td>' +
      '<td><span class="badge badge-type">' + esc(typeName(r.doc_type)) + '</span></td>' +
      '<td>' + esc(r.file_name) + '</td>' +
      '<td class="num"><span class="score ' + scoreClass(r.score) + '">' + Number(r.score).toFixed(1) + '</span></td>' +
      '<td>' + gradeBadge(r.grade, r.score) + '</td>' +
      '<td class="num">' + esc(r.created_at) + '</td>' +
      '<td><button class="btn btn-sm" data-detail="' + r.id + '">详情</button></td></tr>').join('')
    : '<tr><td colspan="8"><div class="empty">暂无稽核记录，先去做一次单文档稽核吧</div></td></tr>';

  const typeCards = types.map((t) =>
    '<div class="type-item"><div style="min-width:0">' +
    '<div class="rule-title">' + esc(t.name) + '</div>' +
    '<div class="rule-desc">' + esc(t.description || '') + '</div>' +
    '<div class="hint">生效规则 ' + t.rule_count + ' 条 · 关键词：' + esc(t.filename_keywords.join(' / ')) + '</div>' +
    '</div><div class="rule-actions" style="flex:none">' +
    '<button class="btn btn-sm btn-primary" data-audit-type="' + t.code + '">稽核</button>' +
    '<button class="btn btn-sm" data-standard-type="' + t.code + '">配置标准</button>' +
    '</div></div>').join('');

  main.innerHTML =
    '<div class="page-head"><div><h1>稽核概览</h1><div class="sub">项目验收文档的合规检查、标准管理与追溯</div></div>' +
    '<div class="page-actions"><a class="btn" href="#/directory">项目目录稽核</a>' +
    '<a class="btn btn-primary" href="#/audit">单文档稽核</a></div></div>' +
    '<div class="grid grid-4" style="margin-bottom:18px">' +
    '<div class="stat"><div class="label">文档类型</div><div class="value">' + stats.doc_type_count + '</div><div class="hint">内置验收文档类型</div></div>' +
    '<div class="stat"><div class="label">生效稽核规则</div><div class="value">' + stats.rule_count + '</div><div class="hint">可按类型自行配置</div></div>' +
    '<div class="stat"><div class="label">累计稽核次数</div><div class="value">' + stats.run_count + '</div><div class="hint">全部记录可追溯</div></div>' +
    '<div class="stat"><div class="label">平均得分</div><div class="value">' + Number(stats.avg_score).toFixed(1) + '</div><div class="hint">严重问题 ' + stats.high_fail_count + ' 项</div></div>' +
    '</div>' +
    '<div class="card"><h3>最近稽核</h3>' +
    '<table class="table"><thead><tr><th>编号</th><th>项目</th><th>文档类型</th><th>文件</th><th>得分</th><th>结论</th><th>时间</th><th></th></tr></thead>' +
    '<tbody>' + recentRows + '</tbody></table></div>' +
    '<div class="grid grid-2">' +
    '<div class="card"><h3>按文档类型统计</h3>' +
    '<table class="table"><thead><tr><th>文档类型</th><th>次数</th><th>平均分</th><th>不合格</th><th>得分分布</th></tr></thead>' +
    '<tbody>' + typeRows + '</tbody></table></div>' +
    '<div class="card"><h3>文档类型与标准</h3>' + typeCards + '</div>' +
    '</div>';

  main.querySelectorAll('[data-detail]').forEach((btn) => {
    btn.addEventListener('click', () => openRunDetail(Number(btn.dataset.detail)));
  });
  main.querySelectorAll('[data-standard-type]').forEach((btn) => {
    btn.addEventListener('click', () => {
      state.standardType = btn.dataset.standardType;
      location.hash = '#/standards';
    });
  });
  main.querySelectorAll('[data-audit-type]').forEach((btn) => {
    btn.addEventListener('click', () => {
      location.hash = '#/audit?type=' + btn.dataset.auditType;
    });
  });
}

/* ------------------------------------------------------------ 单文档稽核 */

function escapeRegExp(text) {
  return String(text).replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
}

function detectTypeByFileName(name) {
  const lower = String(name || '').toLowerCase();
  let best = null;
  let bestLen = 0;
  state.docTypes.forEach((t) => {
    (t.filename_keywords || []).forEach((kw) => {
      if (kw && lower.indexOf(kw.toLowerCase()) >= 0 && kw.length > bestLen) {
        best = t;
        bestLen = kw.length;
      }
    });
  });
  return best;
}

function guessProjectName(fileName) {
  let base = String(fileName || '').replace(/\.docx$/i, '').replace(/^~\$/, '').trim();
  const keywords = [];
  state.docTypes.forEach((t) => (t.filename_keywords || []).forEach((kw) => { if (kw) keywords.push(kw); }));
  keywords.sort((a, b) => b.length - a.length);
  keywords.forEach((kw) => {
    base = base.replace(new RegExp(escapeRegExp(kw), 'gi'), ' ');
  });
  return base
    .replace(/\d{4}\s*[-_年.]\s*\d{1,2}\s*[-_月.]\s*\d{1,2}\s*日?/g, ' ')
    .replace(/[（(]?\s*[Vv]\d+(?:\.\d+)*\s*[)）]?/g, ' ')
    .replace(/[（(]?\s*版本\s*[Vv]?\d+(?:\.\d+)*\s*[)）]?/g, ' ')
    .replace(/(终稿|定稿|送审稿|征求意见稿|初稿|修订版|最终版|评审稿)/g, ' ')
    .replace(/[-_—－·]+/g, ' ')
    .replace(/\s{2,}/g, ' ')
    .trim();
}

async function viewAudit(main) {
  const types = state.docTypes;
  const preset = (location.hash.split('?')[1] || '').replace('type=', '');
  const options = types.map((t) =>
    '<option value="' + t.code + '"' + (preset === t.code ? ' selected' : '') + '>' + esc(t.name) + '</option>').join('');

  main.innerHTML =
    '<div class="page-head"><div><h1>单文档稽核</h1><div class="sub">按文档类型导入 .docx，立即按该类型标准执行四维稽核</div></div></div>' +
    '<div class="card"><form id="audit-form">' +
    '<div class="form-row">' +
    '<label class="field"><span>项目名称（可选，用于归档追溯）</span><input id="f-project" type="text" placeholder="例如：XX 系统建设项目"></label>' +
    '<label class="field"><span>文档类型</span><select id="f-type"><option value="auto">自动识别（按文件名）</option>' + options + '</select></label>' +
    '</div>' +
    '<div id="detect-hint" class="hint" style="margin:-4px 0 12px"></div>' +
    '<label class="field"><span>文档文件</span></label>' +
    '<div class="dropzone" id="dz"><div class="dz-title">点击选择，或将 .docx 文件拖拽到此处</div>' +
    '<div class="dz-sub">支持多选；文件在本机解析，稽核结果写入本地数据库留痕</div>' +
    '<input id="file-input" type="file" accept=".docx" multiple></div>' +
    '<div id="file-list" class="hint" style="margin-top:10px"></div>' +
    '<div style="margin-top:16px;display:flex;gap:8px;align-items:center">' +
    '<button class="btn btn-primary" type="submit" id="audit-btn">开始稽核</button>' +
    '<span class="hint">评分按严重级别加权：高 5 / 中 3 / 低 1</span></div>' +
    '</form></div>' +
    '<div id="audit-results"></div>';

  const input = $('#file-input', main);
  const dz = $('#dz', main);
  const fileList = $('#file-list', main);
  const projectInput = $('#f-project', main);
  const typeSelect = $('#f-type', main);
  const hint = $('#detect-hint', main);
  let userPickedType = !!preset;
  let projectAuto = false;

  function syncFields(infos, codes) {
    if (!userPickedType) {
      if (codes.length === 1) typeSelect.value = codes[0];
      else if (codes.length > 1) typeSelect.value = 'auto';
      else if (!infos.length) typeSelect.value = 'auto';
    }
    if (infos.length && (!projectInput.value.trim() || projectAuto)) {
      const guess = guessProjectName(infos[0].file.name);
      if (guess) {
        projectInput.value = guess;
        projectAuto = true;
      } else if (projectAuto) {
        projectInput.value = '';
        projectAuto = false;
      }
    }
  }

  function renderHint(infos, codes) {
    if (!infos.length) {
      hint.textContent = '';
      return;
    }
    if (userPickedType) {
      const label = typeSelect.options[typeSelect.selectedIndex].text;
      hint.innerHTML = '已手动指定文档类型：<b>' + esc(label) + '</b>，将以手动选择为准。';
      return;
    }
    if (codes.length === 1) {
      const blank = projectInput.value.trim() ? '' : '；项目名称未能从文件名推断，请手动填写';
      hint.innerHTML = '已根据文件名自动识别为 <b>' + esc(typeName(codes[0])) + '</b>' + blank + '。';
    } else if (codes.length > 1) {
      hint.innerHTML = '所选文件包含 ' + codes.length + ' 种文档类型，提交时将按文件名分别识别。';
    } else {
      hint.innerHTML = '<span style="color:#b06a00">未能从文件名识别文档类型，请手动选择。</span>';
    }
  }

  function updateList() {
    const files = Array.from(input.files || []);
    const infos = files.map((file) => ({ file: file, type: detectTypeByFileName(file.name) }));
    const codes = [];
    infos.forEach((item) => {
      if (item.type && codes.indexOf(item.type.code) < 0) codes.push(item.type.code);
    });

    fileList.innerHTML = infos.length
      ? infos.map((item) => '<div>· ' + esc(item.file.name) +
        '（' + (item.file.size / 1024).toFixed(0) + ' KB）' +
        (item.type
          ? ' <span class="badge badge-type">' + esc(item.type.name) + '</span>'
          : ' <span class="badge badge-skip">类型未识别</span>') +
        '</div>').join('')
      : '';

    syncFields(infos, codes);
    renderHint(infos, codes);
  }

  projectInput.addEventListener('input', () => { projectAuto = false; });
  typeSelect.addEventListener('change', () => {
    userPickedType = true;
    renderHint(
      Array.from(input.files || []).map((file) => ({ file: file, type: detectTypeByFileName(file.name) })),
      []
    );
  });

  dz.addEventListener('click', () => input.click());
  dz.addEventListener('dragover', (e) => { e.preventDefault(); dz.classList.add('drag'); });
  dz.addEventListener('dragleave', () => dz.classList.remove('drag'));
  dz.addEventListener('drop', (e) => {
    e.preventDefault();
    dz.classList.remove('drag');
    input.files = e.dataTransfer.files;
    updateList();
  });
  input.addEventListener('change', updateList);

  function readBase64(file) {
    return new Promise((resolve, reject) => {
      const reader = new FileReader();
      reader.onload = () => resolve(String(reader.result).split(',')[1] || '');
      reader.onerror = () => reject(new Error('读取文件失败：' + file.name));
      reader.readAsDataURL(file);
    });
  }

  $('#audit-form', main).addEventListener('submit', async (e) => {
    e.preventDefault();
    const files = Array.from(input.files || []);
    if (!files.length) { toast('请先选择要稽核的 .docx 文件', true); return; }
    const docType = $('#f-type', main).value;
    const project = $('#f-project', main).value.trim();
    const btn = $('#audit-btn', main);
    const results = $('#audit-results', main);
    btn.disabled = true;

    const done = [];
    for (let i = 0; i < files.length; i++) {
      results.innerHTML = '<div class="progress-line">正在稽核 ' + (i + 1) + ' / ' + files.length + '：' + esc(files[i].name) + ' …</div>';
      try {
        const content = await readBase64(files[i]);
        const payload = { file_name: files[i].name, content: content, project_name: project };
        if (docType !== 'auto') payload.doc_type = docType;
        const run = await api('/api/audit/file', { method: 'POST', body: JSON.stringify(payload) });
        done.push(run);
      } catch (err) {
        done.push({ file_name: files[i].name, status: 'error', error: err.message, score: 0, grade: '无法稽核', total_rules: 0, passed_rules: 0, duration_ms: 0 });
      }
    }
    btn.disabled = false;
    state.lastAuditResults = done;

    results.innerHTML = '<div class="card"><h3>稽核结果（' + done.length + ' 份）</h3>' +
      done.map((r, idx) => {
        if (r.status === 'error') {
          return '<div class="result-card"><div class="score score-na">—</div><div class="file">' +
            '<div class="name">' + esc(r.file_name) + '</div>' +
            '<div class="err-box" style="margin:6px 0 0">' + esc(r.error || '稽核失败') + '</div></div></div>';
        }
        return '<div class="result-card"><div class="score ' + scoreClass(r.score) + '">' + Number(r.score).toFixed(1) + '</div>' +
          '<div class="file"><div class="name">' + esc(r.file_name) + '</div>' +
          '<div class="meta">' + esc(typeName(r.doc_type)) + ' · 通过 ' + r.passed_rules + ' / ' + r.total_rules +
          ' 条 · 未通过 ' + r.failed_rules + ' 条 · 耗时 ' + r.duration_ms + 'ms</div></div>' +
          gradeBadge(r.grade, r.score) +
          '<button class="btn btn-sm" data-view-result="' + idx + '">查看详情</button></div>';
      }).join('') + '</div>';

    results.querySelectorAll('[data-view-result]').forEach((b) => {
      b.addEventListener('click', () => showRunModal(done[Number(b.dataset.viewResult)]));
    });
    if (done.length === 1 && done[0].status === 'done') showRunModal(done[0]);
    if (done.some((r) => r.status === 'done')) toast('稽核完成，结果已写入历史记录');
  });
}

/* ------------------------------------------------------------ 目录批量稽核 */

async function viewDirectory(main) {
  main.innerHTML =
    '<div class="page-head"><div><h1>项目目录稽核</h1><div class="sub">指定项目文档目录，按文件名自动匹配五类验收文档并批量稽核</div></div></div>' +
    '<div class="card"><form id="dir-form">' +
    '<div class="form-row">' +
    '<label class="field"><span>项目名称（可选）</span><input id="d-project" type="text" placeholder="默认取目录名"></label>' +
    '<label class="field"><span>文档目录绝对路径</span>' +
    '<div class="input-with-btn">' +
    '<input id="d-path" type="text" placeholder="/Users/xxx/project/验收文档">' +
    '<button class="btn" type="button" id="pick-dir">选择目录…</button>' +
    '</div></label>' +
    '</div>' +
    '<div class="hint" style="margin-bottom:12px">可手动输入或以弹窗选择目录；将递归扫描目录下 .docx 文件（最多 5 层、300 份），按文件名关键词匹配：需求规格说明书 / 概要设计 / 详细设计 / 测试报告 / 后评估报告。</div>' +
    '<div style="display:flex;gap:8px"><button class="btn" type="button" id="scan-btn">扫描预览</button>' +
    '<button class="btn btn-primary" type="submit">开始批量稽核</button></div>' +
    '</form></div><div id="dir-result"></div>';

  const pathInput = $('#d-path', main);
  const projectInput = $('#d-project', main);
  const resultBox = $('#dir-result', main);

  $('#pick-dir', main).addEventListener('click', async () => {
    const btn = $('#pick-dir', main);
    const original = btn.textContent;
    btn.disabled = true;
    btn.textContent = '选择中…';
    try {
      const data = await api('/api/system/pick-directory', { method: 'POST', body: '{}' });
      pathInput.value = data.path;
      if (!projectInput.value.trim()) {
        const name = data.path.split(/[\\/]/).filter(Boolean).pop();
        if (name) projectInput.value = name;
      }
      resultBox.innerHTML = '';
      toast('已选择目录：' + data.path);
    } catch (err) {
      if (err.message.indexOf('已取消') >= 0) toast('已取消选择');
      else toast(err.message, true);
    } finally {
      btn.disabled = false;
      btn.textContent = original;
    }
  });

  async function scan(dryRun) {
    const path = pathInput.value.trim();
    if (!path) { toast('请填写目录绝对路径', true); return null; }
    if (!path.startsWith('/')) { toast('请填写绝对路径（以 / 开头）', true); return null; }
    const data = await api('/api/audit/directory', {
      method: 'POST',
      body: JSON.stringify({ path: path, project_name: projectInput.value.trim(), dry_run: dryRun }),
    });
    return data;
  }

  function mappingHtml(scanData) {
    const rows = scanData.matched.map((m) =>
      '<tr><td>' + esc(m.file_name) + '</td><td><span class="badge badge-type">' + esc(m.doc_type_name) + '</span></td>' +
      '<td class="num">' + (m.file_size / 1024).toFixed(0) + ' KB</td>' +
      '<td class="hint" style="word-break:break-all">' + esc(m.file_path) + '</td></tr>').join('');
    const unmatched = scanData.unmatched.length
      ? '<div class="warn-box" style="margin-top:12px">' + scanData.unmatched.length + ' 份文档未匹配到文档类型，将跳过：' +
        scanData.unmatched.map((u) => esc(u.file_name)).join('、') + '</div>'
      : '';
    return '<div class="card"><h3>扫描结果：共 ' + scanData.docx_total + ' 份 .docx，匹配 ' + scanData.matched.length + ' 份</h3>' +
      (scanData.matched.length
        ? '<table class="table"><thead><tr><th>文件</th><th>匹配类型</th><th>大小</th><th>路径</th></tr></thead><tbody>' + rows + '</tbody></table>'
        : '<div class="empty">目录下没有可匹配的验收文档</div>') + unmatched + '</div>';
  }

  $('#scan-btn', main).addEventListener('click', async () => {
    const btn = $('#scan-btn', main);
    btn.disabled = true;
    resultBox.innerHTML = '<div class="progress-line">正在扫描目录…</div>';
    try {
      const data = await scan(true);
      if (data) resultBox.innerHTML = mappingHtml(data);
    } catch (err) {
      resultBox.innerHTML = '<div class="err-box">' + esc(err.message) + '</div>';
    } finally {
      btn.disabled = false;
    }
  });

  $('#dir-form', main).addEventListener('submit', async (e) => {
    e.preventDefault();
    resultBox.innerHTML = '<div class="progress-line">正在批量稽核，请稍候…</div>';
    try {
      const data = await scan(false);
      if (!data) return;
      const batch = data.batch;
      const rows = data.results.map((r, idx) => r.status === 'error'
        ? '<tr><td>' + esc(r.file_name) + '</td><td><span class="badge badge-type">' + esc(r.doc_type_name) + '</span></td>' +
          '<td colspan="3" class="hint">' + esc(r.error) + '</td><td></td></tr>'
        : '<tr><td>' + esc(r.file_name) + '</td><td><span class="badge badge-type">' + esc(r.doc_type_name) + '</span></td>' +
          '<td class="num"><span class="score ' + scoreClass(r.score) + '">' + Number(r.score).toFixed(1) + '</span></td>' +
          '<td>' + gradeBadge(r.grade, r.score) + '</td>' +
          '<td class="num">' + r.failed_rules + ' / ' + r.total_rules + '</td>' +
          '<td><button class="btn btn-sm" data-open-run="' + r.id + '">详情</button></td></tr>').join('');

      resultBox.innerHTML =
        '<div class="grid grid-4" style="margin-bottom:16px">' +
        '<div class="stat"><div class="label">批次编号</div><div class="value">#' + batch.id + '</div><div class="hint">' + esc(batch.project_name) + '</div></div>' +
        '<div class="stat"><div class="label">稽核文档数</div><div class="value">' + batch.doc_total + '</div><div class="hint">未匹配 ' + data.unmatched.length + ' 份</div></div>' +
        '<div class="stat"><div class="label">合格文档</div><div class="value">' + batch.doc_passed + '</div><div class="hint">得分 ≥ 60 计为合格</div></div>' +
        '<div class="stat"><div class="label">批次平均分</div><div class="value">' + Number(batch.avg_score).toFixed(1) + '</div><div class="hint">按严重级别加权</div></div>' +
        '</div>' +
        '<div class="card"><h3>批次明细</h3><table class="table"><thead><tr><th>文件</th><th>文档类型</th><th>得分</th><th>结论</th><th>未通过/规则</th><th></th></tr></thead>' +
        '<tbody>' + rows + '</tbody></table>' +
        (data.unmatched.length ? '<div class="warn-box" style="margin-top:12px">未匹配文档：' + data.unmatched.map((u) => esc(u.file_name)).join('、') + '</div>' : '') +
        '</div>';

      resultBox.querySelectorAll('[data-open-run]').forEach((b) => {
        b.addEventListener('click', () => openRunDetail(Number(b.dataset.openRun)));
      });
      toast('批量稽核完成，批次 #' + batch.id + ' 已归档');
    } catch (err) {
      resultBox.innerHTML = '<div class="err-box">' + esc(err.message) + '</div>';
    }
  });
}

/* ------------------------------------------------------------ 标准配置 */

async function viewStandards(main) {
  if (!state.standardType) state.standardType = state.docTypes[0] ? state.docTypes[0].code : '';
  const code = state.standardType;
  const [rules, versionData] = await Promise.all([
    api('/api/rules?docType=' + encodeURIComponent(code)),
    api('/api/standards/versions?docType=' + encodeURIComponent(code)),
  ]);

  const tabs = state.docTypes.map((t) =>
    '<button data-type="' + t.code + '" class="' + (t.code === code ? 'active' : '') + '">' + esc(t.name) + '</button>').join('');

  const grouped = state.dimensions.map((dim) => {
    const items = rules.filter((r) => r.dimension === dim.key);
    if (!items.length) {
      return '<div class="dim-block"><div class="dim-head"><h4>' + esc(dim.name) + '</h4><span class="stat-mini">0 条</span></div>' +
        '<div class="empty" style="padding:14px">该维度暂无规则</div></div>';
    }
    const rows = items.map((r) => {
      const checker = state.checkers.find((c) => c.key === r.checker);
      const checkerLabel = checker ? checker.label : r.checker;
      return '<div class="rule-row">' +
        '<label class="switch"><input type="checkbox" data-toggle="' + r.id + '"' + (r.enabled ? ' checked' : '') + '><span class="track"></span></label>' +
        '<div class="rule-main"><div class="rule-title">' + esc(r.name) + sevBadge(r.severity) +
        (checkerLabel !== r.name ? '<span class="badge badge-low">' + esc(checkerLabel) + '</span>' : '') +
        (r.enabled ? '' : '<span class="badge badge-skip">已停用</span>') + '</div>' +
        '<div class="rule-desc">' + esc(r.description || '') + '</div>' +
        '<code class="rule-params">' + esc(JSON.stringify(r.params)) + '</code></div>' +
        '<div class="rule-actions"><button class="btn btn-sm" data-edit="' + r.id + '">编辑</button>' +
        '<button class="btn btn-sm btn-danger" data-del="' + r.id + '">删除</button></div></div>';
    }).join('');
    return '<div class="dim-block"><div class="dim-head"><h4>' + esc(dim.name) + '</h4>' +
      '<span class="stat-mini">' + items.length + ' 条规则，启用 ' + items.filter((x) => x.enabled).length + ' 条</span></div>' + rows + '</div>';
  }).join('');

  const versions = versionData.versions.length
    ? versionData.versions.map((v) =>
      '<tr><td class="num">v' + v.version_no + '</td><td class="num">' + v.rule_count + ' 条</td>' +
      '<td>' + esc(v.note || '') + '</td><td class="num">' + esc(v.created_at) + '</td></tr>').join('')
    : '<tr><td colspan="4"><div class="empty">尚未发布标准版本</div></td></tr>';

  const current = versionData.versions[0];

  main.innerHTML =
    '<div class="page-head"><div><h1>稽核标准</h1><div class="sub">按文档类型维护稽核规则，发布后作为留痕版本</div></div>' +
    '<div class="page-actions"><button class="btn" id="reset-rules">恢复默认</button>' +
    '<button class="btn" id="publish">发布标准版本</button>' +
    '<button class="btn btn-primary" id="add-rule">新增规则</button></div></div>' +
    '<div class="tabs">' + tabs + '</div>' +
    (current ? '<div class="ok-box">当前标准版本 v' + current.version_no + '（' + current.rule_count + ' 条规则，发布于 ' + esc(current.created_at) + '）；修改规则后请发布新版本以便稽核记录追溯。</div>' : '') +
    '<div class="grid grid-2" style="grid-template-columns: minmax(0,2fr) minmax(0,1fr)">' +
    '<div>' + grouped + '</div>' +
    '<div class="card"><h3>标准版本历史</h3><table class="table"><thead><tr><th>版本</th><th>规则数</th><th>说明</th><th>发布时间</th></tr></thead><tbody>' +
    versions + '</tbody></table></div></div>';

  main.querySelectorAll('[data-type]').forEach((btn) => {
    btn.addEventListener('click', () => { state.standardType = btn.dataset.type; route(); });
  });
  main.querySelectorAll('[data-toggle]').forEach((el) => {
    el.addEventListener('change', async () => {
      try {
        await api('/api/rules/' + el.dataset.toggle + '/toggle', { method: 'POST', body: '{}' });
        toast('规则状态已更新');
        route();
      } catch (err) { toast(err.message, true); }
    });
  });
  main.querySelectorAll('[data-edit]').forEach((btn) => {
    btn.addEventListener('click', () => {
      const rule = rules.find((x) => x.id === Number(btn.dataset.edit));
      openRuleModal(rule);
    });
  });
  main.querySelectorAll('[data-del]').forEach((btn) => {
    btn.addEventListener('click', async () => {
      if (!confirm('确定删除该稽核规则？历史稽核记录中的结果不会受影响。')) return;
      try {
        await api('/api/rules/' + btn.dataset.del, { method: 'DELETE', body: '{}' });
        toast('规则已删除');
        route();
      } catch (err) { toast(err.message, true); }
    });
  });
  $('#add-rule', main).addEventListener('click', () => openRuleModal(null));

  $('#publish', main).addEventListener('click', async () => {
    const note = prompt('请输入版本说明（可选）', '标准调整');
    if (note === null) return;
    try {
      const data = await api('/api/standards/publish', {
        method: 'POST',
        body: JSON.stringify({ doc_type: code, note: note }),
      });
      toast('已发布标准版本 v' + data.version_no);
      route();
    } catch (err) { toast(err.message, true); }
  });

  $('#reset-rules', main).addEventListener('click', async () => {
    if (!confirm('将删除当前类型的所有规则并恢复内置默认值，是否继续？')) return;
    try {
      await api('/api/rules/reset', { method: 'POST', body: JSON.stringify({ doc_type: code }) });
      toast('已恢复默认标准');
      route();
    } catch (err) { toast(err.message, true); }
  });
}

function paramFields(example, current) {
  const source = Object.assign({}, example || {}, current || {});
  const keys = Object.keys(source);
  if (!keys.length) return '<p class="hint">该检查器无需参数。</p>';
  return keys.map((key) => {
    const value = source[key];
    if (Array.isArray(value)) {
      const text = value.map((v) => (typeof v === 'object' ? JSON.stringify(v) : v)).join('\n');
      return '<label class="field"><span>' + esc(key) + '（每行一项）</span>' +
        '<textarea data-param="' + esc(key) + '" data-type="array">' + esc(text) + '</textarea></label>';
    }
    if (typeof value === 'number') {
      return '<label class="field"><span>' + esc(key) + '</span><input type="number" step="any" data-param="' +
        esc(key) + '" data-type="number" value="' + value + '"></label>';
    }
    if (typeof value === 'boolean') {
      return '<label class="field"><span>' + esc(key) + '</span><select data-param="' + esc(key) + '" data-type="boolean">' +
        '<option value="true"' + (value ? ' selected' : '') + '>是</option>' +
        '<option value="false"' + (!value ? ' selected' : '') + '>否</option></select></label>';
    }
    return '<label class="field"><span>' + esc(key) + '</span><input type="text" data-param="' + esc(key) +
      '" data-type="string" value="' + esc(value == null ? '' : value) + '"></label>';
  }).join('');
}

function collectParams(scope) {
  const out = {};
  scope.querySelectorAll('[data-param]').forEach((el) => {
    const key = el.dataset.param;
    const type = el.dataset.type;
    if (type === 'array') out[key] = el.value.split('\n').map((s) => s.trim()).filter(Boolean);
    else if (type === 'number') out[key] = el.value === '' ? 0 : Number(el.value);
    else if (type === 'boolean') out[key] = el.value === 'true';
    else out[key] = el.value.trim();
  });
  return out;
}

function openRuleModal(rule) {
  const isEdit = !!rule;
  const checkerOptions = state.checkers.map((c) =>
    '<option value="' + c.key + '"' + (rule && rule.checker === c.key ? ' selected' : '') + '>' +
    esc(c.label) + ' · ' + esc(c.dimension_name) + '</option>').join('');
  const dimOptions = state.dimensions.map((d) =>
    '<option value="' + d.key + '"' + (rule && rule.dimension === d.key ? ' selected' : '') + '>' + esc(d.name) + '</option>').join('');
  const sevOptions = ['high', 'medium', 'low'].map((s) =>
    '<option value="' + s + '"' + (rule && rule.severity === s ? ' selected' : '') + '>' +
    ({ high: '高', medium: '中', low: '低' }[s]) + '</option>').join('');

  const modal = openModal(
    isEdit ? '编辑稽核规则' : '新增稽核规则',
    '<form id="rule-form">' +
    '<div class="form-row">' +
    '<label class="field"><span>规则名称</span><input id="f-name" type="text" value="' + esc(rule ? rule.name : '') + '" placeholder="例如：必备章节齐全"></label>' +
    '<label class="field"><span>检查器</span><select id="f-checker">' + checkerOptions + '</select></label>' +
    '</div>' +
    '<div class="form-row">' +
    '<label class="field"><span>稽核维度</span><select id="f-dimension">' + dimOptions + '</select></label>' +
    '<label class="field"><span>严重级别</span><select id="f-severity">' + sevOptions + '</select></label>' +
    '</div>' +
    '<div class="form-row">' +
    '<label class="field"><span>排序值（小在前）</span><input id="f-sort" type="number" value="' + (rule ? rule.sort_order : 100) + '"></label>' +
    '<label class="field"><span>说明</span><input id="f-desc" type="text" value="' + esc(rule ? rule.description || '' : '') + '" placeholder="规则用途 / 验收依据"></label>' +
    '</div>' +
    '<div class="field"><span>规则参数</span><div id="params-form"></div>' +
    '<div style="margin-top:4px"><button type="button" class="btn-link" id="mode-toggle">切换为 JSON 编辑</button></div>' +
    '<textarea id="params-json" style="display:none;margin-top:8px"></textarea></div>' +
    '<div id="checker-desc" class="hint"></div>' +
    '</form>',
    '<button class="btn" data-close>取消</button><button class="btn btn-primary" id="save-rule">保存</button>');

  const checkerSel = $('#f-checker', modal);
  const paramsForm = $('#params-form', modal);
  const paramsJson = $('#params-json', modal);
  const modeToggle = $('#mode-toggle', modal);
  let mode = 'form';

  function renderParams() {
    const meta = state.checkers.find((c) => c.key === checkerSel.value);
    const example = meta ? meta.params_example : {};
    const current = (rule && rule.checker === checkerSel.value) ? rule.params : {};
    paramsForm.innerHTML = paramFields(example, current);
    paramsJson.value = JSON.stringify(Object.assign({}, example, current), null, 2);
    $('#checker-desc', modal).textContent = meta ? meta.description : '';
    if (meta) $('#f-dimension', modal).value = meta.dimension;
  }

  checkerSel.addEventListener('change', renderParams);
  renderParams();

  modeToggle.addEventListener('click', () => {
    if (mode === 'form') {
      paramsJson.value = JSON.stringify(collectParams(paramsForm), null, 2);
      paramsJson.style.display = 'block';
      paramsForm.style.display = 'none';
      modeToggle.textContent = '切换为表单编辑';
      mode = 'json';
    } else {
      let parsed = {};
      try { parsed = JSON.parse(paramsJson.value || '{}'); } catch (e) {
        toast('JSON 格式错误，请修正后再切换', true);
        return;
      }
      const meta = state.checkers.find((c) => c.key === checkerSel.value);
      paramsForm.innerHTML = paramFields(meta ? meta.params_example : {}, parsed);
      paramsJson.style.display = 'none';
      paramsForm.style.display = 'block';
      modeToggle.textContent = '切换为 JSON 编辑';
      mode = 'form';
    }
  });

  $('#save-rule', modal).addEventListener('click', async () => {
    let params;
    if (mode === 'json') {
      try { params = JSON.parse(paramsJson.value || '{}'); } catch (e) {
        toast('规则参数不是合法 JSON', true);
        return;
      }
    } else {
      params = collectParams(paramsForm);
    }
    const payload = {
      doc_type: state.standardType,
      name: $('#f-name', modal).value.trim(),
      checker: checkerSel.value,
      dimension: $('#f-dimension', modal).value,
      severity: $('#f-severity', modal).value,
      sort_order: Number($('#f-sort', modal).value || 100),
      description: $('#f-desc', modal).value.trim(),
      params: params,
      enabled: 1,
    };
    if (!payload.name) { toast('请填写规则名称', true); return; }
    try {
      if (isEdit) {
        await api('/api/rules/' + rule.id, { method: 'PUT', body: JSON.stringify(payload) });
        toast('规则已更新');
      } else {
        await api('/api/rules', { method: 'POST', body: JSON.stringify(payload) });
        toast('规则已新增');
      }
      closeModal();
      route();
    } catch (err) { toast(err.message, true); }
  });
}

/* ------------------------------------------------------------ 历史记录 */

async function viewHistory(main) {
  const typeOptions = state.docTypes.map((t) => '<option value="' + t.code + '">' + esc(t.name) + '</option>').join('');
  main.innerHTML =
    '<div class="page-head"><div><h1>历史记录</h1><div class="sub">所有稽核结果与标准快照长期留存，可追溯查询</div></div></div>' +
    '<div class="card"><form id="filter-form" style="display:flex;gap:10px;flex-wrap:wrap;align-items:flex-end">' +
    '<label class="field" style="margin:0;min-width:170px"><span>文档类型</span><select id="h-type"><option value="">全部类型</option>' + typeOptions + '</select></label>' +
    '<label class="field" style="margin:0;min-width:240px;flex:1"><span>文件 / 项目关键词</span><input id="h-keyword" type="text" placeholder="模糊匹配"></label>' +
    '<button class="btn btn-primary" type="submit">查询</button>' +
    '<button class="btn" type="button" id="h-reset">重置</button></form></div>' +
    '<div class="card" id="runs-card"><h3>稽核记录</h3><div class="empty">加载中…</div></div>' +
    '<div class="card" id="batches-card"><h3>批量稽核批次</h3><div class="empty">加载中…</div></div>';

  async function loadRuns() {
    const params = new URLSearchParams();
    const type = $('#h-type', main).value;
    const keyword = $('#h-keyword', main).value.trim();
    if (type) params.set('docType', type);
    if (keyword) params.set('keyword', keyword);
    params.set('limit', '200');
    const card = $('#runs-card', main);
    try {
      const runs = await api('/api/runs?' + params.toString());
      if (!runs.length) {
        card.innerHTML = '<h3>稽核记录</h3><div class="empty">没有符合条件的稽核记录</div>';
        return;
      }
      card.innerHTML = '<h3>稽核记录（' + runs.length + '）</h3>' +
        '<table class="table"><thead><tr><th>编号</th><th>时间</th><th>项目</th><th>文档类型</th><th>文件</th>' +
        '<th>得分</th><th>结论</th><th>通过/总数</th><th>操作</th></tr></thead><tbody>' +
        runs.map((r) => '<tr>' +
          '<td class="num">#' + r.id + '</td>' +
          '<td class="num">' + esc(r.created_at) + '</td>' +
          '<td>' + esc(r.project_name || '—') + '</td>' +
          '<td><span class="badge badge-type">' + esc(r.doc_type_name) + '</span></td>' +
          '<td style="max-width:260px;word-break:break-all">' + esc(r.file_name) +
          (r.batch_id ? ' <span class="tag">批次 #' + r.batch_id + '</span>' : '') + '</td>' +
          '<td class="num"><span class="score ' + scoreClass(r.score) + '">' + Number(r.score).toFixed(1) + '</span></td>' +
          '<td>' + gradeBadge(r.grade, r.score) + '</td>' +
          '<td class="num">' + r.passed_rules + ' / ' + r.total_rules + '</td>' +
          '<td><button class="btn btn-sm" data-run="' + r.id + '">详情</button>' +
          '<button class="btn btn-sm" data-export="' + r.id + '">导出</button>' +
          '<button class="btn btn-sm btn-danger" data-remove="' + r.id + '">删除</button></td></tr>').join('') +
        '</tbody></table>';

      card.querySelectorAll('[data-run]').forEach((b) => {
        b.addEventListener('click', () => openRunDetail(Number(b.dataset.run)));
      });
      card.querySelectorAll('[data-export]').forEach((b) => {
        b.addEventListener('click', () => window.open('/api/runs/' + b.dataset.export + '/export', '_blank'));
      });
      card.querySelectorAll('[data-remove]').forEach((b) => {
        b.addEventListener('click', async () => {
          if (!confirm('删除后该次稽核结果不可恢复，是否继续？')) return;
          try {
            await api('/api/runs/' + b.dataset.remove, { method: 'DELETE', body: '{}' });
            toast('记录已删除');
            loadRuns();
          } catch (err) { toast(err.message, true); }
        });
      });
    } catch (err) {
      card.innerHTML = '<h3>稽核记录</h3><div class="err-box">' + esc(err.message) + '</div>';
    }
  }

  async function loadBatches() {
    const card = $('#batches-card', main);
    try {
      const batches = await api('/api/batches');
      if (!batches.length) {
        card.innerHTML = '<h3>批量稽核批次</h3><div class="empty">暂无批次记录</div>';
        return;
      }
      card.innerHTML = '<h3>批量稽核批次</h3>' +
        '<table class="table"><thead><tr><th>批次</th><th>项目</th><th>目录</th><th>文档数</th><th>合格</th><th>平均分</th><th>时间</th><th></th></tr></thead><tbody>' +
        batches.map((b) => '<tr><td class="num">#' + b.id + '</td><td>' + esc(b.project_name || '—') + '</td>' +
          '<td class="hint" style="max-width:300px;word-break:break-all">' + esc(b.source_dir) + '</td>' +
          '<td class="num">' + b.doc_total + '</td><td class="num">' + b.doc_passed + '</td>' +
          '<td class="num"><span class="score ' + scoreClass(b.avg_score) + '">' + Number(b.avg_score).toFixed(1) + '</span></td>' +
          '<td class="num">' + esc(b.created_at) + '</td>' +
          '<td><button class="btn btn-sm" data-batch="' + b.id + '">查看</button></td></tr>').join('') +
        '</tbody></table>';
      card.querySelectorAll('[data-batch]').forEach((btn) => {
        btn.addEventListener('click', () => openBatch(Number(btn.dataset.batch)));
      });
    } catch (err) {
      card.innerHTML = '<h3>批量稽核批次</h3><div class="err-box">' + esc(err.message) + '</div>';
    }
  }

  $('#filter-form', main).addEventListener('submit', (e) => { e.preventDefault(); loadRuns(); });
  $('#h-reset', main).addEventListener('click', () => {
    $('#h-type', main).value = '';
    $('#h-keyword', main).value = '';
    loadRuns();
  });

  await Promise.all([loadRuns(), loadBatches()]);
}

async function openBatch(batchId) {
  try {
    const batch = await api('/api/batches/' + batchId);
    const rows = batch.runs.length
      ? batch.runs.map((r) => '<tr><td>' + esc(r.file_name) + '</td>' +
        '<td><span class="badge badge-type">' + esc(typeName(r.doc_type)) + '</span></td>' +
        '<td class="num"><span class="score ' + scoreClass(r.score) + '">' + Number(r.score).toFixed(1) + '</span></td>' +
        '<td>' + gradeBadge(r.grade, r.score) + '</td>' +
        '<td><button class="btn btn-sm" data-batch-run="' + r.id + '">详情</button></td></tr>').join('')
      : '<tr><td colspan="5"><div class="empty">该批次没有成功稽核的文档</div></td></tr>';

    const modal = openModal('批次 #' + batch.id + ' · ' + (batch.project_name || '未命名项目'),
      '<div class="meta-chips" style="margin-bottom:12px">' +
      '<span class="tag">目录：' + esc(batch.source_dir) + '</span>' +
      '<span class="tag">文档 ' + batch.doc_total + ' 份</span>' +
      '<span class="tag">合格 ' + batch.doc_passed + ' 份</span>' +
      '<span class="tag">平均分 ' + Number(batch.avg_score).toFixed(1) + '</span>' +
      '<span class="tag">' + esc(batch.created_at) + '</span></div>' +
      '<table class="table"><thead><tr><th>文件</th><th>文档类型</th><th>得分</th><th>结论</th><th></th></tr></thead><tbody>' +
      rows + '</tbody></table>');

    modal.querySelectorAll('[data-batch-run]').forEach((btn) => {
      btn.addEventListener('click', () => openRunDetail(Number(btn.dataset.batchRun)));
    });
  } catch (err) { toast(err.message, true); }
}

function findingsHtml(findings) {
  const groups = state.dimensions.map((dim) => ({
    dim: dim,
    items: findings.filter((f) => f.dimension === dim.key),
  })).filter((g) => g.items.length);

  return groups.map((g) => {
    const passed = g.items.filter((f) => f.status === 'pass').length;
    const failed = g.items.filter((f) => f.status === 'fail').length;
    const skipped = g.items.filter((f) => f.status === 'skip').length;
    const rows = g.items.map((f) => {
      const dot = f.status === 'pass' ? 'dot-pass' : (f.status === 'fail' ? 'dot-fail' : 'dot-skip');
      return '<div class="finding"><span class="dot ' + dot + '"></span><div class="f-body">' +
        '<div class="f-head"><b>' + esc(f.rule_name) + '</b>' + sevBadge(f.severity) + statusBadge(f.status) + '</div>' +
        '<p class="f-msg">' + esc(f.message) + '</p>' +
        (f.evidence ? '<pre class="f-evidence">' + esc(f.evidence) + '</pre>' : '') +
        (f.location ? '<span class="f-loc">位置：' + esc(f.location) + '</span>' : '') +
        '</div></div>';
    }).join('');
    return '<div class="dim-block"><div class="dim-head"><h4>' + esc(g.dim.name) + '</h4>' +
      '<span class="stat-mini">通过 ' + passed + ' · 未通过 ' + failed + ' · 跳过 ' + skipped + '</span></div>' + rows + '</div>';
  }).join('');
}

function showRunModal(run) {
  if (!run) { toast('稽查记录为空', true); return; }
  if (run.status === 'error') {
    openModal('稽核失败 · ' + run.file_name,
      '<div class="err-box">' + esc(run.error || '文档解析失败') + '</div>' +
      '<p class="hint">请确认文件为有效的 .docx（Word 2007+）格式，旧版 .doc 需先另存为 .docx。</p>');
    return;
  }
  const meta = run.doc_meta || {};
  const chips = [];
  if (meta.word_count != null) chips.push('正文 ' + meta.word_count + ' 字');
  if (meta.paragraph_count != null) chips.push('段落 ' + meta.paragraph_count);
  if (meta.tables != null) chips.push('表格 ' + meta.tables);
  if (meta.figures != null) chips.push('插图 ' + meta.figures);
  if (meta.chapter_count != null) chips.push('一级章节 ' + meta.chapter_count);
  if (run.standard_version_no) chips.push('标准版本 v' + run.standard_version_no);

  const body =
    '<div class="run-summary">' +
    '<div class="score-ring" style="--p:' + Math.min(100, run.score) + ';--c:' + scoreColor(run.score) + '"><span>' + Number(run.score).toFixed(1) + '</span></div>' +
    '<div class="info"><h2>' + esc(run.file_name) + '</h2>' +
    '<div class="hint">' + esc(typeName(run.doc_type)) + (run.project_name ? ' · ' + esc(run.project_name) : '') +
    ' · ' + esc(run.created_at || '') + ' · 耗时 ' + (run.duration_ms || 0) + 'ms</div>' +
    '<div class="meta-chips">' + chips.map((c) => '<span class="tag">' + esc(c) + '</span>').join('') + '</div></div>' +
    '<div>' + gradeBadge(run.grade, run.score) + '</div></div>' +
    '<div class="grid grid-4" style="margin:16px 0">' +
    '<div class="stat"><div class="label">规则总数</div><div class="value">' + run.total_rules + '</div></div>' +
    '<div class="stat"><div class="label">通过</div><div class="value" style="color:#12855b">' + run.passed_rules + '</div></div>' +
    '<div class="stat"><div class="label">未通过</div><div class="value" style="color:#cf2b2b">' + run.failed_rules + '</div></div>' +
    '<div class="stat"><div class="label">跳过</div><div class="value" style="color:#7b869c">' + run.skipped_rules + '</div></div>' +
    '</div>' +
    '<div class="legend" style="margin-bottom:10px"><span><i style="background:#17a673"></i>通过</span>' +
    '<span><i style="background:#e03131"></i>未通过</span><span><i style="background:#b6bfd2"></i>跳过（条件不适用）</span></div>' +
    findingsHtml(run.findings || []);

  openModal('稽核详情', body);
}

async function openRunDetail(runId) {
  try {
    const run = await api('/api/runs/' + runId);
    showRunModal(run);
  } catch (err) { toast(err.message, true); }
}

/* ------------------------------------------------------------ 启动 */

async function boot() {
  try {
    const data = await api('/api/bootstrap');
    state.docTypes = data.doc_types;
    state.dimensions = data.dimensions;
    state.checkers = data.checkers;
    if (!state.standardType && state.docTypes.length) state.standardType = state.docTypes[0].code;
  } catch (err) {
    $('#main').innerHTML = '<div class="err-box">初始化失败：' + esc(err.message) + '</div>';
    return;
  }
  window.addEventListener('hashchange', route);
  route();
}

boot();
