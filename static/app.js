/* Ops Center - the ready-made frontend. You never need to touch this.
 * It only talks to YOUR API, with plain fetch(). Everything it shows comes from your backend.
 * All text goes in through textContent (never innerHTML) - that is how you avoid XSS. */
'use strict';

// ------------------------------------------------------------------ tiny helpers
const $ = (sel, root = document) => root.querySelector(sel);

function h(tag, props, ...kids) {
  const el = document.createElement(tag);
  for (const [key, val] of Object.entries(props || {})) {
    if (val == null || val === false) continue;
    if (key === 'class') el.className = val;
    else if (key.startsWith('on')) el.addEventListener(key.slice(2), val);
    else if (key.startsWith('--')) el.style.setProperty(key, val);
    else el.setAttribute(key, val === true ? '' : val);
  }
  for (const kid of kids.flat(Infinity)) if (kid != null && kid !== false) el.append(kid);
  return el;
}

const pad = (n) => String(n).padStart(2, '0');
const clock = (d = new Date()) => `${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}`;
const pct = (v) => (v == null ? '-' : `${v.toFixed(1)}%`);

function ago(iso) {
  if (!iso) return 'never';
  const s = Math.max(0, Math.round((Date.now() - new Date(iso).getTime()) / 1000));
  if (s < 5) return 'just now';
  if (s < 60) return `${s}s ago`;
  if (s < 3600) return `${Math.floor(s / 60)}m ago`;
  return new Date(iso).toLocaleString();
}

function uptime(sec) {
  const d = Math.floor(sec / 86400), hh = Math.floor((sec % 86400) / 3600), m = Math.floor((sec % 3600) / 60);
  return d ? `${d}d ${hh}h ${m}m` : hh ? `${hh}h ${m}m` : `${m}m`;
}

// ------------------------------------------------------------------ talking to the API
class ApiError extends Error {
  constructor(status, detail, retryAfter) {
    super(detail);
    this.status = status;
    this.retryAfter = retryAfter;
  }
}

function detailText(data) {
  if (data && typeof data === 'object' && 'detail' in data) {
    const d = data.detail;
    if (typeof d === 'string') return d;
    if (Array.isArray(d)) return d.map((e) => `${(e.loc || []).slice(1).join('.') || 'body'}: ${e.msg}`).join('\n');
    return JSON.stringify(d);
  }
  return typeof data === 'string' && data ? data : 'Something went wrong';
}

const TOKEN_KEY = 'ops_token';
let token = null;
try { token = sessionStorage.getItem(TOKEN_KEY); } catch { /* storage may be blocked - fine */ }
let me = null;

function setToken(value) {
  token = value;
  try { value ? sessionStorage.setItem(TOKEN_KEY, value) : sessionStorage.removeItem(TOKEN_KEY); } catch { /* ignore */ }
}

async function api(path, { method = 'GET', json, form, probe = false } = {}) {
  const headers = {};
  if (token) headers.Authorization = `Bearer ${token}`;
  if (probe) headers['x-mission-probe'] = '1'; // keeps our own polling out of the Traffic panel
  let body;
  if (json !== undefined) { headers['Content-Type'] = 'application/json'; body = JSON.stringify(json); }
  else if (form) body = new URLSearchParams(form);
  let res;
  try {
    res = await fetch(path, { method, headers, body });
  } catch {
    throw new ApiError(0, 'The server is not reachable. Is it running?');
  }
  let data = null;
  if (res.status !== 204) {
    const text = await res.text();
    try { data = text ? JSON.parse(text) : null; } catch { data = text; }
  }
  if (!res.ok) throw new ApiError(res.status, detailText(data), res.headers.get('retry-after'));
  return data;
}

// ------------------------------------------------------------------ app state + router
const state = { dev: false, bootId: null, timers: [], view: null };
const viewEl = $('#view');
const dlg = $('#dlg');

