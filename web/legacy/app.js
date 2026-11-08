'use strict';
/* Fiber@Home Knowledge Intelligence Platform — front end. All data comes from the API; nothing is stored locally except the CSRF token for the tab. Text is always rendered with textContent. */
const $ = (s, r = document) => r.querySelector(s);
const el = (tag, attrs = {}, ...kids) => {
  const n = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) {
    if (k === 'class') n.className = v; else if (k.startsWith('on')) n.addEventListener(k.slice(2), v); else if (v !== false && v != null) n.setAttribute(k, v === true ? '' : v);
  }
  for (const c of kids.flat()) if (c != null && c !== false) n.append(c.nodeType ? c : document.createTextNode(String(c)));
  return n;
};
const ICON = {
  overview: '<rect x="3.5" y="3.5" width="7" height="7" rx="1.5"/><rect x="13.5" y="3.5" width="7" height="7" rx="1.5"/><rect x="3.5" y="13.5" width="7" height="7" rx="1.5"/><rect x="13.5" y="13.5" width="7" height="7" rx="1.5"/>',
  assistant: '<path d="M21 12a8 8 0 0 1-11.6 7.1L4 20l1-4.6A8 8 0 1 1 21 12z"/>',
  vault: '<path d="M4 5h4v14H4zM10 5h4v14h-4zM16.5 6l3.5 1-3 12-3.5-1z"/>',
  approvals: '<path d="M5 12l4 4 10-10"/>',
  audit: '<path d="M6 3h9l4 4v14H6zM14 3v5h5M9 13h6M9 17h6"/>',
};
const svg = k => { const s = el('span'); s.innerHTML = `<svg viewBox="0 0 24 24" aria-hidden="true">${ICON[k]}</svg>`; return s.firstChild; };

let csrf = sessionStorage.getItem('csrf') || '';
let me = null;
const toast = (msg, kind = '') => { const t = el('div', { class: 'toast ' + kind }, msg); $('#toasts').append(t); setTimeout(() => t.remove(), 5000); };

async function api(path, { method = 'GET', body } = {}) {
  const r = await fetch('/api' + path, { method, credentials: 'same-origin', headers: { ...(body ? { 'Content-Type': 'application/json' } : {}), ...(csrf ? { 'X-CSRF-Token': csrf } : {}) }, body: body ? JSON.stringify(body) : undefined });
  let data = null; try { data = await r.json(); } catch { /* empty body */ }
  if (r.status === 401 && me) { me = null; sessionStorage.removeItem('csrf'); render(); toast('Your session has ended. Please sign in again.', 'bad'); }
  if (!r.ok) { const d = data && data.detail; throw new Error(typeof d === 'string' ? d : Array.isArray(d) ? 'Please check the highlighted fields and try again.' : 'Something went wrong. Please try again.'); }
  return data;
}

const can = (perm, dept) => {
  const roles = me.roles, ok = { write: ['editor', 'admin'], review: ['reviewer', 'admin'] }[perm];
  return roles.some(r => ok.includes(r.role) && (r.dept_id === null || dept == null || r.dept_id === dept));
};
const isAdmin = () => me.roles.some(r => r.role === 'admin' && r.dept_id === null);

function confirmDialog(title, text, okLabel) {
  return new Promise(res => {
    const prev = document.activeElement;
    const done = v => { m.remove(); document.removeEventListener('keydown', kd, true); prev && prev.focus(); res(v); };
    const ok = el('button', { class: 'btn bad', onclick: () => done(true) }, okLabel), cancel = el('button', { class: 'btn', onclick: () => done(false) }, 'Cancel');
    const m = el('div', { class: 'modal', onclick: e => { if (e.target === m) done(false); } }, el('div', { class: 'card', role: 'alertdialog', 'aria-modal': 'true', 'aria-labelledby': 'cd-t' }, el('h2', { id: 'cd-t' }, title), el('p', { class: 'sub' }, text), el('div', { class: 'row' }, cancel, ok)));
    const kd = e => { if (e.key === 'Escape') { e.stopPropagation(); done(false); } else if (e.key === 'Tab') { e.preventDefault(); (document.activeElement === ok ? cancel : ok).focus(); } };
    document.addEventListener('keydown', kd, true); document.body.append(m); cancel.focus();
  });
}

/* ------------------------------------------------------------ views */
const VIEWS = {
  overview: async () => {
    const d = await api('/dashboard'), max = Math.max(1, ...d.by_department.map(x => x.entries));
    const kpi = (l, v) => el('div', { class: 'kpi' }, el('span', {}, l), el('b', {}, v));
    return el('div', {},
      el('h1', {}, 'Executive overview'), el('p', { class: 'sub' }, 'Live figures from the central database.'),
      el('div', { class: 'kpis' }, kpi('Approved entries', d.approved_entries), kpi('Pending approvals', d.pending_approvals), kpi('Searches (30 days)', d.searches_30d), kpi('Unanswered (30 days)', d.unanswered_30d), kpi('Open knowledge gaps', d.open_gaps), kpi('Documents overdue review', d.documents_overdue_review)),
      el('div', { class: 'grid2' },
        el('section', { class: 'card', 'aria-labelledby': 'h-d' }, el('h2', { id: 'h-d' }, 'Entries by department'),
          ...d.by_department.map(x => el('div', { class: 'bar' }, el('span', {}, x.name.split(/[ &(]/)[0]), el('span', { class: 't' }, el('i', { style: `width:${x.entries ? Math.max(2, x.entries / max * 100) : 0}%` })), el('b', {}, x.entries)))),
        el('div', { style: 'display:grid;gap:16px' },
          el('section', { class: 'card' }, el('h2', {}, 'Most searched (30 days)'), d.top_queries_30d.length ? el('ul', { class: 'list' }, d.top_queries_30d.map(q => el('li', {}, q.query, el('small', {}, q.n + (q.n === 1 ? ' search' : ' searches'))))) : el('p', { class: 'empty' }, 'No searches yet. Questions asked in the assistant appear here.')),
          el('section', { class: 'card' }, el('h2', {}, 'Answer feedback'), el('p', { class: 'empty' }, `${d.feedback.helpful} helpful · ${d.feedback.not_helpful} not helpful`)),
          el('section', { class: 'card' }, el('h2', {}, 'Recent updates'), d.recent_updates.length ? el('ul', { class: 'list' }, d.recent_updates.map(u => el('li', {}, u.title, el('small', {}, `${u.dept_id} · ${u.status}`)))) : el('p', { class: 'empty' }, 'No team updates yet.')))));
  },

  assistant: async () => {
    const log = el('div', { class: 'chat', 'aria-live': 'polite' }), inp = el('input', { type: 'text', 'aria-label': 'Ask a question', placeholder: 'Ask about Fiber@Home, the BTRC rules or the network…', maxlength: 500 }), go = el('button', { class: 'btn pri', type: 'submit' }, 'Ask');
    const form = el('form', { class: 'ask', onsubmit: async e => {
      e.preventDefault(); const q = inp.value.trim(); if (q.length < 2) return; inp.value = ''; log.append(el('div', { class: 'q' }, q)); go.disabled = true;
      const pending = el('div', { class: 'a' }, 'Searching approved knowledge…'); log.append(pending);
      try {
        const r = await api('/ask', { method: 'POST', body: { query: q } });
        const box = el('div', { class: 'a' });
        if (!r.answered) box.append(el('p', {}, r.message));
        else {
          box.append(el('p', {}, r.answer));
          if (r.conflicts_with.length) box.append(el('div', { class: 'warnbox' }, 'Sources disagree on this topic. Entries to compare: ' + r.conflicts_with.join(', ')));
          box.append(el('div', { class: 'src' }, el('b', {}, 'Sources used'), ...r.citations.slice(0, 4).map(c => el('span', { class: 'cite' }, el('b', {}, `${c.entry_id} `), `${c.title} — ${c.source}${c.reference ? ' (' + c.reference + ')' : ''}`))));
          const fb = async h => { try { await api('/feedback', { method: 'POST', body: { search_event: r.search_event, helpful: h } }); toast('Thanks for the feedback.', 'ok'); fbRow.remove(); } catch (x) { toast(x.message, 'bad'); } };
          var fbRow = el('div', { class: 'row', style: 'margin-top:10px' }, el('button', { class: 'btn sm', onclick: () => fb(true) }, 'Helpful'), el('button', { class: 'btn sm', onclick: () => fb(false) }, 'Not helpful')); box.append(fbRow);
        }
        pending.replaceWith(box);
      } catch (x) { pending.replaceWith(el('div', { class: 'a err' }, x.message)); }
      go.disabled = false; inp.focus();
    } }, inp, go);
    return el('div', {}, el('h1', {}, 'AI Knowledge Assistant'), el('p', { class: 'sub' }, 'Answers are quoted from approved entries you are allowed to read, with their sources. If nothing supports an answer, it says so.'), log, form);
  },

  vault: async () => {
    const depts = (await api('/dashboard')).by_department; let dept = '', q = '', offset = 0;
    const body = el('tbody'), more = el('button', { class: 'btn', onclick: () => load(true) }, 'Load more'), count = el('p', { class: 'sub', 'aria-live': 'polite' });
    async function load(append) {
      if (!append) { offset = 0; body.replaceChildren(); }
      try {
        const rows = await api(`/entries?limit=50&offset=${offset}${dept ? '&dept=' + dept : ''}${q ? '&q=' + encodeURIComponent(q) : ''}`);
        rows.forEach(r => body.append(el('tr', {}, el('td', {}, r.id), el('td', {}, el('button', { class: 'btn sm', onclick: () => openEntry(r.id) }, r.title)), el('td', {}, r.dept_id), el('td', {}, r.source), el('td', {}, el('span', { class: 'pill ' + r.status }, r.status)))));
        offset += rows.length; more.hidden = rows.length < 50; count.textContent = offset ? `${offset} shown` : 'No entries match.';
      } catch (x) { toast(x.message, 'bad'); }
    }
    const sel = el('select', { 'aria-label': 'Department', onchange: e => { dept = e.target.value; load(); } }, el('option', { value: '' }, 'All departments'), depts.map(d => el('option', { value: d.id }, `${d.name} (${d.entries})`)));
    let t; const search = el('input', { type: 'search', 'aria-label': 'Filter by title', placeholder: 'Filter by title…', oninput: e => { clearTimeout(t); t = setTimeout(() => { q = e.target.value.trim(); load(); }, 250); } });
    load();
    return el('div', {}, el('h1', {}, 'Knowledge Vault'), el('p', { class: 'sub' }, 'Every published entry you may read, with its department and source.'), el('div', { class: 'tools' }, sel, search), count,
      el('div', { class: 'card', style: 'overflow:auto' }, el('table', { class: 'tbl' }, el('thead', {}, el('tr', {}, ['ID', 'Title', 'Dept', 'Source', 'Status'].map(h => el('th', { scope: 'col' }, h)))), body)), el('div', { style: 'margin-top:12px' }, more));
  },

  approvals: async () => {
    const wrap = el('div', {}); const deptOpts = (await api('/dashboard')).by_department;
    async function section(status, title, actions) {
      const rows = await api('/entries?status=' + status + '&limit=100');
      return el('section', { class: 'card', style: 'margin-bottom:16px' }, el('h2', {}, `${title} (${rows.length})`),
        rows.length ? el('table', { class: 'tbl' }, el('tbody', {}, rows.map(r => el('tr', {}, el('td', {}, r.id), el('td', {}, r.title, el('small', { style: 'display:block;color:var(--mut)' }, `${r.dept_id} · v${r.version}`)), el('td', {}, el('div', { class: 'row' }, actions(r))))))) : el('p', { class: 'empty' }, 'Nothing here.'));
    }
    const act = (label, path, extra = {}, cls = '') => el('button', { class: 'btn sm ' + cls, onclick: async () => { try { await api(path, extra.body ? { method: 'POST', body: extra.body } : { method: 'POST' }); toast(extra.ok || 'Done.', 'ok'); show('approvals'); } catch (x) { toast(x.message, 'bad'); } } }, label);
    const newBtn = can('write') ? el('button', { class: 'btn pri', onclick: () => newEntry(deptOpts) }, 'New entry') : null;
    wrap.append(el('div', { class: 'row', style: 'justify-content:space-between;align-items:flex-start' }, el('div', {}, el('h1', {}, 'Update & approval centre'), el('p', { class: 'sub' }, 'Draft → Review → Approved → Published. The author cannot approve their own entry.')), newBtn));
    try {
      wrap.append(await section('draft', 'Drafts', r => can('write', r.dept_id) ? [act('Submit for review', `/entries/${r.id}/submit`, { ok: 'Submitted for review.' })] : []));
      wrap.append(await section('review', 'Awaiting review', r => can('review', r.dept_id) ? [act('Approve', `/entries/${r.id}/review`, { body: { approve: true }, ok: 'Approved.' }, 'pri'), act('Return to draft', `/entries/${r.id}/review`, { body: { approve: false }, ok: 'Returned to draft.' })] : []));
      wrap.append(await section('approved', 'Approved, ready to publish', r => can('review', r.dept_id) ? [act('Publish', `/entries/${r.id}/publish`, { ok: 'Published.' }, 'pri')] : []));
    } catch (x) { wrap.append(el('p', { class: 'err' }, x.message)); }
    return wrap;
  },

  audit: async () => {
    const [log, v] = await Promise.all([api('/audit?limit=200'), api('/audit/verify')]);
    return el('div', {}, el('h1', {}, 'Audit log'), el('p', { class: 'sub' }, v.intact ? 'Integrity check passed: the log has not been altered.' : 'WARNING: the log failed its integrity check at entries ' + v.broken_at.join(', ')),
      el('div', { class: 'card', style: 'overflow:auto' }, el('table', { class: 'tbl' }, el('thead', {}, el('tr', {}, ['When', 'Who', 'Action', 'Object'].map(h => el('th', { scope: 'col' }, h)))), el('tbody', {}, log.map(l => el('tr', {}, el('td', {}, new Date(l.at).toLocaleString()), el('td', {}, l.actor_email || '—'), el('td', {}, l.action), el('td', {}, [l.object_type, l.object_id].filter(Boolean).join(' ')))))))); 
  },
};

async function openEntry(id) {
  try {
    const e = await api('/entries/' + id), close = () => m.remove();
    const m = el('div', { class: 'modal', onclick: ev => { if (ev.target === m) close(); } }, el('div', { class: 'card', role: 'dialog', 'aria-modal': 'true', 'aria-labelledby': 'e-t' },
      el('h2', { id: 'e-t' }, e.title), el('p', { class: 'sub' }, `${e.id} · ${e.dept_id} · version ${e.version} · ${e.status}`), el('p', {}, e.body),
      el('p', { class: 'sub', style: 'margin-top:14px' }, `Source: ${e.source}${e.reference ? ' (' + e.reference + ')' : ''}`),
      el('div', { class: 'row' }, can('write', e.dept_id) && e.status === 'published' ? el('button', { class: 'btn', onclick: async () => { try { const r = await api(`/entries/${e.id}/revise`, { method: 'POST' }); toast('Revision ' + r.id + ' created as a draft.', 'ok'); close(); } catch (x) { toast(x.message, 'bad'); } } }, 'Create revision') : null,
        can('review', e.dept_id) && e.status === 'published' ? el('button', { class: 'btn bad', onclick: async () => { if (await confirmDialog('Archive this entry?', 'It will no longer be used for answers. You can restore it only by creating a new entry.', 'Archive')) { try { await api(`/entries/${e.id}/archive`, { method: 'POST' }); toast('Entry archived.', 'ok'); close(); show('vault'); } catch (x) { toast(x.message, 'bad'); } } } }, 'Archive') : null,
        el('button', { class: 'btn', onclick: close }, 'Close'))));
    document.addEventListener('keydown', function k(ev) { if (ev.key === 'Escape') { close(); document.removeEventListener('keydown', k); } });
    document.body.append(m); $('button', m).focus();
  } catch (x) { toast(x.message, 'bad'); }
}

function newEntry(depts) {
  const allowed = depts.filter(d => can('write', d.id)), close = () => m.remove(), err = el('p', { class: 'err', role: 'alert' });
  const f = { dept: el('select', { id: 'n-d' }, allowed.map(d => el('option', { value: d.id }, d.name))), cat: el('input', { id: 'n-c', required: true, maxlength: 200 }), title: el('input', { id: 'n-t', required: true, minlength: 3, maxlength: 300 }), body: el('textarea', { id: 'n-b', rows: 6, required: true, minlength: 3 }), src: el('input', { id: 'n-s', required: true, maxlength: 300 }), ref: el('input', { id: 'n-r', maxlength: 300 }) };
  const m = el('div', { class: 'modal' }, el('form', { class: 'card', 'aria-labelledby': 'n-h', onsubmit: async e => {
    e.preventDefault(); err.textContent = '';
    try { const r = await api('/entries', { method: 'POST', body: { dept_id: f.dept.value, category: f.cat.value, title: f.title.value, body: f.body.value, source: f.src.value, reference: f.ref.value || null, kind: 'team' } }); toast(`Draft ${r.id} saved.`, 'ok'); close(); show('approvals'); } catch (x) { err.textContent = x.message; }
  } }, el('h2', { id: 'n-h' }, 'New knowledge entry'),
    el('label', { for: 'n-d' }, 'Department'), f.dept, el('label', { for: 'n-c' }, 'Category'), f.cat, el('label', { for: 'n-t' }, 'Title'), f.title, el('label', { for: 'n-b' }, 'Content'), f.body, el('label', { for: 'n-s' }, 'Source document'), f.src, el('label', { for: 'n-r' }, 'Reference (page or section, optional)'), f.ref, err,
    el('div', { class: 'row', style: 'margin-top:14px' }, el('button', { class: 'btn pri', type: 'submit' }, 'Save draft'), el('button', { class: 'btn', type: 'button', onclick: close }, 'Cancel'))));
  document.body.append(m); f.dept.focus();
}

/* ------------------------------------------------------------ shell */
const NAV = [['overview', 'Overview'], ['assistant', 'AI Assistant'], ['vault', 'Knowledge Vault'], ['approvals', 'Updates & Approvals', () => can('write') || can('review')], ['audit', 'Audit log', isAdmin]];
let view = 'overview';
async function show(v) {
  view = v; const main = $('#main'); if (!main) return;
  document.querySelectorAll('.nav').forEach(b => b.toggleAttribute('aria-current', b.dataset.v === v) || (b.dataset.v !== v && b.removeAttribute('aria-current')));
  document.querySelectorAll('.nav').forEach(b => { if (b.dataset.v === v) b.setAttribute('aria-current', 'page'); });
  $('.crumb b').textContent = NAV.find(n => n[0] === v)[1]; history.replaceState(null, '', '#' + v);
  main.replaceChildren(el('p', { class: 'spin' }, 'Loading…'));
  try { main.replaceChildren(await VIEWS[v]()); main.focus(); } catch (x) { main.replaceChildren(el('p', { class: 'err', role: 'alert' }, x.message), el('button', { class: 'btn', onclick: () => show(v) }, 'Try again')); }
}
function renderShell() {
  const items = NAV.filter(n => !n[2] || n[2]());
  $('#root').replaceChildren(el('div', { class: 'shell' },
    el('nav', { class: 'side', 'aria-label': 'Main' }, el('div', { class: 'brand' }, 'Fiber@Home', el('small', {}, 'Knowledge Intelligence Platform')),
      items.map(([k, l]) => el('button', { class: 'nav', 'data-v': k, onclick: () => show(k) }, svg(k), l)), el('div', { class: 'sp' }),
      el('div', { class: 'who' }, el('b', {}, me.name), me.roles.map(r => `${r.role}${r.dept_id ? ' · ' + r.dept_id : ''}`).join(', ') || 'No access granted yet', el('div', { style: 'margin-top:8px' }, el('button', { class: 'btn sm', onclick: logout }, 'Sign out')))),
    el('div', {}, el('div', { class: 'top' }, el('div', { class: 'crumb' }, 'Fiber@Home / ', el('b', {}, ''))), el('main', { id: 'main', tabindex: '-1' }))));
  const h = location.hash.slice(1); show(items.some(n => n[0] === h) ? h : 'overview');
}
async function logout() { try { await api('/auth/logout', { method: 'POST' }); } catch { /* already gone */ } me = null; csrf = ''; sessionStorage.removeItem('csrf'); render(); }
function renderLogin() {
  const err = el('p', { class: 'err', role: 'alert' }), email = el('input', { id: 'l-e', type: 'email', autocomplete: 'username', required: true }), pw = el('input', { id: 'l-p', type: 'password', autocomplete: 'current-password', required: true }), btn = el('button', { class: 'btn pri', type: 'submit', style: 'width:100%;margin-top:18px' }, 'Sign in');
  $('#root').replaceChildren(el('div', { class: 'login' },
    el('section', { class: 'art' }, el('h1', {}, 'Connecting our future with ', el('span', { class: 'acc' }, 'light')), el('p', {}, 'One governed source of truth for every Fiber@Home team. Every answer is drawn from approved documents you are permitted to read, and cites its source.'), el('ul', {}, el('li', {}, 'Approved, versioned knowledge'), el('li', {}, 'Department-level access control'), el('li', {}, 'Every action audited'))),
    el('section', { class: 'form' }, el('form', { class: 'card', 'aria-labelledby': 'l-h', onsubmit: async e => {
      e.preventDefault(); err.textContent = ''; btn.disabled = true;
      try { const r = await api('/auth/login', { method: 'POST', body: { email: email.value, password: pw.value } }); csrf = r.csrf_token; sessionStorage.setItem('csrf', csrf); me = await api('/auth/me'); renderShell(); }
      catch (x) { err.textContent = x.message; pw.value = ''; pw.focus(); } btn.disabled = false;
    } }, el('h1', { id: 'l-h' }, 'Sign in'), el('p', { class: 'sub' }, 'Use your Fiber@Home account.'), el('label', { for: 'l-e' }, 'Work email'), email, el('label', { for: 'l-p' }, 'Password'), pw, err, btn))));
  email.focus();
}
async function render() { if (me) return renderShell(); try { me = await api('/auth/me'); renderShell(); } catch { me = null; renderLogin(); } }
render();