function every(ms, fn) { state.timers.push(setInterval(fn, ms)); }
function clearTimers() { state.timers.forEach(clearInterval); state.timers = []; state.onReload = null; }

function notice(kind, title, ...lines) {
  return h('div', { class: `notice ${kind}` }, h('h3', {}, title), ...lines.map((l) => h('p', {}, l)));
}

/** Show an API error in a friendly way. 501 = "your endpoint is not built yet" (not an error!). */
function showError(container, err) {
  let box;
  if (err.status === 501) {
    box = notice('', 'Not built yet', h('code', {}, err.message), 'Find this endpoint in app/routers/ (see the README table), build it, save - the page updates itself.');
  } else if (err.status === 401) {
    box = notice('', 'Please sign in', 'This part of the API needs a login.', h('button', { class: 'btn primary', onclick: () => openLogin() }, 'Sign in'));
  } else if (err.status === 403) {
    box = notice('err', 'Not allowed', err.message);
  } else {
    box = notice('err', err.status ? `The server answered ${err.status}` : 'Connection problem', err.message);
  }
  container.replaceChildren(box);
}

const VIEWS = { mission: viewMission, hosts: viewHosts, system: viewSystem, traffic: viewTraffic, admin: viewAdmin };

function route() {
  clearTimers();
  let name = (location.hash.match(/^#\/(\w+)/) || [])[1];
  if (!VIEWS[name] || (name === 'mission' || name === 'traffic') && !state.dev) name = state.dev ? 'mission' : 'hosts';
  document.querySelectorAll('.nav a[data-view]').forEach((a) => a.classList.toggle('active', a.dataset.view === name));
  viewEl.replaceChildren();
  VIEWS[name](viewEl);
}

window.addEventListener('hashchange', route);

// ------------------------------------------------------------------ dialogs
function openDialog(...nodes) {
  dlg.replaceChildren(...nodes);
  if (!dlg.open) dlg.showModal();
}
function closeDialog() { if (dlg.open) dlg.close(); }
dlg.addEventListener('click', (e) => { if (e.target === dlg) closeDialog(); });
dlg.addEventListener('close', () => { dlg.replaceChildren(); state.onDialogClose?.(); state.onDialogClose = null; });

// ------------------------------------------------------------------ login / register
function openLogin(startTab = 'login') {
  let tab = startTab;
  const err = h('div', { class: 'err-text', role: 'alert' });
  const user = h('input', { type: 'text', name: 'username', autocomplete: 'username', required: true, maxlength: 32 });
  const pass = h('input', { type: 'password', name: 'password', autocomplete: 'current-password', required: true, maxlength: 128 });
  const submit = h('button', { class: 'btn primary', type: 'submit' }, 'Sign in');
  const tabs = h('div', { class: 'tabs' });
  const heading = h('h2', {}, 'Sign in');

  function paint() {
    tabs.replaceChildren(
      h('button', { type: 'button', class: tab === 'login' ? 'on' : '', onclick: () => { tab = 'login'; paint(); } }, 'Log in'),
      h('button', { type: 'button', class: tab === 'register' ? 'on' : '', onclick: () => { tab = 'register'; paint(); } }, 'Create account'),
    );
    submit.textContent = tab === 'login' ? 'Log in' : 'Create account';
    pass.autocomplete = tab === 'login' ? 'current-password' : 'new-password';
    heading.textContent = tab === 'login' ? 'Sign in' : 'New account';
    err.textContent = '';
  }

  const form = h('form', {
    onsubmit: async (e) => {
      e.preventDefault();
      submit.disabled = true;
      err.textContent = '';
      try {
        const creds = { username: user.value.trim(), password: pass.value };
        if (tab === 'register') await api('/api/auth/register', { method: 'POST', json: creds });
        const out = await api('/api/auth/token', { method: 'POST', form: creds });
        setToken(out.access_token);
        await refreshMe();
        closeDialog();
        route();
      } catch (ex) {
        err.textContent = ex.status === 429
          ? `Too many attempts. Try again in ${ex.retryAfter || '?'} seconds.`
          : ex.status === 501 ? `Not built yet: ${ex.message}` : ex.message;
      } finally {
        submit.disabled = false;
      }
    },
  },
  tabs,
  h('label', {}, 'Username'), user,
  h('label', {}, 'Password'), pass,
  err,
  h('div', { class: 'actions' }, h('button', { class: 'btn', type: 'button', onclick: closeDialog }, 'Cancel'), submit));

  paint();
  openDialog(heading, form);
  user.focus();
}

async function refreshMe() {
  me = null;
  if (token) {
    try { me = await api('/api/auth/me', { probe: true }); } catch (ex) { if (ex.status === 401) setToken(null); }
  }
  $('#who').textContent = me ? `@${me.username}${me.is_admin ? ' (admin)' : ''}` : '';
  const btn = $('#auth-btn');
  btn.hidden = false;
  btn.textContent = token ? 'Sign out' : 'Sign in';
  $('#nav-admin').hidden = !(me && me.is_admin);
}

$('#auth-btn').addEventListener('click', () => {
  if (token) { setToken(null); me = null; refreshMe().then(route); } else openLogin();
});

// ------------------------------------------------------------------ dev status (live reload dot)
async function pollDev() {
  const dot = $('#live-dot'), text = $('#live-text');
  try {
    const info = await api('/_dev/info', { probe: true });
    if (state.bootId && info.boot_id !== state.bootId) {
      state.onReload?.();
      text.textContent = 'code reloaded';
      setTimeout(() => { text.textContent = 'server live'; }, 2500);
    } else if (text.textContent !== 'code reloaded') text.textContent = 'server live';
    state.bootId = info.boot_id;
    dot.className = 'dot on';
  } catch {
    dot.className = 'dot off';
    text.textContent = 'server down / restarting';
  }
}

// ------------------------------------------------------------------ view: Mission Control
function viewMission(root) {
  const s = { report: null, running: false, auto: true, onlyOpen: false, error: null };
  const out = h('div');
  root.append(h('h1', {}, 'Mission Control'),
    h('p', { class: 'lead' }, 'Live checks against your running code. Nothing is stored, nothing is scored: each line just asks "does it work right now?". Fix a red line, save the file, and this page checks again by itself.'),
    out);

  async function run() {
    if (s.running) return;
    s.running = true; paint();
    try { s.report = await api('/_dev/mission/run', { method: 'POST', probe: true }); s.error = null; }
    catch (ex) { s.error = ex; }
    s.running = false; paint();
  }

  function paint() {
    const r = s.report;
    const bar = h('div', { class: 'toolbar' },
      h('button', { class: 'btn primary', onclick: run, disabled: s.running }, s.running ? 'Running probes...' : 'Run all probes'),
      h('label', { class: 'switch' }, h('input', { type: 'checkbox', checked: s.auto, onchange: (e) => { s.auto = e.target.checked; } }), 'Re-run when my code reloads'),
      h('label', { class: 'switch' }, h('input', { type: 'checkbox', checked: s.onlyOpen, onchange: (e) => { s.onlyOpen = e.target.checked; paint(); } }), 'Only what is left to do'),
      r && h('span', { class: 'mono' }, `last run ${clock(new Date(r.ran_at))} - ${(r.duration_ms / 1000).toFixed(1)}s`));
    const parts = [bar];
    if (s.error) parts.push(notice('err', 'Could not run the probes', s.error.message));
    if (r) {
      parts.push(h('div', { class: 'ms-grid' }, r.milestones.map(milestoneCard)));
      const open = r.results.find((x) => x.status !== 'pass');
      if (!open) {
        parts.push(h('div', { class: 'banner' }, 'ALL SYSTEMS GREEN', h('small', {}, 'Every probe passes. Now write your own tests (pytest) and break things on purpose.')));
      } else {
        parts.push(h('div', { class: 'card next' }, h('span', { class: 'arrow' }, '>'),
          h('div', {}, h('div', {}, h('b', {}, 'Next up: '), `${open.id} ${open.title}`),
            open.message && h('div', { class: 'mono' }, open.message))));
      }
      for (const m of r.milestones) {
        const rows = r.results.filter((x) => x.milestone === m.id && (!s.onlyOpen || x.status !== 'pass'));
        if (!rows.length) continue;
        parts.push(h('h2', {}, `${m.id} - ${m.title}`), h('div', {}, rows.map(probeRow)));
      }
    } else if (!s.error) {
      parts.push(h('div', { class: 'empty' }, 'Running the probes for the first time...'));
    }
    out.replaceChildren(...parts);
  }

  function milestoneCard(m) {
    const done = m.passed === m.total;
    const segs = (r) => r.results.filter((x) => x.milestone === m.id).map((x) => h('span', { class: x.status }));
    return h('div', { class: `card ms ${done ? 'done' : ''}` },
      done && h('span', { class: 'chip pass badge' }, m.id === 'M4' ? 'hardened' : 'complete'),
      h('div', { class: 'id' }, m.id), h('div', { class: 'title' }, m.title),
      h('div', { class: 'count' }, `${m.passed}`, h('small', {}, ` / ${m.total}`)),
      h('div', { class: 'segs' }, segs(s.report)));
  }

  function probeRow(x) {
    const attack = x.kind === 'attack';
    const mark = { pass: 'OK', fail: 'X', todo: '...' }[x.status];
    const label = attack
      ? { pass: 'blocked', fail: 'BREACHED', todo: 'not built' }[x.status]
      : { pass: 'ok', fail: 'fails', todo: 'todo' }[x.status];
    return h('div', { class: `probe ${x.status}` },
      h('span', { class: 'mark' }, mark), h('span', { class: 'pid' }, x.id),
      h('div', {}, x.title, x.message && h('div', { class: 'msg' }, x.message)),
      h('span', { class: `chip ${x.status}` }, label));
  }

  state.onReload = () => { if (s.auto) setTimeout(run, 400); };
  paint();
  run();
}

// ------------------------------------------------------------------ view: Hosts
function meter(label, value) {
  const level = value == null ? '' : value >= 85 ? 'high' : value >= 60 ? 'mid' : '';
  return h('div', { class: `meter ${level}` }, h('span', {}, label),
    h('div', { class: 'bar' }, h('i', { '--v': value ?? 0 })), h('span', {}, pct(value)));
}

function viewHosts(root) {
  const PAGE = 24;
  const s = { q: '', items: [], more: false };
  const list = h('div');
  const search = h('input', { type: 'search', placeholder: 'Search hosts...', 'aria-label': 'Search hosts', maxlength: 50 });
  let debounce;
  search.addEventListener('input', () => { clearTimeout(debounce); debounce = setTimeout(() => { s.q = search.value.trim(); load(true); }, 250); });
  root.append(h('h1', {}, 'Hosts'),
    h('p', { class: 'lead' }, 'Machines that report to your Ops Center. Each host gets its own API key (shown once!) for the agent.'),
    h('div', { class: 'toolbar' }, search, h('button', { class: 'btn primary', onclick: openNewHost }, '+ New host')), list);

  async function load(reset = false) {
    try {
      const want = reset ? PAGE : Math.min(100, Math.max(PAGE, s.items.length));
      const params = new URLSearchParams({ limit: want, skip: 0 });
      if (s.q) params.set('q', s.q);
      s.items = await api(`/api/hosts?${params}`, { probe: true });
      s.more = s.items.length === want && want < 100 || s.items.length === 100;
      paint();
    } catch (ex) { showError(list, ex); }
  }

  async function loadMore() {
    const params = new URLSearchParams({ limit: PAGE, skip: s.items.length });
    if (s.q) params.set('q', s.q);
    try {
      const next = await api(`/api/hosts?${params}`);
      s.items = s.items.concat(next);
      s.more = next.length === PAGE;
      paint();
    } catch (ex) { showError(list, ex); }
  }

  function paint() {
    if (!s.items.length) {
      list.replaceChildren(h('div', { class: 'empty' }, s.q ? 'No host matches your search.' : 'No hosts yet. Create one with "+ New host", then start the agent.'));
      return;
    }
    list.replaceChildren(
      h('div', { class: 'grid' }, s.items.map(hostCard)),
      s.more && h('div', { class: 'toolbar' }, h('button', { class: 'btn', onclick: loadMore }, 'Load more')));
  }

  function hostCard(x) {
    return h('div', { class: 'card host', tabindex: 0, role: 'button', onclick: () => openDetail(x), onkeydown: (e) => { if (e.key === 'Enter') openDetail(x); } },
      h('header', {}, h('h3', {}, x.name), h('span', { class: `chip ${x.status}` }, x.status)),
      h('p', {}, x.description),
      meter('CPU', x.cpu_percent), meter('MEM', x.memory_percent), meter('DISK', x.disk_percent),
      h('div', { class: 'seen' }, `last seen: ${ago(x.last_seen)}`));
  }

  function openNewHost() {
    const err = h('div', { class: 'err-text', role: 'alert' });
    const name = h('input', { type: 'text', required: true, maxlength: 50, placeholder: 'web-1' });
    const desc = h('input', { type: 'text', maxlength: 200, placeholder: 'What does it do?' });
    const submit = h('button', { class: 'btn primary', type: 'submit' }, 'Create');
    openDialog(h('h2', {}, 'New host'), h('form', {
      onsubmit: async (e) => {
        e.preventDefault(); submit.disabled = true; err.textContent = '';
        try {
          const created = await api('/api/hosts', { method: 'POST', json: { name: name.value, description: desc.value } });
          showKey(created); load(true);
        } catch (ex) { err.textContent = ex.status === 501 ? `Not built yet: ${ex.message}` : ex.status === 401 ? 'Please sign in first.' : ex.message; }
        finally { submit.disabled = false; }
      },
    }, h('label', {}, 'Name'), name, h('label', {}, 'Description (optional)'), desc, err,
    h('div', { class: 'actions' }, h('button', { class: 'btn', type: 'button', onclick: closeDialog }, 'Cancel'), submit)));
    name.focus();
  }

  function showKey(created) {
    const cmd = `python agent/agent.py --url ${location.origin} --key ${created.api_key}`;
    const copy = h('button', { class: 'btn small', onclick: async () => { try { await navigator.clipboard.writeText(cmd); copy.textContent = 'copied'; } catch { copy.textContent = 'select + Ctrl+C'; } } }, 'copy');
    openDialog(h('h2', {}, `Host "${created.name}" created`),
      notice('', 'Save this API key now', 'It is shown exactly once. Your server only stores a hash of it - nobody (not even you) can read it again.'),
      h('div', { class: 'keybox' }, h('span', {}, created.api_key)),
      h('label', {}, 'Start the agent on that machine:'),
      h('div', { class: 'keybox' }, h('span', {}, cmd), copy),
      h('div', { class: 'actions' }, h('button', { class: 'btn primary', onclick: closeDialog }, 'Done')));
  }

  function openDetail(x) {
    const minutes = { value: 60 };
    const canvas = h('canvas', { class: 'chart', width: 600, height: 220 });
    const info = h('p', { class: 'mono' });
    const pick = h('select', { 'aria-label': 'Time range', onchange: () => { minutes.value = Number(pick.value); refresh(); } },
      [[15, 'last 15 min'], [60, 'last hour'], [360, 'last 6 hours'], [1440, 'last 24 hours']].map(([v, l]) => h('option', { value: v, selected: v === 60 }, l)));
    const err = h('div', { class: 'err-text', role: 'alert' });
    let armed = false;
    const del = h('button', { class: 'btn danger', onclick: async () => {
      if (!armed) { armed = true; del.textContent = 'Really delete? Click again'; return; }
      try { await api(`/api/hosts/${x.id}`, { method: 'DELETE' }); closeDialog(); load(true); }
      catch (ex) { err.textContent = ex.message; }
    } }, 'Delete host');

    async function refresh() {
      try {
        const [rows, fresh] = await Promise.all([
          api(`/api/hosts/${x.id}/metrics?minutes=${minutes.value}&limit=1000`, { probe: true }),
          api(`/api/hosts/${x.id}`, { probe: true }),
        ]);
        info.textContent = `${fresh.status} - last seen ${ago(fresh.last_seen)} - ${rows.length} measurements`;
        drawChart(canvas, rows);
        err.textContent = '';
      } catch (ex) { err.textContent = ex.status === 501 ? `Not built yet: ${ex.message}` : ex.message; }
    }
    openDialog(h('h2', {}, x.name), h('p', { class: 'lead' }, x.description || 'No description'), info,
      h('div', { class: 'toolbar' }, pick),
      h('div', { class: 'legend' }, h('span', {}, h('b', { class: 'c-cpu' }), 'CPU'), h('span', {}, h('b', { class: 'c-mem' }), 'Memory'), h('span', {}, h('b', { class: 'c-disk' }), 'Disk')),
      canvas, err, h('div', { class: 'actions' }, del, h('button', { class: 'btn', onclick: closeDialog }, 'Close')));
    legendColors();
    refresh();
    const t = setInterval(refresh, 5000);
    state.onDialogClose = () => clearInterval(t);
  }

  every(5000, () => { if (!dlg.open && s.items.length <= 100) load(); });
  load(true);
}

const SERIES = [['cpu_percent', '#35e0a1'], ['memory_percent', '#4cc9f0'], ['disk_percent', '#ffb84d']];

function legendColors() {
  // The legend squares get their colour through a CSS variable (CSP forbids inline style attributes).
  [['c-cpu', SERIES[0][1]], ['c-mem', SERIES[1][1]], ['c-disk', SERIES[2][1]]].forEach(([cls, col]) => {
    const el = $(`.${cls}`); if (el) el.style.background = col;
  });
}

function drawChart(canvas, rows) {
  const dpr = window.devicePixelRatio || 1;
  const w = canvas.clientWidth || 600, hgt = canvas.clientHeight || 220;
  canvas.width = w * dpr; canvas.height = hgt * dpr;
  const g = canvas.getContext('2d');
  g.scale(dpr, dpr);
  const L = 36, R = 10, T = 10, B = 20, pw = w - L - R, ph = hgt - T - B;
  g.font = '11px ui-monospace, Consolas, monospace';
  g.strokeStyle = '#243049'; g.fillStyle = '#55667f'; g.lineWidth = 1;
  for (const v of [0, 25, 50, 75, 100]) {
    const y = T + ph - (v / 100) * ph;
    g.beginPath(); g.moveTo(L, y); g.lineTo(w - R, y); g.stroke();
    g.fillText(String(v), 6, y + 4);
  }
  if (rows.length < 2) {
    g.fillStyle = '#8294b3';
    g.fillText(rows.length ? 'only one measurement so far...' : 'no measurements in this time range', L + 12, T + ph / 2);
    return;
  }
  const t0 = new Date(rows[0].ts).getTime(), t1 = new Date(rows[rows.length - 1].ts).getTime() || t0 + 1;
  const span = Math.max(1, t1 - t0);
  for (const [key, color] of SERIES) {
    g.strokeStyle = color; g.lineWidth = 2; g.beginPath();
    rows.forEach((r, i) => {
      const x = L + ((new Date(r.ts).getTime() - t0) / span) * pw, y = T + ph - (r[key] / 100) * ph;
      i ? g.lineTo(x, y) : g.moveTo(x, y);
    });
    g.stroke();
  }
  g.fillStyle = '#55667f';
  g.fillText(clock(new Date(t0)), L, hgt - 5);
  const end = clock(new Date(t1));
  g.fillText(end, w - R - g.measureText(end).width, hgt - 5);
}

// ------------------------------------------------------------------ view: This machine
function viewSystem(root) {
  const s = { sort: 'cpu', limit: 5 };
  const top = h('div'), procs = h('div');
  const sort = h('select', { 'aria-label': 'Sort processes by', onchange: () => { s.sort = sort.value; load(); } },
    ['cpu', 'memory', 'name'].map((v) => h('option', { value: v }, `sort by ${v}`)));
  const limit = h('select', { 'aria-label': 'How many processes', onchange: () => { s.limit = Number(limit.value); load(); } },
    [5, 10, 25].map((v) => h('option', { value: v }, `top ${v}`)));
  root.append(h('h1', {}, 'This machine'),
    h('p', { class: 'lead' }, 'Live numbers from the computer your server runs on. Your endpoints deliver them; Python\'s psutil measures them.'),
    top, h('h2', {}, 'Processes'), h('div', { class: 'toolbar' }, sort, limit), procs);

  function gauge(label, v) {
    const color = v >= 85 ? 'var(--red)' : v >= 60 ? 'var(--amber)' : 'var(--green)';
    return h('div', { class: 'card gauge' },
      h('div', { class: 'ring-wrap' }, h('div', { class: 'ring', '--v': v, '--c': color }), h('div', { class: 'num' }, `${Math.round(v)}%`)),
      h('div', { class: 'lab' }, label));
  }
  const fact = (k, v) => h('div', { class: 'card fact' }, h('div', { class: 'k' }, k), h('div', { class: 'v' }, String(v)));

  async function load() {
    try {
      const x = await api('/api/system', { probe: true });
      top.replaceChildren(
        h('div', { class: 'gauges' }, gauge('CPU', x.cpu_percent), gauge('Memory', x.memory_percent), gauge('Disk', x.disk_percent)),
        h('div', { class: 'facts' }, fact('Hostname', x.hostname), fact('System', x.os), fact('CPU cores', x.cpu_count), fact('Uptime', uptime(x.uptime_seconds))));
    } catch (ex) { showError(top, ex); }
    try {
      const rows = await api(`/api/system/processes?limit=${s.limit}&sort_by=${s.sort}`, { probe: true });
      procs.replaceChildren(h('table', {}, h('thead', {}, h('tr', {}, h('th', {}, 'PID'), h('th', {}, 'Name'), h('th', { class: 'num' }, 'CPU'), h('th', { class: 'num' }, 'Memory'))),
        h('tbody', {}, rows.map((p) => h('tr', {}, h('td', {}, p.pid), h('td', {}, p.name), h('td', { class: 'num' }, pct(p.cpu_percent)), h('td', { class: 'num' }, pct(p.memory_percent)))))));
    } catch (ex) { showError(procs, ex); }
  }
  every(3000, load);
  load();
}

// ------------------------------------------------------------------ view: Traffic (dev only)
function viewTraffic(root) {
  const s = { seq: 0, items: [], paused: false, errorsOnly: false, open: new Set() };
  const list = h('div');
  root.append(h('h1', {}, 'Traffic'),
    h('p', { class: 'lead' }, 'Every request your API receives, live - this is what a "network tab" or an attacker\'s proxy sees. Passwords and tokens are masked here on purpose: logs are a classic place for secrets to leak.'),
    h('div', { class: 'toolbar' },
      h('button', { class: 'btn', onclick: () => { s.items = []; s.open.clear(); paint(); } }, 'Clear'),
      h('label', { class: 'switch' }, h('input', { type: 'checkbox', onchange: (e) => { s.paused = e.target.checked; } }), 'Pause'),
      h('label', { class: 'switch' }, h('input', { type: 'checkbox', onchange: (e) => { s.errorsOnly = e.target.checked; paint(); } }), 'Only errors')),
    list);

  function pretty(text) {
    if (!text) return '(empty)';
    try { return JSON.stringify(JSON.parse(text), null, 2); } catch { return text; }
  }

  function paint() {
    const shown = s.items.filter((i) => !s.errorsOnly || i.status >= 400).slice(-200).reverse();
    if (!shown.length) { list.replaceChildren(h('div', { class: 'empty' }, 'Nothing yet - use the other pages, or poke the API from /docs.')); return; }
    list.replaceChildren(...shown.map((i) => {
      const cls = i.status < 300 ? 'ok' : i.status < 400 ? 'warn' : i.status < 500 ? 'warn' : 'bad';
      const pre = h('pre', {}, h('b', {}, 'REQUEST'), pretty(i.request), h('b', {}, 'RESPONSE'), pretty(i.response));
      pre.hidden = !s.open.has(i.seq);
      return h('div', { class: 'req' },
        h('button', { type: 'button', 'aria-expanded': String(!pre.hidden), onclick: () => { pre.hidden = !pre.hidden; pre.hidden ? s.open.delete(i.seq) : s.open.add(i.seq); } },
          h('span', { class: 't' }, i.time), h('span', { class: `m ${i.method}` }, i.method), h('span', { class: 'p' }, i.path),
          h('span', { class: `s ${i.status >= 500 ? 'bad' : cls}` }, i.status), h('span', { class: 'ms' }, `${i.ms}ms`)), pre);
    }));
  }

  async function poll() {
    if (s.paused) return;
    try {
      const out = await api(`/_dev/traffic?after=${s.seq}`, { probe: true });
      if (out.seq < s.seq) { s.items = []; s.seq = 0; } // server restarted
      if (out.items.length) { s.items = s.items.concat(out.items).slice(-400); paint(); }
      s.seq = out.seq;
    } catch { /* server restarting - try again next tick */ }
  }
  paint();
  every(1000, poll);
  poll();
}

// ------------------------------------------------------------------ view: Admin
async function viewAdmin(root) {
  const box = h('div');
  root.append(h('h1', {}, 'Admin'), h('p', { class: 'lead' }, 'All registered users. Only admins may see this page - and your API enforces that, not this page.'), box);
  try {
    const users = await api('/api/admin/users');
    box.replaceChildren(h('table', {}, h('thead', {}, h('tr', {}, h('th', {}, 'ID'), h('th', {}, 'Username'), h('th', {}, 'Admin'), h('th', {}, 'Created'))),
      h('tbody', {}, users.map((u) => h('tr', {}, h('td', {}, u.id), h('td', {}, u.username), h('td', {}, u.is_admin ? 'yes' : 'no'), h('td', {}, new Date(u.created_at).toLocaleString()))))));
  } catch (ex) { showError(box, ex); }
}

// ------------------------------------------------------------------ start
(async function start() {
  try {
    const info = await api('/_dev/info', { probe: true });
    state.dev = true; state.bootId = info.boot_id;
    ['#nav-mission', '#nav-traffic', '#nav-docs', '#live'].forEach((sel) => { $(sel).hidden = false; });
    $('#live-dot').className = 'dot on'; $('#live-text').textContent = 'server live';
    setInterval(pollDev, 2000);
  } catch { /* not in dev mode: the dev tools simply do not exist */ }
  await refreshMe();
  if (!location.hash) location.hash = state.dev ? '#/mission' : '#/hosts';
  route();
})();
