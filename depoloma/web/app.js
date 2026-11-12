/* Depoloma UI — plain JavaScript, no build step, no external requests.
   Names coming from the disk are always inserted as text (never as HTML). */
(() => {
  'use strict';

  const TOKEN = document.querySelector('meta[name="depoloma-token"]').content;
  const VERSION = document.querySelector('meta[name="depoloma-version"]').content;
  const I18N = window.DEPOLOMA_I18N;
  const $ = (sel, root) => (root || document).querySelector(sel);
  const NS = 'http://www.w3.org/2000/svg';
  const DAY = 86400;

  const store = {
    get(k, d) { try { return localStorage.getItem('depoloma.' + k) || d; } catch (e) { return d; } },
    set(k, v) { try { localStorage.setItem('depoloma.' + k, v); } catch (e) { /* private mode */ } },
  };

  const state = {
    lang: store.get('lang', (navigator.language || 'en').toLowerCase().startsWith('tr') ? 'tr' : 'en'),
    theme: store.get('theme', window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light'),
    meta: null,
    status: { state: 'idle' },
    summary: null,
    view: 'welcome',
    pick: null,
    ex: { id: null, node: null },
    find: { act: 'all', cat: null, open: new Set() },
    files: { group: 'all', q: '' },
    proj: { sort: 'size' },
    apps: null,
    appsQ: '',
    wsl: null,
    wslRes: {},
    wslOpen: new Set(),
    drawer: null,
    lost: false,
    elevated: false,
    busy: false,
    // clean-up: what is ticked, the plan the server validated, the running job
    clean: { sel: new Set(), plan: null, job: null, ok: false, modal: null, busy: false, stale: false, error: '' },
  };

  const CAT_ORDER = ['personal', 'apps', 'dev', 'data', 'virtual', 'system', 'other'];
  const ACT_ORDER = ['safe', 'regen', 'review', 'keep', 'info'];
  const ACT_ICON = { safe: 'check', regen: 'refresh', review: 'eye', keep: 'lock', info: 'info' };
  const KIND_NAME = {
    git: 'Git', node: 'Node.js', python: 'Python', rust: 'Rust', go: 'Go', java: 'Java / Kotlin', dotnet: '.NET',
    flutter: 'Flutter', php: 'PHP', ruby: 'Ruby', cpp: 'C / C++', unity: 'Unity', unreal: 'Unreal', swift: 'Swift',
    docker: 'Docker',
  };

  const ICONS = {
    overview: '<rect x="3" y="3" width="7" height="9" rx="1.5"/><rect x="14" y="3" width="7" height="5" rx="1.5"/><rect x="14" y="12" width="7" height="9" rx="1.5"/><rect x="3" y="16" width="7" height="5" rx="1.5"/>',
    folder: '<path d="M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/>',
    file: '<path d="M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8z"/><path d="M14 3v5h5"/>',
    bulb: '<path d="M9 18h6M10 21h4M12 3a6 6 0 0 0-4 10.5c.7.7 1 1.5 1 2.5h6c0-1 .3-1.8 1-2.5A6 6 0 0 0 12 3z"/>',
    files: '<path d="M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8z"/><path d="M14 3v5h5M9 13h6M9 17h4"/>',
    code: '<path d="m8 8-4 4 4 4M16 8l4 4-4 4M13.5 5l-3 14"/>',
    apps: '<rect x="3" y="3" width="7" height="7" rx="1.5"/><rect x="14" y="3" width="7" height="7" rx="1.5"/><rect x="3" y="14" width="7" height="7" rx="1.5"/><path d="M17.5 14v7M14 17.5h7"/>',
    terminal: '<rect x="3" y="4" width="18" height="16" rx="2"/><path d="m7 9 3 3-3 3M13 15h4"/>',
    check: '<circle cx="12" cy="12" r="9"/><path d="m8 12 3 3 5-6"/>',
    refresh: '<path d="M20 11a8 8 0 0 0-14.3-4.3L4 8M4 4v4h4M4 13a8 8 0 0 0 14.3 4.3L20 16M20 20v-4h-4"/>',
    eye: '<path d="M2 12s3.6-7 10-7 10 7 10 7-3.6 7-10 7S2 12 2 12z"/><circle cx="12" cy="12" r="3"/>',
    lock: '<rect x="5" y="11" width="14" height="9" rx="2"/><path d="M8 11V8a4 4 0 0 1 8 0v3"/>',
    info: '<circle cx="12" cy="12" r="9"/><path d="M12 11v5M12 8h.01"/>',
    alert: '<path d="M12 3 2.5 19.5h19z"/><path d="M12 10v4M12 17h.01"/>',
    external: '<path d="M14 4h6v6M20 4l-9 9M18 14v4a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h4"/>',
    copy: '<rect x="9" y="9" width="11" height="11" rx="2"/><path d="M5 15V6a2 2 0 0 1 2-2h9"/>',
    sun: '<circle cx="12" cy="12" r="4"/><path d="M12 2v2M12 20v2M2 12h2M20 12h2M5 5l1.5 1.5M17.5 17.5 19 19M19 5l-1.5 1.5M6.5 17.5 5 19"/>',
    moon: '<path d="M20 14.5A8 8 0 0 1 9.5 4a8 8 0 1 0 10.5 10.5z"/>',
    globe: '<circle cx="12" cy="12" r="9"/><path d="M3 12h18M12 3c2.5 2.6 3.8 5.6 3.8 9S14.5 18.4 12 21c-2.5-2.6-3.8-5.6-3.8-9S9.5 5.6 12 3z"/>',
    right: '<path d="m9 6 6 6-6 6"/>',
    down: '<path d="m6 9 6 6 6-6"/>',
    up: '<path d="M12 19V6M6 11l6-6 6 6"/>',
    close: '<path d="M6 6l12 12M18 6 6 18"/>',
    search: '<circle cx="11" cy="11" r="7"/><path d="m20 20-3.5-3.5"/>',
    shield: '<path d="M12 3 4.5 6v6c0 4.5 3.2 7.7 7.5 9 4.3-1.3 7.5-4.5 7.5-9V6z"/><path d="m9 12 2 2 4-4"/>',
    play: '<path d="M7 5v14l12-7z"/>',
    stop: '<rect x="6" y="6" width="12" height="12" rx="2"/>',
    disk: '<ellipse cx="12" cy="6" rx="8" ry="3"/><path d="M4 6v12c0 1.7 3.6 3 8 3s8-1.3 8-3V6M4 12c0 1.7 3.6 3 8 3s8-1.3 8-3"/>',
    home: '<path d="M4 11 12 4l8 7v8a1 1 0 0 1-1 1h-4v-6H9v6H5a1 1 0 0 1-1-1z"/>',
    cloud: '<path d="M7 18a4 4 0 0 1-.6-8A6 6 0 0 1 18 9.5 4.2 4.2 0 0 1 17.5 18z"/>',
    link: '<path d="M10 14a4 4 0 0 0 5.7 0l3-3a4 4 0 0 0-5.7-5.7l-1 1M14 10a4 4 0 0 0-5.7 0l-3 3a4 4 0 0 0 5.7 5.7l1-1"/>',
    clock: '<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/>',
    trash: '<path d="M4 7h16M10 11v6M14 11v6M6 7l1 12a2 2 0 0 0 2 2h6a2 2 0 0 0 2-2l1-12M9 7V4h6v3"/>',
    tick: '<path d="m5 12 5 5 9-10"/>',
    minus: '<path d="M6 12h12"/>',
  };

  // ── small helpers ──────────────────────────────────────────────────────

  // A few labels differ outside Windows ("Windows & system" → "System", "File Explorer" → "file manager").
  // Such keys have a twin ending in ".nix", used automatically on Linux and macOS.
  function t(key, vars) {
    const dict = I18N[state.lang] || I18N.en;
    if (state.meta && state.meta.platform !== 'win' && dict[key + '.nix'] !== undefined) key += '.nix';
    let s = (I18N[state.lang] && I18N[state.lang][key]) || I18N.en[key] || key;
    if (vars) for (const k in vars) s = s.split('{' + k + '}').join(vars[k]);
    return s;
  }

  function h(tag, props, ...kids) {
    const el = document.createElement(tag);
    if (props) {
      for (const k in props) {
        const v = props[k];
        if (v == null || v === false) continue;
        if (k === 'class') el.className = v;
        else if (k === 'style') el.style.cssText = v;
        else if (k.startsWith('on')) el.addEventListener(k.slice(2), v);
        else el.setAttribute(k, v === true ? '' : v);
      }
    }
    append(el, kids);
    return el;
  }

  function append(el, kids) {
    for (const kid of kids) {
      if (kid == null || kid === false) continue;
      if (Array.isArray(kid)) append(el, kid);
      else el.append(kid.nodeType ? kid : document.createTextNode(String(kid)));
    }
  }

  function icon(name, size) {
    const s = document.createElementNS(NS, 'svg');
    s.setAttribute('viewBox', '0 0 24 24');
    s.setAttribute('width', size || 18);
    s.setAttribute('height', size || 18);
    s.setAttribute('class', 'ico');
    s.setAttribute('aria-hidden', 'true');
    s.innerHTML = ICONS[name] || '';          // static, trusted markup defined above
    return s;
  }

  const locale = () => (state.lang === 'tr' ? 'tr-TR' : 'en-US');
  const nf = (v, d) => Number(v).toLocaleString(locale(), { minimumFractionDigits: d || 0, maximumFractionDigits: d || 0 });

  function fmtSize(bytes) {
    if (bytes == null) return '–';
    const units = ['B', 'KB', 'MB', 'GB', 'TB'];
    let v = Math.abs(bytes);
    let i = 0;
    while (v >= 1024 && i < units.length - 1) { v /= 1024; i++; }
    return nf(v, i <= 1 || v >= 100 ? 0 : 1) + ' ' + units[i];
  }

  function fmtPct(part, whole) {
    if (!whole) return '–';
    const p = (100 * part) / whole;
    const txt = nf(p, p < 10 ? 1 : 0);
    return state.lang === 'tr' ? '%' + txt : txt + '%';
  }

  function span(ts) {
    if (!ts) return null;
    const days = Math.max(0, Math.floor((Date.now() / 1000 - ts) / DAY));
    if (days < 60) return { unit: 'day', n: days, days };
    if (days < 730) return { unit: 'month', n: Math.round(days / 30.4), days };
    return { unit: 'year', n: Math.floor(days / 365), days };
  }

  function ago(ts) {
    const s = span(ts);
    if (!s) return t('d.never');
    if (s.days < 1) return t('misc.ago.today');
    return t('misc.ago.' + s.unit, { n: nf(s.n) });
  }

  function forSpan(ts) {
    const s = span(ts);
    return s ? t('misc.for.' + s.unit, { n: nf(s.n) }) : '';
  }

  const sep = () => (state.meta && state.meta.sep) || '\\';
  const baseName = (p) => { const s = p.replace(/[\\/]+$/, ''); const i = Math.max(s.lastIndexOf('\\'), s.lastIndexOf('/')); return i >= 0 && i < s.length - 1 ? s.slice(i + 1) : s; };
  const dirName = (p) => { const i = Math.max(p.lastIndexOf('\\'), p.lastIndexOf('/')); return i > 0 ? p.slice(0, i) : p; };
  const joinPath = (dir, name) => (dir.endsWith(sep()) ? dir + name : dir + sep() + name);

  async function api(path, body) {
    const opt = { headers: { 'X-Depoloma-Token': TOKEN } };
    if (body !== undefined) {
      opt.method = 'POST';
      opt.headers['Content-Type'] = 'application/json';
      opt.body = JSON.stringify(body);
    }
    const res = await fetch(path, opt);
    let data = {};
    try { data = await res.json(); } catch (e) { /* empty body */ }
    if (!res.ok) throw new Error(data.error || res.statusText);
    return data;
  }

  function ruleText(id) {
    const r = id && state.meta && state.meta.rules[id];
    if (!r) return null;
    const x = r[state.lang] || r.en;
    return { title: x[0], what: x[1], why: x[2], how: x[3], act: r.act, cat: r.cat };
  }

  function findingText(f) {
    if (f.kind === 'special') {
      const k = 'sp.' + f.id + '.';
      return { title: t(k + 'title'), what: t(k + 'what'), why: t(k + 'why'), how: t(k + 'how'), act: f.act, cat: f.cat };
    }
    return ruleText(f.id) || { title: f.id, what: '', why: '', how: '', act: f.act, cat: f.cat };
  }

  function badge(act, compact) {
    return h('span', { class: 'badge act-' + act, 'data-tip': compact ? t('act.' + act) + ' — ' + t('act.' + act + '.d') : t('act.' + act + '.d') },
      icon(ACT_ICON[act], 14), compact ? null : t('act.' + act));
  }

  function chip(text, cls, ico, tipText) {
    return h('span', { class: 'chip ' + (cls || ''), 'data-tip': tipText || null }, ico ? icon(ico, 13) : null, text);
  }

  function bar(part, whole, cls) {
    const pct = whole > 0 ? Math.max(0, Math.min(100, (100 * part) / whole)) : 0;
    return h('div', { class: 'bar ' + (cls || '') }, h('i', { style: 'width:' + (part > 0 ? Math.max(pct, 0.6) : 0) + '%' }));
  }

  function clickable(el, fn) {
    el.setAttribute('role', 'button');
    el.setAttribute('tabindex', '0');
    el.addEventListener('click', fn);
    el.addEventListener('keydown', (e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); fn(e); } });
    return el;
  }

  async function copyText(text, btn) {
    try {
      await navigator.clipboard.writeText(text);
    } catch (e) {
      const ta = h('textarea', { style: 'position:fixed;opacity:0' });
      ta.value = text;
      document.body.append(ta);
      ta.select();
      try { document.execCommand('copy'); } catch (e2) { /* give up quietly */ }
      ta.remove();
    }
    if (btn) {
      const label = btn.querySelector('.lbl');
      if (label) { const old = label.textContent; label.textContent = t('d.copied'); setTimeout(() => { label.textContent = old; }, 1400); }
    }
  }

  const reveal = (path) => api('/api/reveal', { path }).catch(() => {});
  const showCleanLog = () => api('/api/clean/log', {}).catch(() => {});

  // ── theme / language ───────────────────────────────────────────────────

  function applyTheme() {
    document.documentElement.dataset.theme = state.theme;
    document.documentElement.lang = state.lang;
  }

  function toggleTheme() {
    state.theme = state.theme === 'dark' ? 'light' : 'dark';
    store.set('theme', state.theme);
    applyTheme();
    render();
  }

  function toggleLang() {
    state.lang = state.lang === 'tr' ? 'en' : 'tr';
    store.set('lang', state.lang);
    applyTheme();
    render();
  }

  // ── boot, live status ──────────────────────────────────────────────────

  async function boot() {
    applyTheme();
    try {
      state.meta = await api('/api/meta');
    } catch (e) {
      state.lost = true;
    }
    render();
    connect();
    if (state.meta && state.meta.canClean) {
      try {                                   // the page was reloaded while a clean-up was running
        const st = await api('/api/clean/status');
        if (st.state === 'running') { state.clean.job = st; state.clean.modal = 'running'; render(); pollClean(); }
      } catch (e) { /* older server */ }
    }
  }

  function connect() {
    const es = new EventSource('/api/events?t=' + encodeURIComponent(TOKEN));
    let errors = 0;
    es.onmessage = (ev) => {
      errors = 0;
      if (state.lost) { state.lost = false; render(); }
      onStatus(JSON.parse(ev.data));
    };
    es.onerror = async () => {
      errors++;
      if (es.readyState === 2) {
        // The server refused us: it was restarted and this page holds an old token → reload once.
        es.close();
        try {
          const res = await fetch('/', { cache: 'no-store' });
          if (res.ok && !sessionStorage.getItem('depoloma.reloaded')) {
            sessionStorage.setItem('depoloma.reloaded', '1');
            location.reload();
            return;
          }
        } catch (e) { /* really gone */ }
        state.lost = true;
        render();
      } else if (errors >= 3 && !state.lost) {
        state.lost = true;
        render();
      }
    };
    es.onopen = () => { try { sessionStorage.removeItem('depoloma.reloaded'); } catch (e) { /* ignore */ } };
  }

  function onStatus(st) {
    const prev = state.status.state;
    state.status = st;
    if (st.state === 'scanning' || st.state === 'analyzing') {
      if (state.view !== 'scanning') { state.view = 'scanning'; state.drawer = null; render(); } else updateScanning();
    } else if (st.state === 'done' || st.state === 'cancelled') {
      if (prev === 'scanning' || prev === 'analyzing' || (!state.summary && !state.busy)) loadSummary();
    } else if (st.state === 'error' && state.view === 'scanning') {
      render();
    }
  }

  async function loadSummary() {
    state.busy = true;
    try {
      state.summary = await api('/api/summary');
      state.apps = null;
      state.clean.sel = new Set();
      state.clean.stale = false;
      state.find = { act: 'all', cat: null, open: new Set() };
      state.ex = { id: state.summary.volumes.length ? state.summary.volumes[0].id : null, node: null };
      state.view = 'overview';
      state.meta = await api('/api/meta');
    } catch (e) {
      state.view = 'welcome';
    }
    state.busy = false;
    render();
  }

  async function startScan(roots) {
    try {
      state.summary = null;
      await api('/api/scan', { roots });
      state.status = { state: 'scanning', files: 0, dirs: 0, bytes: 0, elapsed: 0, current: '', target: 0 };
      state.view = 'scanning';
      render();
    } catch (e) {
      alert(e.message);
    }
  }

  function go(view) {
    state.view = view;
    state.drawer = null;
    render();
    if (view === 'explorer' && !state.ex.node && state.ex.id != null) openNode(state.ex.id);
    if (view === 'apps' && !state.apps) loadApps();
    if (view === 'wsl') loadWsl();
  }

  // ── shell ──────────────────────────────────────────────────────────────

  function render() {
    const app = $('#app');
    const main = $('.main');
    const scroll = main ? main.scrollTop : 0;
    const sameView = app.dataset.view === state.view;
    app.dataset.view = state.view;
    $('#tip').hidden = true;
    app.replaceChildren(shell());
    if (state.drawer) app.append(drawerEl());
    if (state.clean.modal) app.append(cleanModal());
    if (state.lost) app.append(lostEl());
    if (sameView) { const m = $('.main'); if (m) m.scrollTop = scroll; }
    afterRender();
  }

  function shell() {
    const ready = !!state.summary;
    const navItem = (view, ico, extra) => h('button', {
      class: 'nav-item' + (state.view === view ? ' on' : ''), disabled: !ready, onclick: () => go(view),
    }, icon(ico, 18), h('span', null, t('nav.' + view)), extra || null);
    const nFind = ready ? state.summary.findings.filter((f) => f.act === 'safe' || f.act === 'regen' || f.act === 'review').length : 0;
    const m = state.meta || {};
    const hasApps = m.apps !== undefined ? m.apps : m.platform === 'win';
    const hasWsl = !!m.wsl;
    const side = h('aside', { class: 'side' },
      h('div', { class: 'brand' },
        h('img', { src: '/icon.svg', alt: '', width: 36, height: 36 }),
        h('div', null, h('div', { class: 'brand-name' }, 'Depoloma'), h('div', { class: 'brand-tag' }, t('app.tagline')))),
      h('nav', { class: 'nav' },
        navItem('overview', 'overview'),
        navItem('explorer', 'folder'),
        navItem('findings', 'bulb', nFind ? h('span', { class: 'count' }, nFind) : null),
        navItem('files', 'files'),
        navItem('projects', 'code'),
        hasApps ? navItem('apps', 'apps') : null,
        hasWsl ? navItem('wsl', 'terminal') : null),
      h('div', { class: 'side-foot' },
        h('div', { class: 'ro-pill', 'data-tip': t('app.readonly.tip') }, icon('shield', 16), t('app.readonly')),
        h('button', { class: 'side-btn', onclick: () => { state.view = 'welcome'; state.drawer = null; render(); } }, icon('refresh', 16), t('nav.rescan')),
        h('div', { class: 'side-row' },
          h('button', { class: 'side-btn', onclick: toggleTheme, 'aria-label': t('nav.theme') }, icon(state.theme === 'dark' ? 'sun' : 'moon', 16), t('nav.theme')),
          h('button', { class: 'side-btn', onclick: toggleLang }, icon('globe', 16), t('nav.lang'))),
        h('div', { class: 'ver' }, 'Depoloma ' + VERSION)));
    let page;
    if (!state.meta) page = h('div', { class: 'page center' }, t('misc.loading'));
    else if (state.view === 'scanning') page = viewScanning();
    else if (!ready || state.view === 'welcome') page = viewWelcome();
    else if (state.view === 'explorer') page = viewExplorer();
    else if (state.view === 'findings') page = viewFindings();
    else if (state.view === 'files') page = viewFiles();
    else if (state.view === 'projects') page = viewProjects();
    else if (state.view === 'apps') page = viewApps();
    else if (state.view === 'wsl') page = viewWsl();
    else page = viewOverview();
    return h('div', { class: 'shell' }, side, h('main', { class: 'main' }, page));
  }

  function lostEl() {
    return h('div', { class: 'overlay' }, h('div', { class: 'lost card' },
      icon('alert', 28), h('h2', null, t('misc.lost')), h('p', null, t('misc.lost.d'))));
  }

  function pageHead(title, sub, right) {
    return h('header', { class: 'page-head' },
      h('div', null, h('h1', null, title), sub ? h('p', { class: 'sub' }, sub) : null),
      right || null);
  }

  function afterRender() {
    const tm = $('.treemap');
    if (tm && state.ex.node) drawTreemap(tm, state.ex.node);
  }

  // ── welcome ────────────────────────────────────────────────────────────

  function viewWelcome() {
    const vols = state.meta.volumes || [];
    if (!state.pick) {
      state.pick = new Set(vols.filter((v) => v.system).map((v) => v.path));
      if (!state.pick.size && vols.length) state.pick.add(vols[0].path);
    }
    const volCard = (v) => {
      const on = state.pick.has(v.path);
      const freeRatio = v.total ? v.free / v.total : 1;
      const sev = freeRatio < 0.1 ? 'crit' : freeRatio < 0.2 ? 'warn' : 'ok';
      const el = h('div', { class: 'vol' + (on ? ' on' : ''), 'aria-pressed': on ? 'true' : 'false' },
        h('div', { class: 'vol-top' },
          h('span', { class: 'vol-ico' }, icon('disk', 22)),
          h('div', { class: 'vol-name' }, h('b', null, v.path), v.label ? h('span', null, v.label) : null),
          h('span', { class: 'check' + (on ? ' on' : '') }, on ? icon('check', 20) : null)),
        h('div', { class: 'meter ' + sev }, h('i', { style: 'width:' + (v.total ? (100 * v.used) / v.total : 0) + '%' })),
        h('div', { class: 'vol-nums' },
          h('span', null, h('b', null, fmtSize(v.free)), ' ' + t('welcome.free')),
          h('span', null, fmtSize(v.total) + ' ' + t('welcome.of'))));
      return clickable(el, () => {
        if (state.pick.has(v.path)) state.pick.delete(v.path); else state.pick.add(v.path);
        render();
      });
    };
    const assure = (ico, title, text) => h('div', { class: 'assure' }, h('span', { class: 'assure-ico' }, icon(ico, 20)),
      h('div', null, h('b', null, title), h('p', null, text)));
    const st = state.status;
    return h('div', { class: 'page welcome' },
      h('div', { class: 'hero-card card' },
        h('img', { src: '/icon.svg', alt: '', width: 64, height: 64, class: 'hero-logo' }),
        h('h1', null, t('welcome.title')),
        h('p', { class: 'lead' }, t('welcome.lead')),
        st.state === 'error' ? h('div', { class: 'note crit' }, icon('alert', 16), t('scan.error') + ': ' + (st.error || '')) : null,
        h('div', { class: 'label' }, t('welcome.pick')),
        h('div', { class: 'vols' }, vols.map(volCard)),
        h('div', { class: 'actions' },
          h('button', { class: 'btn primary lg', disabled: !state.pick.size, onclick: () => startScan(Array.from(state.pick)) },
            icon('play', 18), t('welcome.start')),
          h('button', { class: 'btn ghost', onclick: () => startScan([state.meta.home]) }, icon('home', 16), t('welcome.home'))),
        state.meta.elevated ? h('div', { class: 'note' }, icon('shield', 16), t('welcome.admin')) : null),
      h('div', { class: 'assures' },
        assure('shield', t('welcome.safe1'), t('welcome.safe1d')),
        assure('lock', t('welcome.safe2'), t('welcome.safe2d')),
        assure('bulb', t('welcome.safe3'), t('welcome.safe3d'))));
  }

  // ── scanning ───────────────────────────────────────────────────────────

  function viewScanning() {
    const el = h('div', { class: 'page scanning' },
      h('div', { class: 'card scan-card' },
        h('div', { class: 'scan-ring' }, h('div', { class: 'pulse' }), h('img', { src: '/icon.svg', alt: '', width: 72, height: 72 })),
        h('h1', { id: 'scan-title' }, t('scan.title')),
        h('div', { class: 'progress' }, h('i', { id: 'scan-bar' })),
        h('div', { class: 'scan-pct', id: 'scan-pct' }, ''),
        h('div', { class: 'tiles' },
          h('div', { class: 'tile' }, h('b', { id: 'scan-files' }, '0'), h('span', null, t('scan.files'))),
          h('div', { class: 'tile' }, h('b', { id: 'scan-dirs' }, '0'), h('span', null, t('scan.dirs'))),
          h('div', { class: 'tile' }, h('b', { id: 'scan-size' }, '0'), h('span', null, t('scan.size'))),
          h('div', { class: 'tile' }, h('b', { id: 'scan-time' }, '0'), h('span', null, t('scan.time')))),
        h('div', { class: 'scan-path', id: 'scan-path' }, ''),
        h('p', { class: 'muted' }, t('scan.note')),
        h('button', { class: 'btn ghost', onclick: () => api('/api/cancel', {}).catch(() => {}) }, icon('stop', 16), t('scan.cancel'))));
    setTimeout(updateScanning, 0);
    return el;
  }

  function updateScanning() {
    const st = state.status;
    const set = (id, text) => { const e = document.getElementById(id); if (e) e.textContent = text; };
    if (!document.getElementById('scan-files')) return;
    set('scan-title', st.state === 'analyzing' ? t('scan.analyzing') : t('scan.title'));
    set('scan-files', nf(st.files || 0));
    set('scan-dirs', nf(st.dirs || 0));
    set('scan-size', fmtSize(st.bytes || 0));
    const secs = Math.round(st.elapsed || 0);
    set('scan-time', Math.floor(secs / 60) + ':' + String(secs % 60).padStart(2, '0'));
    const p = st.current || '';
    set('scan-path', p.length > 86 ? '…' + p.slice(-85) : p);
    const barEl = document.getElementById('scan-bar');
    if (st.state === 'analyzing') {
      barEl.style.width = '100%';
      set('scan-pct', '');
    } else if (st.target > 0) {
      const pct = Math.min(99, (100 * (st.bytes || 0)) / st.target);
      barEl.style.width = pct + '%';
      barEl.classList.remove('indet');
      set('scan-pct', fmtPct(pct, 100));
    } else {
      barEl.classList.add('indet');
    }
  }

  // ── overview ───────────────────────────────────────────────────────────

  function viewOverview() {
    const s = state.summary;
    const vols = s.volumes.filter((v) => v.isVolume);
    const whole = vols.length === s.volumes.length && vols.length > 0;
    const total = whole ? vols.reduce((a, v) => a + v.total, 0) : s.scanned;
    const used = whole ? vols.reduce((a, v) => a + v.used, 0) : s.scanned;
    const free = whole ? vols.reduce((a, v) => a + v.free, 0) : 0;
    const freeRatio = total ? free / total : 1;
    const sev = !whole ? 'ok' : freeRatio < 0.1 ? 'crit' : freeRatio < 0.2 ? 'warn' : 'ok';

    const tile = (value, label, tipText) => h('div', { class: 'tile', 'data-tip': tipText || null }, h('b', null, value), h('span', null, label));
    const hero = h('section', { class: 'card hero ' + sev },
      h('div', { class: 'hero-main' },
        whole
          ? [h('div', { class: 'hero-state' }, icon(sev === 'ok' ? 'check' : 'alert', 16), t('ov.state.' + sev)),
            h('div', { class: 'hero-fig' }, fmtSize(free), h('small', null, t('ov.free'))),
            h('div', { class: 'meter big ' + sev }, h('i', { style: 'width:' + (100 * used) / (total || 1) + '%' })),
            h('div', { class: 'hero-sub' }, t('ov.used', { total: fmtSize(total), used: fmtSize(used) }) + ' (' + fmtPct(used, total) + ')'
              + '  ·  ' + vols.map((v) => v.path + (v.label ? ' ' + v.label : '')).join(', '))]
          : [h('div', { class: 'hero-state' }, icon('folder', 16), t('ov.partial', { path: s.volumes.map((v) => v.path).join(', ') })),
            h('div', { class: 'hero-fig' }, fmtSize(s.scanned), h('small', null, t('scan.size')))]),
      h('div', { class: 'tiles' },
        tile(fmtSize(s.reclaim.safe), t('ov.tile.safe'), t('act.safe.d')),
        tile(fmtSize(s.reclaim.regen), t('ov.tile.regen'), t('act.regen.d')),
        tile(nf(s.files), t('ov.tile.files')),
        tile(nf(Math.round(s.elapsed)) + ' s', t('ov.tile.time'))));

    // where does the space go: one bar, fixed order, plus a legend that doubles as the table view
    const parts = CAT_ORDER.map((k) => ({ key: k, size: (s.cats.find((c) => c.key === k) || { size: 0 }).size }));
    if (s.hidden > 0) parts.push({ key: 'hidden', size: s.hidden });
    const seg = h('div', { class: 'seg', role: 'img', 'aria-label': t('ov.where') },
      parts.filter((p) => p.size > 0).map((p) => {
        const share = p.size / (total || 1);
        const name = p.key === 'hidden' ? t('seg.hidden') : t('cat.' + p.key);
        return h('div', {
          class: 'seg-part c-' + p.key, style: 'flex:' + Math.max(share * 1000, 3) + ' 0 0',
          'data-tip': name + '\n' + fmtSize(p.size) + ' · ' + fmtPct(p.size, total),
        }, share >= 0.065 ? h('span', null, fmtPct(p.size, total)) : null);
      }),
      free > 0 ? h('div', { class: 'seg-part c-free', style: 'flex:' + Math.max((free / total) * 1000, 3) + ' 0 0',
        'data-tip': t('seg.free') + '\n' + fmtSize(free) + ' · ' + fmtPct(free, total) },
      free / total >= 0.065 ? h('span', null, t('seg.free')) : null) : null);
    const legend = h('div', { class: 'legend' }, parts.filter((p) => p.size > 0).map((p) => {
      const isHidden = p.key === 'hidden';
      const row = h('div', { class: 'legend-row' },
        h('i', { class: 'sw c-' + p.key }),
        h('div', { class: 'legend-name' }, h('b', null, isHidden ? t('seg.hidden') : t('cat.' + p.key)),
          h('span', null, t('cat.' + p.key + '.d'))),
        h('div', { class: 'legend-num' }, h('b', null, fmtSize(p.size)), h('span', null, fmtPct(p.size, used))),
        isHidden || p.key === 'other' ? h('span', { class: 'go' }) : h('span', { class: 'go' }, icon('right', 16)));
      if (isHidden || p.key === 'other') return row;
      return clickable(row, () => { state.find = { act: 'all', cat: p.key, open: new Set() }; go('findings'); });
    }));
    const where = h('section', { class: 'card' },
      h('h2', null, t('ov.where')), h('p', { class: 'sub' }, t('ov.where.sub')), seg, legend);

    // hotspots: ranked bars, one hue
    const maxHot = s.hotspots.length ? s.hotspots[0].size : 1;
    const hot = h('section', { class: 'card' },
      h('h2', null, t('ov.hot')), h('p', { class: 'sub' }, t('ov.hot.sub')),
      h('div', { class: 'rank' }, s.hotspots.map((x) => {
        const rt = ruleText(x.rule);
        const row = h('div', { class: 'rank-row' },
          h('span', { class: 'rank-ico' }, icon(x.t === 'f' ? 'file' : 'folder', 16)),
          h('div', { class: 'rank-name' },
            h('b', null, baseName(x.path)),
            rt ? chip(rt.title, 'act-' + rt.act, ACT_ICON[rt.act]) : (x.project ? chip(t('ex.project'), 'proj', 'code') : null),
            h('span', { class: 'path' }, dirName(x.path))),
          bar(x.size, maxHot),
          h('b', { class: 'num' }, fmtSize(x.size)));
        return clickable(row, () => openDrawer({ t: x.t, id: x.id, name: baseName(x.path), path: x.path, size: x.size,
          newest: x.newest, files: x.files, rule: x.rule, open: x.t === 'd' }));
      })));

    // top suggestions
    const topF = s.findings.filter((f) => f.act === 'safe' || f.act === 'regen' || f.act === 'review')
      .slice().sort((a, b) => b.size - a.size).slice(0, 6);
    const top = h('section', { class: 'card' },
      h('h2', null, t('ov.top')), h('p', { class: 'sub' }, t('ov.top.sub')),
      h('div', { class: 'sugg' }, topF.map((f) => {
        const ft = findingText(f);
        return clickable(h('div', { class: 'sugg-row' },
          badge(f.act, true),
          h('div', { class: 'sugg-name' }, h('b', null, ft.title), h('span', null, ft.what)),
          h('b', { class: 'num' }, fmtSize(f.size)),
          icon('right', 16)), () => { state.find = { act: 'all', cat: null, open: new Set([f.id]) }; go('findings'); });
      })),
      h('button', { class: 'btn ghost', onclick: () => go('findings') }, t('ov.top.all'), icon('right', 16)));

    // file types
    const maxType = s.types.length ? s.types[0].size : 1;
    const types = h('section', { class: 'card' },
      h('h2', null, t('ov.types')), h('p', { class: 'sub' }, t('ov.types.sub')),
      h('div', { class: 'rank compact' }, s.types.filter((x) => x.size > 0).slice(0, 10).map((x) =>
        h('div', { class: 'rank-row', 'data-tip': x.exts.filter((e) => e.size > 0).map((e) => (e.ext ? '.' + e.ext : '—') + '  ' + fmtSize(e.size)).join('\n') },
          h('div', { class: 'rank-name' }, h('b', null, t('grp.' + x.key)), h('span', { class: 'path' }, nf(x.count) + ' ' + t('scan.files'))),
          bar(x.size, maxType),
          h('b', { class: 'num' }, fmtSize(x.size))))));

    // age of data
    const ageTotal = s.ages.reduce((a, x) => a + x.size, 0) || 1;
    const maxAge = Math.max.apply(null, s.ages.map((x) => x.size)) || 1;
    const oldBytes = s.ages.slice(3).reduce((a, x) => a + x.size, 0);
    const ages = h('section', { class: 'card' },
      h('h2', null, t('ov.ages')), h('p', { class: 'sub' }, t('ov.ages.sub')),
      h('div', { class: 'rank compact' }, s.ages.map((x) =>
        h('div', { class: 'rank-row', 'data-tip': fmtPct(x.size, ageTotal) },
          h('div', { class: 'rank-name' }, h('b', null, t('age.' + x.key))),
          bar(x.size, maxAge),
          h('b', { class: 'num' }, fmtSize(x.size))))),
      h('p', { class: 'note' }, icon('clock', 16), t('ov.ages.note', { size: fmtSize(oldBytes), pct: fmtPct(oldBytes, ageTotal) })));

    // what we could not see
    let hidden = null;
    if (s.hidden > (1 << 30) || s.denied.count > 0) {
      hidden = h('section', { class: 'card hiddencard' },
        h('h2', null, icon('lock', 18), t('ov.hidden')),
        s.hidden > 0 ? h('p', null, t('ov.hidden.text', { size: fmtSize(s.hidden) })) : null,
        s.denied.count ? h('p', { class: 'muted' }, t('ov.hidden.denied', { n: nf(s.denied.count) })) : null,
        state.meta.elevated ? null
          : state.meta.platform !== 'win' ? h('div', { class: 'codebox' },
            h('div', { class: 'code-head' }, h('b', null, t('ov.hidden.sudo')),
              h('button', { class: 'btn ghost sm', onclick: (e) => copyText(state.meta.sudo || '', e.currentTarget) }, icon('copy', 14), h('span', { class: 'lbl' }, t('misc.copy')))),
            h('pre', null, state.meta.sudo || 'sudo python3 -m depoloma --no-open'))
            : (state.elevated ? h('p', { class: 'note' }, icon('shield', 16), t('ov.hidden.elevated'))
              : h('button', { class: 'btn ghost', onclick: async () => {
                try { const r = await api('/api/elevate', {}); if (r.ok) { state.elevated = true; render(); } } catch (e) { /* declined */ }
              } }, icon('shield', 16), t('ov.hidden.elevate'))));
    }

    return h('div', { class: 'page' },
      s.state === 'cancelled' ? h('div', { class: 'note warn' }, icon('alert', 16), t('scan.cancelled')) : null,
      hero, where,
      h('div', { class: 'grid2' }, hot, top),
      h('div', { class: 'grid2' }, types, ages),
      hidden);
  }

  // ── explorer ───────────────────────────────────────────────────────────

  async function openNode(id) {
    try {
      const node = await api('/api/node?deep=1&id=' + id);
      state.ex = { id, node };
      if (state.view !== 'explorer') state.view = 'explorer';
      state.drawer = null;
      render();
      const m = $('.main');
      if (m) m.scrollTop = 0;
    } catch (e) { /* folder vanished from the tree */ }
  }

  function rowChips(c) {
    const out = [];
    const rt = ruleText(c.rule);
    if (rt) out.push(chip(rt.title, 'act-' + rt.act, ACT_ICON[rt.act], rt.what));
    if (c.project) {
      out.push(chip(t('ex.project') + ' · ' + c.project.kinds.map((k) => KIND_NAME[k] || k).join(', '), 'proj', 'code'));
      const s = span(c.project.newest);
      if (s && s.days >= 180) out.push(chip(t('misc.untouched', { for: forSpan(c.project.newest) }), 'old', 'clock'));
    } else if (c.newest && c.size >= 50 * 1048576 && (!rt || rt.act === 'review' || rt.act === 'info')) {
      const s = span(c.newest);
      if (s && s.days >= 365) out.push(chip(t('misc.untouched', { for: forSpan(c.newest) }), 'old', 'clock'));
    }
    if (c.denied) out.push(chip(t(c.partial ? 'ex.partial' : 'ex.denied'), 'warn', 'lock', t('ex.denied.d')));
    if (c.link) out.push(chip(t('ex.link'), '', 'link', t('ex.link.d')));
    return out;
  }

  function viewExplorer() {
    const node = state.ex.node;
    if (!node) return h('div', { class: 'page center' }, t('misc.loading'));
    const crumbs = h('nav', { class: 'crumbs' }, node.crumbs.map((c, i) => {
      const last = i === node.crumbs.length - 1;
      return [i ? h('span', { class: 'crumb-sep' }, icon('right', 14)) : null,
        last ? h('b', null, c.name) : h('button', { class: 'crumb', onclick: () => openNode(c.id) }, c.name)];
    }));
    const parent = node.crumbs.length > 1 ? node.crumbs[node.crumbs.length - 2] : null;
    const rt = ruleText(node.rule);
    const self = { t: 'd', id: node.id, name: node.name, path: node.path, size: node.size, files: node.files, newest: node.newest,
      rule: node.rule, project: node.project, open: false };
    const head = h('section', { class: 'card ex-head' },
      h('div', { class: 'ex-top' },
        h('button', { class: 'btn icon', disabled: !parent, 'aria-label': t('ex.up'), 'data-tip': t('ex.up'), onclick: () => parent && openNode(parent.id) }, icon('up', 18)),
        crumbs),
      h('div', { class: 'ex-facts' },
        h('div', { class: 'fact big' }, h('b', null, fmtSize(node.size)), h('span', null, t('d.size'))),
        h('div', { class: 'fact' }, h('b', null, nf(node.files)), h('span', null, t('scan.files'))),
        h('div', { class: 'fact' }, h('b', null, nf(node.dirs)), h('span', null, t('scan.dirs'))),
        h('div', { class: 'fact' }, h('b', null, ago(node.newest)), h('span', null, t('d.changed'))),
        h('div', { class: 'ex-btns' },
          h('button', { class: 'btn ghost', onclick: () => openDrawer(self) }, icon('info', 16), t('ex.details')),
          h('button', { class: 'btn ghost', onclick: () => reveal(node.path) }, icon('external', 16), t('d.reveal')))),
      rt ? h('div', { class: 'explain act-' + rt.act }, badge(rt.act), h('div', null, h('b', null, rt.title), ' — ', rt.what, rt.why ? ' ' + rt.why : '')) : null,
      node.cloud > 100 * 1048576 ? h('div', { class: 'note' }, icon('cloud', 16), t('ex.cloud', { size: fmtSize(node.cloud) })) : null,
      node.linked > 100 * 1048576 && node.linked > node.size * 0.05 ? h('div', { class: 'note' }, icon('link', 16), t('ex.linked', { size: fmtSize(node.linked) })) : null);

    const rows = [];
    const whole = node.size || 1;
    for (const c of node.items) {
      const isDir = c.t === 'd';
      const frt = !isDir ? ruleText(c.rule) : null;
      const item = isDir ? Object.assign({ path: joinPath(node.path, c.name) }, c)
        : { t: 'f', id: node.id, name: c.name, path: joinPath(node.path, c.name), size: c.size, newest: c.newest, rule: c.rule };
      const row = h('div', { class: 'ex-row' + (isDir && c.open ? ' can-open' : '') },
        h('span', { class: 'ex-ico ' + (isDir ? 'dir' : 'file') }, icon(isDir ? 'folder' : 'file', 18)),
        h('div', { class: 'ex-name' }, h('b', null, c.name),
          isDir ? rowChips(c) : (frt ? chip(frt.title, 'act-' + frt.act, ACT_ICON[frt.act], frt.what) : null)),
        bar(c.size, whole),
        h('span', { class: 'num pct' }, fmtPct(c.size, whole)),
        h('b', { class: 'num' }, c.denied && !c.size ? '?' : fmtSize(c.size)),
        h('span', { class: 'num dim' }, isDir ? nf(c.files) : ''),
        h('span', { class: 'dim when' }, ago(c.newest)),
        h('button', { class: 'btn icon sm', 'aria-label': t('ex.details'), 'data-tip': t('ex.details'),
          onclick: (e) => { e.stopPropagation(); openDrawer(item); } }, icon('info', 16)));
      rows.push(clickable(row, () => (isDir && c.open ? openNode(c.id) : openDrawer(item))));
    }
    const agg = (n, size, label, tipText) => h('div', { class: 'ex-row agg', 'data-tip': tipText },
      h('span', { class: 'ex-ico' }, icon('files', 18)),
      h('div', { class: 'ex-name' }, h('span', null, label)),
      bar(size, whole, 'muted'), h('span', { class: 'num pct' }, fmtPct(size, whole)), h('b', { class: 'num' }, fmtSize(size)),
      h('span', null), h('span', null), h('span', null));
    if (node.small.n) rows.push(agg(node.small.n, node.small.size, t('ex.small', { n: nf(node.small.n) }), t('ex.small.d')));
    if (node.tiny.n) rows.push(agg(node.tiny.n, node.tiny.size, t('ex.tiny', { n: nf(node.tiny.n) }), t('ex.tiny.d')));
    if (node.more) rows.push(agg(node.more.n, node.more.size, t('ex.more', { n: nf(node.more.n) }), ''));

    const hasMap = node.items.length > 0;
    return h('div', { class: 'page' },
      head,
      hasMap ? h('section', { class: 'card' },
        h('div', { class: 'card-head' }, h('div', null, h('h2', null, t('ex.map')), h('p', { class: 'sub' }, t('ex.map.d'))),
          h('div', { class: 'tm-legend' },
            h('span', null, h('i', { class: 'sw tm-dir' }), t('ex.legend.dir')),
            h('span', null, h('i', { class: 'sw tm-file' }), t('ex.legend.file')),
            h('span', null, h('i', { class: 'sw tm-other' }), t('ex.legend.other')))),
        h('div', { class: 'treemap' })) : null,
      h('section', { class: 'card flush' },
        h('div', { class: 'ex-row ex-headrow' },
          h('span', null), h('span', null, t('ex.name')), h('span', null, t('ex.share')), h('span', null),
          h('span', { class: 'num' }, t('ex.size')), h('span', { class: 'num' }, t('ex.items')), h('span', null, t('ex.changed')), h('span', null)),
        rows.length ? rows : h('div', { class: 'empty' }, node.denied ? t('ex.denied.d') : t('ex.empty'))));
  }

  // squarified treemap (Bruls, Huizing, van Wijk)
  function squarify(items, x, y, w, h0) {
    const total = items.reduce((a, i) => a + i.size, 0);
    const out = [];
    if (total <= 0 || w <= 1 || h0 <= 1) return out;
    const scale = (w * h0) / total;
    let rx = x, ry = y, rw = w, rh = h0;
    let row = [];
    let rowSum = 0;
    const worst = (list, sum, side) => {
      let mx = 0, mn = Infinity;
      for (const r of list) { if (r.area > mx) mx = r.area; if (r.area < mn) mn = r.area; }
      const s2 = side * side, sum2 = sum * sum;
      return Math.max((s2 * mx) / sum2, sum2 / (s2 * mn));
    };
    const flush = () => {
      if (!row.length) return;
      if (rw >= rh) {
        const cw = rowSum / rh;
        let cy = ry;
        for (const r of row) { const ch = r.area / cw; out.push({ item: r.item, x: rx, y: cy, w: cw, h: ch }); cy += ch; }
        rx += cw; rw -= cw;
      } else {
        const ch = rowSum / rw;
        let cx = rx;
        for (const r of row) { const cw = r.area / ch; out.push({ item: r.item, x: cx, y: ry, w: cw, h: ch }); cx += cw; }
        ry += ch; rh -= ch;
      }
      row = []; rowSum = 0;
    };
    for (const it of items) {
      const r = { item: it, area: it.size * scale };
      if (r.area <= 0) continue;
      const side = Math.min(rw, rh);
      if (!row.length) { row.push(r); rowSum = r.area; continue; }
      if (worst(row.concat([r]), rowSum + r.area, side) <= worst(row, rowSum, side)) { row.push(r); rowSum += r.area; } else { flush(); row = [r]; rowSum = r.area; }
    }
    flush();
    return out;
  }

  function drawTreemap(box, node) {
    const W = box.clientWidth, H = box.clientHeight;
    if (W < 50 || H < 50) return;
    const total = node.size || 1;
    let items = node.items.filter((c) => c.size > 0).map((c) => ({ kind: c.t === 'd' ? 'dir' : 'file', name: c.name, size: c.size, ref: c }));
    let other = node.small.size + node.tiny.size + (node.more ? node.more.size : 0);
    const keep = [];
    for (const it of items) { if (keep.length < 48 && it.size / total >= 0.004) keep.push(it); else other += it.size; }
    if (other > 0) keep.push({ kind: 'other', name: t('ex.other'), size: other });
    keep.sort((a, b) => b.size - a.size);
    const frag = document.createDocumentFragment();
    const pos = (r) => 'left:' + r.x + 'px;top:' + r.y + 'px;width:' + Math.max(0, r.w - 2) + 'px;height:' + Math.max(0, r.h - 2) + 'px';
    // Draw one item; a folder that is large enough becomes a labelled group showing what is inside it.
    const place = (into, r, it, rel, parentId, depth) => {
      const c = it.ref;
      const relPath = rel ? rel + sep() + it.name : it.name;
      const tipText = relPath + '\n' + fmtSize(it.size) + ' · ' + fmtPct(it.size, total);
      if (it.kind === 'dir' && c.sub && c.sub.length && r.w > 104 && r.h > 70 && depth < 4) {
        const wrap = h('div', { class: 'tm-group d' + depth, style: pos(r) });
        const headEl = h('div', { class: 'tm-head', 'data-tip': tipText }, h('b', null, it.name), h('span', null, fmtSize(it.size)));
        clickable(headEl, () => openNode(c.id));
        wrap.append(headEl);
        const shown = [];
        let rest = it.size;
        for (const k of c.sub) {
          if (k.size / it.size >= 0.02) { shown.push({ kind: k.t === 'd' ? 'dir' : 'file', name: k.name, size: k.size, ref: k }); rest -= k.size; }
        }
        if (rest > it.size * 0.004) shown.push({ kind: 'other', name: t('ex.other'), size: rest });
        shown.sort((a, b) => b.size - a.size);
        for (const q of squarify(shown, 3, 22, r.w - 8, r.h - 27)) place(wrap, q, q.item, relPath, c.id, depth + 1);
        into.append(wrap);
        return;
      }
      let onClick = null;
      if (it.kind === 'dir') {
        onClick = c.open && c.id != null ? () => openNode(c.id)
          : (depth ? () => openNode(parentId) : () => openDrawer(Object.assign({ path: joinPath(node.path, c.name) }, c)));
      } else if (it.kind === 'file') {
        onClick = depth ? () => openNode(parentId)
          : () => openDrawer({ t: 'f', id: node.id, name: c.name, path: joinPath(node.path, c.name), size: c.size, newest: c.newest, rule: c.rule });
      } else if (depth) {
        onClick = () => openNode(parentId);
      }
      const el = h('div', { class: 'tm-cell tm-' + it.kind, style: pos(r), 'data-tip': tipText });
      if (r.w > 64 && r.h > 26) {
        el.append(h('span', { class: 'tm-name' }, it.name));
        if (r.h > 44) el.append(h('span', { class: 'tm-size' }, fmtSize(it.size)));
      }
      if (onClick) clickable(el, onClick);
      into.append(el);
    };
    for (const r of squarify(keep, 0, 0, W, H)) place(frag, r, r.item, '', node.id, 0);
    box.replaceChildren(frag);
  }

  // ── findings ───────────────────────────────────────────────────────────

  function itemRow(it, maxSize, fallbackRule, selectable) {
    const isDir = it.t !== 'f';
    const sel = state.clean.sel;
    const row = h('div', { class: 'it-row' + (selectable ? ' sel' : '') },
      !selectable ? null : it.clean
        ? checkbox(sel.has(it.id) ? 'on' : 'off', () => { if (sel.has(it.id)) sel.delete(it.id); else sel.add(it.id); render(); }, t('clean.pick'))
        : checkbox('disabled', null, t('clean.pick'), t('clean.item.no')),
      h('span', { class: 'ex-ico ' + (isDir ? 'dir' : 'file') }, icon(isDir ? 'folder' : 'file', 16)),
      h('div', { class: 'it-name' }, h('b', null, it.name || baseName(it.path)),
        selectable && it.clean && usedRecently(it.used || it.newest) ? chip(t('clean.recent'), 'old', 'clock', t('clean.recent.tip', { days: RECENT_DAYS })) : null,
        h('span', { class: 'path' }, dirName(it.path))),
      bar(it.size, maxSize),
      h('b', { class: 'num' }, fmtSize(it.size)),
      h('span', { class: 'dim when' }, it.days != null ? (it.days >= 0 ? ago(it.newest) : '') : ago(it.newest)),
      h('button', { class: 'btn icon sm', 'aria-label': t('d.reveal'), 'data-tip': t('d.reveal'), onclick: (e) => { e.stopPropagation(); reveal(it.path); } }, icon('external', 16)));
    return clickable(row, () => openDrawer({ t: isDir ? 'd' : 'f', id: it.id, name: it.name || baseName(it.path), path: it.path, size: it.size,
      newest: it.newest, files: it.files, open: isDir, rule: it.rule || fallbackRule || null, projectItem: it.kinds ? it : null }));
  }

  function viewFindings() {
    const s = state.summary;
    const fs = state.find;
    const list = s.findings.filter((f) => (fs.act === 'all' || f.act === fs.act) && (!fs.cat || f.cat === fs.cat));
    const nReview = s.findings.filter((f) => f.act === 'review').length;
    const tiles = h('div', { class: 'tiles three' },
      h('div', { class: 'tile act-safe' }, h('span', { class: 'tile-ico' }, icon('check', 20)), h('b', null, '≈ ' + fmtSize(s.reclaim.safe)), h('span', null, t('act.safe')), h('em', null, t('act.safe.d'))),
      h('div', { class: 'tile act-regen' }, h('span', { class: 'tile-ico' }, icon('refresh', 20)), h('b', null, '≈ ' + fmtSize(s.reclaim.regen)), h('span', null, t('act.regen')), h('em', null, t('act.regen.d'))),
      h('div', { class: 'tile act-review' }, h('span', { class: 'tile-ico' }, icon('eye', 20)), h('b', null, nf(nReview) + ' ' + t('f.review.unit')), h('span', null, t('act.review')), h('em', null, t('act.review.d'))));
    const filt = (key, label) => h('button', { class: 'pill' + (fs.act === key ? ' on' : ''), onclick: () => { fs.act = key; render(); } },
      key !== 'all' ? icon(ACT_ICON[key], 14) : null, label,
      h('span', { class: 'pill-n' }, s.findings.filter((f) => (key === 'all' || f.act === key) && (!fs.cat || f.cat === fs.cat)).length));
    const filters = h('div', { class: 'filters' },
      filt('all', t('f.filter.all')), ACT_ORDER.map((a) => filt(a, t('act.' + a))),
      fs.cat ? h('button', { class: 'pill on cat', onclick: () => { fs.cat = null; render(); } }, h('i', { class: 'sw c-' + fs.cat }), t('cat.' + fs.cat), icon('close', 13)) : null);

    const cleaning = canClean();
    const sel = state.clean.sel;
    const cards = list.map((f) => {
      const ft = findingText(f);
      const open = fs.open.has(f.id);
      const pick = cleaning && f.clean;
      const own = pick ? f.items.filter((it) => it.clean) : [];
      const nSel = own.filter((it) => sel.has(it.id)).length;
      const manual = cleaning && f.act === 'safe' && !f.clean;
      const headRow = clickable(h('div', { class: 'f-head' + (pick ? ' sel' : '') },
        pick ? checkbox(nSel === 0 ? 'off' : nSel === own.length ? 'on' : 'some', () => {
          const all = nSel === own.length;
          for (const it of own) { if (all) sel.delete(it.id); else sel.add(it.id); }
          render();
        }, t('clean.pick')) : null,
        badge(f.act),
        h('div', { class: 'f-title' },
          h('div', { class: 'f-name' }, h('b', null, ft.title), manual ? chip(t('clean.manual'), '', 'info', t('clean.manual.tip')) : null),
          h('span', null, ft.what)),
        h('div', { class: 'f-num' }, h('b', null, fmtSize(f.size)), h('span', null, t('f.items', { n: nf(f.count) }))),
        h('span', { class: 'chev' + (open ? ' open' : '') }, icon('down', 18))),
      () => { if (open) fs.open.delete(f.id); else fs.open.add(f.id); render(); });
      let body = null;
      if (open) {
        const maxSize = f.items.reduce((m, it) => Math.max(m, it.size), 1);
        const ownRule = f.kind === 'special' ? null : f.id;
        body = h('div', { class: 'f-body' },
          h('div', { class: 'qa' },
            ft.why ? h('div', { class: 'qa-box' }, h('h4', null, icon('bulb', 15), t('f.why')), h('p', null, ft.why)) : null,
            ft.how ? h('div', { class: 'qa-box how' }, h('h4', null, icon('shield', 15), t('f.how')), h('p', null, ft.how)) : null),
          h('div', { class: 'it-list' }, f.items.map((it) => itemRow(it, maxSize, ownRule, pick))),
          f.count > f.items.length ? h('div', { class: 'more' }, t('f.more', { n: nf(f.count - f.items.length) })) : null);
      }
      return h('section', { class: 'card finding act-' + f.act + (open ? ' open' : ''), id: 'f-' + f.id.replace(/[^a-z0-9_]/gi, '-') }, headRow, body);
    });

    // bulk clean-up: an intro card, and a bar that follows the page while something is ticked
    let cleanCard = null;
    let cleanBar = null;
    if (cleaning) {
      const all = cleanables();
      if (all.length) {
        cleanCard = h('section', { class: 'card cleancard' },
          h('div', { class: 'card-head' },
            h('div', null, h('h2', null, icon('trash', 18), t('clean.title')),
              h('p', { class: 'sub' }, t('clean.lead', { size: fmtSize(all.reduce((a, it) => a + it.size, 0)), n: nf(all.length) }))),
            h('div', { class: 'actions' },
              h('button', { class: 'btn ghost', onclick: () => { for (const it of all) sel.add(it.id); render(); } }, icon('check', 16), t('clean.selectall')),
              h('button', { class: 'btn ghost', 'data-tip': t('clean.selectold.tip'), onclick: () => {
                sel.clear();
                const cut = Date.now() / 1000 - OLD_DAYS * DAY;
                for (const it of all) { const used = it.used || it.newest; if (used && used < cut) sel.add(it.id); }
                render();
              } }, icon('clock', 16), t('clean.selectold', { days: OLD_DAYS })),
              state.meta && state.meta.cleanLog
                ? h('button', { class: 'btn ghost', 'data-tip': t('clean.log.tip'), onclick: showCleanLog }, icon('folder', 16), t('clean.log.history')) : null)));
      }
      if (sel.size) {
        cleanBar = h('div', { class: 'cleanbar' },
          h('div', null, h('b', null, t('clean.bar', { n: nf(sel.size) })), h('span', null, '≈ ' + fmtSize(selSize()))),
          h('button', { class: 'btn ghost', onclick: () => { sel.clear(); render(); } }, t('clean.none')),
          h('button', { class: 'btn danger', disabled: state.clean.busy, onclick: openCleanPlan }, icon('trash', 16), t('clean.go')));
      }
    }
    const stale = state.clean.stale ? h('div', { class: 'note warn' }, icon('alert', 16), h('span', null, t('clean.stale') + ' '),
      h('button', { class: 'btn ghost sm', onclick: rescan }, icon('refresh', 14), t('clean.done.rescan'))) : null;

    return h('div', { class: 'page' },
      pageHead(t('f.title'), t('f.sub')),
      stale, tiles, cleanCard, filters,
      cards.length ? cards : h('div', { class: 'empty card' }, t('f.empty')),
      cleanBar);
  }

  // ── clean-up: tick → the server validates and lists → confirm → delete ──

  const canClean = () => !!(state.meta && state.meta.canClean && state.summary);
  const RECENT_DAYS = 7;       // "you used this recently" — be careful
  const OLD_DAYS = 30;         // "untouched for a month" — the cautious selection
  const usedRecently = (ts, days) => !!ts && ts > Date.now() / 1000 - (days || RECENT_DAYS) * DAY;

  function cleanables() {
    const out = [];
    for (const f of state.summary.findings) {
      if (f.clean) for (const it of f.items) if (it.clean) out.push(it);
    }
    return out;
  }

  function selSize() {
    let total = 0;
    for (const it of cleanables()) if (state.clean.sel.has(it.id)) total += it.size;
    return total;
  }

  function checkbox(kind, onToggle, label, tipText) {
    const el = h('span', {
      class: 'cb ' + kind, role: 'checkbox', 'aria-label': label, 'data-tip': tipText || null,
      'aria-checked': kind === 'on' ? 'true' : kind === 'some' ? 'mixed' : 'false',
      'aria-disabled': kind === 'disabled' ? 'true' : null, tabindex: kind === 'disabled' ? null : '0',
    }, kind === 'on' ? icon('tick', 14) : kind === 'some' ? icon('minus', 14) : null);
    const stop = (e) => { e.stopPropagation(); e.preventDefault(); };
    el.addEventListener('click', (e) => { stop(e); if (onToggle) onToggle(); });
    el.addEventListener('keydown', (e) => { if (e.key === ' ' || e.key === 'Enter') { stop(e); if (onToggle) onToggle(); } });
    return el;
  }

  function rescan() {
    state.clean.modal = null;
    const roots = state.summary ? state.summary.volumes.map((v) => v.path) : [];
    if (roots.length) startScan(roots); else { state.view = 'welcome'; render(); }
  }

  async function openCleanPlan() {
    const c = state.clean;
    if (c.busy || !c.sel.size) return;
    c.busy = true;
    try {
      c.plan = await api('/api/clean/plan', { nodes: Array.from(c.sel) });   // the server decides what is really safe
      c.ok = false;
      c.modal = 'confirm';
    } catch (e) {
      c.error = e.message;
      c.modal = 'error';
    }
    c.busy = false;
    render();
  }

  async function runCleanPlan() {
    const c = state.clean;
    if (!c.plan || !c.ok) return;
    try {
      await api('/api/clean/run', { token: c.plan.token, lang: state.lang });
      if (state.meta) state.meta.cleanLog = true;
      c.job = { state: 'running', planned: c.plan.total, freed: 0, files: 0, skipped: 0, current: '' };
      c.modal = 'running';
      render();
      pollClean();
    } catch (e) {
      c.error = e.message;
      c.modal = 'error';
      render();
    }
  }

  function pollClean() {
    setTimeout(async () => {
      const c = state.clean;
      try {
        const st = await api('/api/clean/status');
        c.job = st;
        if (st.state === 'running') { render(); pollClean(); return; }
        c.modal = 'done';
        c.stale = true;
        c.sel = new Set();
        c.plan = null;
        render();
        try { state.meta = await api('/api/meta'); } catch (e) { /* keep the old numbers */ }
      } catch (e) {
        pollClean();
      }
    }, 400);
  }

  function closeCleanModal() {
    const c = state.clean;
    if (c.modal === 'running') return;
    c.modal = null;
    c.plan = null;
    c.ok = false;
    render();
  }

  function cleanModal() {
    const c = state.clean;
    let body;
    if (c.modal === 'confirm') {
      const p = c.plan;
      const days = p.targets.reduce((m, x) => Math.max(m, x.keepDays || 0), 0);
      const doIt = h('button', { class: 'btn danger', disabled: !c.ok, onclick: runCleanPlan }, icon('trash', 16), t('clean.confirm.do'));
      const agree = h('input', { type: 'checkbox', onchange: (e) => { c.ok = e.target.checked; doIt.disabled = !c.ok; } });
      agree.checked = c.ok;
      // programs the user worked in during the last days: say so, and offer to leave them out
      const rdays = p.recentDays || RECENT_DAYS;
      // (temp folders are always "in use"; there the cleaner itself keeps everything touched recently)
      const isRecentUse = (x) => !x.keepDays && usedRecently(x.used, rdays);
      const recent = p.targets.filter(isRecentUse);
      const apps = [];
      for (const x of recent.slice().sort((a, b) => b.used - a.used)) {
        const label = (x.app || baseName(x.path)) + ' (' + ago(x.used) + ')';
        if (!apps.includes(label)) apps.push(label);
      }
      const dropRecent = async () => {
        for (const x of recent) c.sel.delete(x.id);
        if (!c.sel.size) { closeCleanModal(); return; }
        await openCleanPlan();
      };
      body = [
        h('h2', null, icon('alert', 20), t('clean.confirm.title')),
        h('p', null, p.targets.length ? t('clean.confirm.lead', { n: nf(p.targets.length), size: fmtSize(p.total) }) : t('clean.confirm.empty')),
        p.targets.length ? h('div', { class: 'plan-list' }, p.targets.map((x) => {
          const isRecent = isRecentUse(x);
          const meta = x.keepDays ? t('clean.confirm.temp', { days: x.keepDays })
            : x.used ? (x.app ? x.app + ' · ' : '') + t('clean.confirm.used', { ago: ago(x.used) }) : '';
          return h('div', { class: 'plan-row' + (isRecent ? ' recent' : '') },
            h('div', { class: 'plan-path' }, h('code', null, x.path),
              meta ? h('span', { class: 'plan-meta' }, isRecent ? icon('clock', 13) : null, meta) : null),
            h('b', { class: 'num' }, fmtSize(x.size)));
        })) : null,
        recent.length ? h('div', { class: 'note warn recent-note' }, icon('clock', 16),
          h('span', null, t('clean.confirm.recent', { n: nf(recent.length), days: rdays, apps: apps.slice(0, 8).join(', ') + (apps.length > 8 ? '…' : '') })),
          h('button', { class: 'btn ghost sm', onclick: dropRecent }, t('clean.confirm.dropRecent'))) : null,
        p.targets.length ? h('div', { class: 'note crit' }, icon('alert', 16), t('clean.confirm.w1')) : null,
        p.targets.length ? h('div', { class: 'note warn' }, icon('lock', 16),
          h('span', null, t('clean.confirm.w2'), p.running && p.running.length ? ' ' + t('clean.confirm.running', { apps: p.running.join(', ') }) : '')) : null,
        days ? h('div', { class: 'note' }, icon('clock', 16), t('clean.confirm.temp', { days })) : null,
        p.rejected.length ? h('div', { class: 'note' }, icon('shield', 16), t('clean.confirm.rejected', { n: nf(p.rejected.length) })) : null,
        p.targets.length ? h('label', { class: 'agree' }, agree, h('span', null, t('clean.confirm.check'))) : null,
        h('div', { class: 'modal-actions' },
          h('button', { class: 'btn ghost', onclick: closeCleanModal }, t('clean.confirm.cancel')),
          p.targets.length ? doIt : null),
      ];
    } else if (c.modal === 'running') {
      const j = c.job || {};
      const pct = j.planned ? Math.min(100, (100 * (j.freed || 0)) / j.planned) : 0;
      const cur = j.current || '';
      body = [
        h('h2', null, icon('trash', 20), t('clean.run.title')),
        h('div', { class: 'progress' }, h('i', { style: 'width:' + pct + '%' })),
        h('div', { class: 'tiles mini' },
          h('div', { class: 'tile' }, h('b', null, fmtSize(j.freed || 0)), h('span', null, t('clean.run.freed'))),
          h('div', { class: 'tile' }, h('b', null, nf(j.files || 0)), h('span', null, t('clean.run.files'))),
          h('div', { class: 'tile' }, h('b', null, nf(j.skipped || 0)), h('span', null, t('clean.run.skipped')))),
        h('div', { class: 'scan-path' }, cur.length > 80 ? '…' + cur.slice(-79) : cur),
        h('div', { class: 'modal-actions' },
          h('button', { class: 'btn ghost', onclick: () => api('/api/clean/cancel', {}).catch(() => {}) }, icon('stop', 16), t('clean.run.stop'))),
      ];
    } else if (c.modal === 'done') {
      const j = c.job || {};
      const ok = j.state === 'done';
      const refused = (j.targets || []).filter((x) => x.why).length;
      const line = (text) => h('li', null, text);
      body = [
        h('h2', null, icon(ok ? 'check' : 'alert', 20), t(ok ? 'clean.done.title' : j.state === 'cancelled' ? 'clean.done.cancelled' : 'clean.done.error')),
        h('div', { class: 'hero-fig' }, fmtSize(j.freed || 0), h('small', null, t('clean.done.freed'))),
        h('ul', { class: 'done-list' },
          line(t('clean.done.files', { n: nf(j.files || 0) })),
          j.skipped ? line(t('clean.done.skipped', { n: nf(j.skipped) })) : null,
          j.kept ? line(t('clean.done.kept', { n: nf(j.kept) })) : null,
          j.protected ? line(t('clean.done.protected', { n: nf(j.protected) })) : null,
          refused ? line(t('clean.done.refused', { n: nf(refused) })) : null),
        j.freeBefore != null && j.freeAfter != null
          ? h('div', { class: 'note good' }, icon('disk', 16), t('clean.done.free', { before: fmtSize(j.freeBefore), after: fmtSize(j.freeAfter) })) : null,
        j.error ? h('div', { class: 'note crit' }, icon('alert', 16), j.error) : null,
        j.logError ? h('div', { class: 'note warn' }, icon('alert', 16), t('clean.log.failed')) : null,
        h('p', { class: 'muted' }, t('clean.done.stale')),
        h('div', { class: 'modal-actions' },
          j.log && !j.logError ? h('button', { class: 'btn ghost', 'data-tip': t('clean.log.tip'), onclick: showCleanLog }, icon('folder', 16), t('clean.log.show')) : null,
          h('button', { class: 'btn ghost', onclick: closeCleanModal }, t('clean.done.close')),
          h('button', { class: 'btn primary', onclick: rescan }, icon('refresh', 16), t('clean.done.rescan'))),
      ];
    } else {
      body = [
        h('h2', null, icon('alert', 20), t('clean.done.error')),
        h('div', { class: 'note crit' }, icon('alert', 16), c.error || ''),
        h('div', { class: 'modal-actions' }, h('button', { class: 'btn ghost', onclick: closeCleanModal }, t('clean.done.close'))),
      ];
    }
    return h('div', { class: 'overlay' }, h('div', { class: 'modal card', role: 'dialog', 'aria-modal': 'true' }, body));
  }

  // ── large files ────────────────────────────────────────────────────────

  function viewFiles() {
    const s = state.summary;
    const fs = state.files;
    const groups = {};
    for (const f of s.bigfiles) groups[f.group] = (groups[f.group] || 0) + f.size;
    const order = Object.keys(groups).sort((a, b) => groups[b] - groups[a]);
    const listBox = h('div', { class: 'tbl-body' });
    const fill = () => {
      const q = fs.q.trim().toLowerCase();
      const rows = s.bigfiles.filter((f) => (fs.group === 'all' || f.group === fs.group) && (!q || f.path.toLowerCase().includes(q)));
      const maxSize = rows.length ? rows[0].size : 1;
      listBox.replaceChildren(...(rows.length ? rows.slice(0, 250).map((f) => {
        const rt = ruleText(f.rule);
        const row = h('div', { class: 'it-row files' },
          h('span', { class: 'ex-ico file' }, icon('file', 16)),
          h('div', { class: 'it-name' }, h('b', null, f.name), rt ? chip(rt.title, 'act-' + rt.act, ACT_ICON[rt.act], rt.what) : null,
            h('span', { class: 'path' }, dirName(f.path))),
          h('span', { class: 'dim' }, t('grp.' + f.group)),
          bar(f.size, maxSize),
          h('b', { class: 'num' }, fmtSize(f.size)),
          h('span', { class: 'dim when' }, ago(f.mtime)),
          h('button', { class: 'btn icon sm', 'aria-label': t('d.reveal'), 'data-tip': t('d.reveal'), onclick: (e) => { e.stopPropagation(); reveal(f.path); } }, icon('external', 16)));
        return clickable(row, () => openDrawer({ t: 'f', id: f.dir, name: f.name, path: f.path, size: f.size, newest: f.mtime, rule: f.rule, group: f.group }));
      }) : [h('div', { class: 'empty' }, t('files.empty'))]));
    };
    const pills = h('div', { class: 'filters' },
      h('button', { class: 'pill' + (fs.group === 'all' ? ' on' : ''), onclick: () => { fs.group = 'all'; render(); } }, t('f.filter.all')),
      order.map((g) => h('button', { class: 'pill' + (fs.group === g ? ' on' : ''), onclick: () => { fs.group = g; render(); } },
        t('grp.' + g), h('span', { class: 'pill-n' }, fmtSize(groups[g])))));
    const search = h('label', { class: 'search' }, icon('search', 16),
      h('input', { type: 'search', placeholder: t('files.search'), value: fs.q, oninput: (e) => { fs.q = e.target.value; fill(); } }));
    fill();
    return h('div', { class: 'page' },
      pageHead(t('files.title'), t('files.sub', { n: nf(s.bigfiles.length) }), search),
      pills,
      h('section', { class: 'card flush' }, listBox));
  }

  // ── projects ───────────────────────────────────────────────────────────

  function viewProjects() {
    const s = state.summary;
    const ps = state.proj;
    const list = s.projects.slice().sort(ps.sort === 'age' ? (a, b) => (b.days - a.days) || (b.size - a.size) : (a, b) => b.size - a.size);
    const maxSize = list.reduce((m, p) => Math.max(m, p.size), 1);
    const status = (p) => (p.days < 0 ? null : p.days >= 180 ? chip(t('pr.stale'), 'act-review', 'eye') : p.days >= 30 ? chip(t('pr.idle'), 'act-info', 'clock') : chip(t('pr.active'), 'act-safe', 'check'));
    const rows = list.map((p) => {
      const row = h('div', { class: 'it-row proj' },
        h('span', { class: 'ex-ico dir' }, icon('code', 16)),
        h('div', { class: 'it-name' }, h('b', null, p.name), h('span', { class: 'path' }, dirName(p.path))),
        h('span', { class: 'dim kinds' }, p.kinds.map((k) => KIND_NAME[k] || k).join(' · ')),
        h('div', { class: 'split', 'data-tip': t('pr.legend.regen') + ': ' + fmtSize(p.regen) + '\n' + t('pr.legend.src') + ': ' + fmtSize(p.size - p.regen) },
          h('div', { class: 'bar two', style: 'width:' + Math.max(4, (100 * p.size) / maxSize) + '%' },
            h('i', { class: 'regen', style: 'width:' + (p.size ? (100 * p.regen) / p.size : 0) + '%' }))),
        h('b', { class: 'num' }, fmtSize(p.size)),
        h('span', { class: 'num dim' }, p.regen > 1048576 ? fmtSize(p.regen) : '–'),
        h('span', { class: 'dim when' }, p.days >= 0 ? ago(p.newest) : ''),
        h('span', null, status(p)));
      return clickable(row, () => openDrawer({ t: 'd', id: p.id, name: p.name, path: p.path, size: p.size, newest: p.newest, files: p.files, open: true, projectItem: p }));
    });
    const sortBtn = (key) => h('button', { class: 'pill' + (ps.sort === key ? ' on' : ''), onclick: () => { ps.sort = key; render(); } }, t('pr.sort.' + key));
    return h('div', { class: 'page' },
      pageHead(t('pr.title'), t('pr.sub'), h('div', { class: 'filters' }, sortBtn('size'), sortBtn('age'))),
      h('div', { class: 'tm-legend left' },
        h('span', null, h('i', { class: 'sw regen' }), t('pr.legend.regen')),
        h('span', null, h('i', { class: 'sw src' }), t('pr.legend.src'))),
      h('section', { class: 'card flush' },
        h('div', { class: 'it-row proj headrow' }, h('span', null), h('span', null, t('pr.name')), h('span', null, t('pr.kind')), h('span', null),
          h('span', { class: 'num' }, t('pr.size')), h('span', { class: 'num' }, t('pr.regen')), h('span', null, t('pr.last')), h('span', null, t('pr.status'))),
        rows.length ? rows : h('div', { class: 'empty' }, t('pr.empty'))));
  }

  // ── programs ───────────────────────────────────────────────────────────

  async function loadApps() {
    try { state.apps = (await api('/api/apps')).apps; } catch (e) { state.apps = []; }
    if (state.view === 'apps') render();
  }

  function viewApps() {
    const listBox = h('div', { class: 'tbl-body' });
    const fill = () => {
      if (!state.apps) { listBox.replaceChildren(h('div', { class: 'empty' }, t('misc.loading'))); return; }
      const q = state.appsQ.trim().toLowerCase();
      const rows = state.apps.filter((a) => !q || (a.name + ' ' + a.publisher).toLowerCase().includes(q));
      const maxSize = rows.reduce((m, a) => Math.max(m, a.size), 1);
      listBox.replaceChildren(...(rows.length ? rows.map((a) => {
        const d = a.installed && a.installed.length === 8 ? a.installed.slice(6) + '.' + a.installed.slice(4, 6) + '.' + a.installed.slice(0, 4) : '';
        const row = h('div', { class: 'it-row apps' },
          h('span', { class: 'ex-ico' }, icon('apps', 16)),
          h('div', { class: 'it-name' }, h('b', null, a.name), h('span', { class: 'path' }, [a.publisher, a.version].filter(Boolean).join(' · '))),
          bar(a.size, maxSize),
          h('b', { class: 'num' }, a.size ? (a.measured ? '' : '≈ ') + fmtSize(a.size) : '–'),
          h('span', { class: 'dim when' }, d),
          a.location ? h('button', { class: 'btn icon sm', 'aria-label': t('d.reveal'), 'data-tip': t('d.reveal'), onclick: (e) => { e.stopPropagation(); reveal(a.location); } }, icon('external', 16)) : h('span', null));
        return a.id != null ? clickable(row, () => openNode(a.id)) : row;
      }) : [h('div', { class: 'empty' }, t('apps.empty'))]));
    };
    fill();
    const search = h('label', { class: 'search' }, icon('search', 16),
      h('input', { type: 'search', placeholder: t('apps.search'), value: state.appsQ, oninput: (e) => { state.appsQ = e.target.value; fill(); } }));
    return h('div', { class: 'page' },
      pageHead(t('apps.title'), t('apps.sub'), search),
      h('p', { class: 'note' }, icon('info', 16), t('apps.how')),
      h('section', { class: 'card flush' },
        h('div', { class: 'it-row apps headrow' }, h('span', null), h('span', null, t('apps.name')), h('span', null), h('span', { class: 'num' }, t('apps.size')), h('span', null, t('apps.date')), h('span', null)),
        listBox));
  }

  // ── WSL ────────────────────────────────────────────────────────────────

  async function loadWsl() {
    try { state.wsl = (await api('/api/wsl')).distros; } catch (e) { state.wsl = []; }
    for (const d of state.wsl) {
      if (d.job && d.job.state === 'done' && !state.wslRes[d.name]) fetchWslResult(d.name);
      if (d.job && d.job.state === 'running') pollWsl(d.name);
    }
    if (state.view === 'wsl') render();
  }

  async function fetchWslResult(name) {
    try {
      const r = await api('/api/wsl/result?name=' + encodeURIComponent(name));
      if (r.state === 'done') state.wslRes[name] = r.result;
      const d = (state.wsl || []).find((x) => x.name === name);
      if (d) d.job = { state: r.state, error: r.error };
      if (state.view === 'wsl') render();
      return r.state;
    } catch (e) { return 'error'; }
  }

  const polling = new Set();
  function pollWsl(name) {
    if (polling.has(name)) return;
    polling.add(name);
    const tick = async () => {
      const st = await fetchWslResult(name);
      if (st === 'running') setTimeout(tick, 1500); else polling.delete(name);
    };
    setTimeout(tick, 1200);
  }

  async function scanWsl(name) {
    try {
      await api('/api/wsl/scan', { name });
      const d = state.wsl.find((x) => x.name === name);
      if (d) d.job = { state: 'running' };
      delete state.wslRes[name];
      render();
      pollWsl(name);
    } catch (e) { alert(e.message); }
  }

  function wslTree(node, total, depth, prefix) {
    const rows = [];
    for (const c of node.children) {
      const key = prefix + c.path;
      const open = state.wslOpen.has(key);
      const rt = ruleText(c.rule);
      const row = h('div', { class: 'it-row wsl', style: 'padding-left:' + (14 + depth * 22) + 'px' },
        h('span', { class: 'chev' + (open ? ' open' : '') + (c.children.length ? '' : ' none') }, icon('right', 14)),
        h('div', { class: 'it-name' }, h('b', null, depth ? c.name : c.path), rt ? chip(rt.title, 'act-' + rt.act, ACT_ICON[rt.act], rt.what) : null),
        bar(c.size, total),
        h('b', { class: 'num' }, fmtSize(c.size)),
        rt ? h('button', { class: 'btn icon sm', 'aria-label': t('ex.details'), 'data-tip': t('ex.details'),
          onclick: (e) => { e.stopPropagation(); openDrawer({ t: 'd', name: c.path, path: c.path, size: c.size, rule: c.rule, foreign: true }); } }, icon('info', 16)) : h('span', null));
      rows.push(c.children.length ? clickable(row, () => { if (open) state.wslOpen.delete(key); else state.wslOpen.add(key); render(); }) : row);
      if (open) rows.push(...wslTree(c, total, depth + 1, prefix));
    }
    return rows;
  }

  function viewWsl() {
    const distros = state.wsl;
    const body = [];
    if (!distros) body.push(h('div', { class: 'empty card' }, t('misc.loading')));
    else if (!distros.length) body.push(h('div', { class: 'empty card' }, t('wsl.none')));
    else {
      for (const d of distros) {
        const res = state.wslRes[d.name];
        const running = d.job && d.job.state === 'running';
        const parts = [
          h('div', { class: 'card-head' },
            h('div', null,
              h('h2', null, icon('terminal', 18), d.name, chip(d.running ? t('wsl.running') : t('wsl.stopped'), d.running ? 'act-safe' : '', d.running ? 'check' : null),
                d.internal ? chip(t('wsl.internal'), '') : null),
              h('p', { class: 'sub path' }, d.vhdx || d.base)),
            h('div', { class: 'f-num' }, h('b', null, fmtSize(d.vhdxSize)), h('span', null, t('wsl.vhdx')))),
        ];
        if (!d.internal) {
          parts.push(h('div', { class: 'actions' },
            h('button', { class: 'btn primary', disabled: running, onclick: () => scanWsl(d.name) }, icon('search', 16), res ? t('wsl.rescan') : t('wsl.scan')),
            d.vhdx ? h('button', { class: 'btn ghost', onclick: () => reveal(d.vhdx) }, icon('external', 16), t('d.reveal')) : null,
            h('span', { class: 'muted' }, running ? t('wsl.scanning') : t('wsl.scan.note'))));
          if (running) parts.push(h('div', { class: 'progress' }, h('i', { class: 'indet' })));
          if (d.job && d.job.state === 'error') {
            const err = d.job.error || '';
            parts.push(h('div', { class: 'note crit' }, icon('alert', 16), t('wsl.error') + ': ' + err));
            if (/HCS_E_|CreateVm|0x8037|VirtualMachinePlatform/i.test(err)) {
              parts.push(h('div', { class: 'qa-box how' }, h('h4', null, icon('bulb', 15), t('wsl.novm.title')),
                h('p', null, t('wsl.novm')), h('p', { class: 'muted' }, t('wsl.novm.how'))));
            }
          }
        }
        if (res) {
          const gain = Math.max(0, d.vhdxSize - res.used);
          const worth = gain > (1 << 30) && gain > d.vhdxSize * 0.05;
          parts.push(h('div', { class: 'wsl-facts' },
            h('div', { class: 'fact big' }, h('b', null, fmtSize(res.used)), h('span', null, t('wsl.used'))),
            h('div', { class: 'fact big' }, h('b', null, fmtSize(d.vhdxSize)), h('span', null, t('wsl.ondisk'))),
            h('div', { class: 'fact big' + (worth ? ' gain' : '') }, h('b', null, fmtSize(gain)), h('span', null, t('wsl.slack')))));
          parts.push(h('div', { class: 'meter big ok' }, h('i', { style: 'width:' + Math.min(100, (100 * res.used) / (d.vhdxSize || 1)) + '%' })));
          parts.push(h('p', { class: 'note' + (worth ? ' good' : '') }, icon(worth ? 'bulb' : 'info', 16),
            worth ? t('wsl.slack.text', { vhdx: fmtSize(d.vhdxSize), used: fmtSize(res.used), gain: fmtSize(gain) }) : t('wsl.slack.none')));
          if (worth && d.vhdx) {
            const cmd = 'wsl --shutdown\ndiskpart\n  select vdisk file="' + d.vhdx + '"\n  attach vdisk readonly\n  compact vdisk\n  detach vdisk\n  exit';
            parts.push(h('div', { class: 'codebox' },
              h('div', { class: 'code-head' }, h('b', null, t('wsl.compact')),
                h('button', { class: 'btn ghost sm', onclick: (e) => copyText(cmd, e.currentTarget) }, icon('copy', 14), h('span', { class: 'lbl' }, t('misc.copy')))),
              h('pre', null, cmd),
              h('p', { class: 'muted' }, t('wsl.compact.note'))));
          }
          parts.push(h('h3', null, t('wsl.inside')));
          parts.push(h('div', { class: 'it-list flush' }, wslTree(res.tree, res.used || res.tree.size || 1, 0, d.name + ':')));
        }
        if (!d.internal) {
          const cmd = 'wsl --unregister ' + d.name;
          parts.push(h('div', { class: 'codebox' },
            h('div', { class: 'code-head' }, h('b', null, t('wsl.unreg')),
              h('button', { class: 'btn ghost sm', onclick: (e) => copyText(cmd, e.currentTarget) }, icon('copy', 14), h('span', { class: 'lbl' }, t('misc.copy')))),
            h('pre', null, cmd),
            h('p', { class: 'muted' }, t('wsl.unreg.text', { size: fmtSize(d.vhdxSize) }))));
        }
        body.push(h('section', { class: 'card' }, parts));
      }
    }
    const hasVirt = state.summary && state.summary.findings.some((f) => f.cat === 'virtual');
    return h('div', { class: 'page' },
      pageHead(t('wsl.title'), t('wsl.sub')),
      body,
      hasVirt ? h('section', { class: 'card' }, h('h2', null, t('wsl.others')), h('p', { class: 'sub' }, t('wsl.others.sub')),
        h('button', { class: 'btn ghost', onclick: () => { state.find = { act: 'all', cat: 'virtual', open: new Set() }; go('findings'); } },
          t('wsl.others.go'), icon('right', 16))) : null);
  }

  // ── details drawer ─────────────────────────────────────────────────────

  function openDrawer(item) {
    state.drawer = item;
    render();
  }

  function closeDrawer() {
    state.drawer = null;
    render();
  }

  function drawerEl() {
    const it = state.drawer;
    const isDir = it.t !== 'f';
    const rt = ruleText(it.rule);
    const s = state.summary;
    const used = s ? s.volumes.reduce((a, v) => a + (v.isVolume ? v.used : v.scanned), 0) : 0;
    const proj = it.project || (it.projectItem ? { kinds: it.projectItem.kinds, regen: it.projectItem.regen, newest: it.projectItem.newest } : null);
    const sections = [];
    if (rt) {
      sections.push(h('div', { class: 'd-sec' }, badge(rt.act), h('h3', null, rt.title), h('p', null, rt.what)));
      if (rt.why) sections.push(h('div', { class: 'qa-box' }, h('h4', null, icon('bulb', 15), t('f.why')), h('p', null, rt.why)));
      if (rt.how) sections.push(h('div', { class: 'qa-box how' }, h('h4', null, icon('shield', 15), t('f.how')), h('p', null, rt.how)));
    }
    if (proj) {
      const sp = span(proj.newest);
      sections.push(h('div', { class: 'qa-box' }, h('h4', null, icon('code', 15), t('d.project')),
        h('p', null, t('d.project.text', { kinds: proj.kinds.map((k) => KIND_NAME[k] || k).join(' + '), ago: ago(proj.newest) })),
        proj.regen > 1048576 ? h('p', null, t('d.project.regen', { size: fmtSize(proj.regen), pct: fmtPct(proj.regen, it.size) })) : null,
        sp && sp.days >= 180 ? h('p', { class: 'nudge' }, icon('clock', 15), t('d.project.stale')) : null));
    }
    if (!rt && !proj) {
      sections.push(h('div', { class: 'd-sec' }, h('p', { class: 'muted' }, isDir ? t('d.norule.dir') : (it.group ? t('grp.' + it.group) + ' — ' : '') + t('d.norule.file'))));
    }
    const sp2 = span(it.newest);
    if (!proj && sp2 && sp2.days >= 365 && (!rt || rt.act === 'review' || rt.act === 'info') && !it.foreign) {
      sections.push(h('p', { class: 'nudge' }, icon('clock', 15), t('d.old', { for: forSpan(it.newest) })));
    }
    const fact = (label, value) => h('div', { class: 'fact' }, h('span', null, label), h('b', null, value));
    const panel = h('aside', { class: 'drawer', role: 'dialog', 'aria-label': it.name },
      h('div', { class: 'd-head' },
        h('span', { class: 'ex-ico big ' + (isDir ? 'dir' : 'file') }, icon(isDir ? 'folder' : 'file', 24)),
        h('h2', null, it.name),
        h('button', { class: 'btn icon', 'aria-label': t('misc.close'), onclick: closeDrawer }, icon('close', 18))),
      h('div', { class: 'd-facts' },
        fact(t('d.size'), fmtSize(it.size)),
        used && !it.foreign ? fact(t('d.share'), fmtPct(it.size, used)) : null,
        isDir && it.files != null ? fact(t('d.files'), nf(it.files)) : null,
        it.newest ? fact(t('d.changed'), ago(it.newest)) : null),
      h('div', { class: 'd-path' }, h('span', null, t('d.path')), h('code', null, it.path)),
      sections,
      it.foreign ? null : h('div', { class: 'd-actions' },
        h('button', { class: 'btn primary', onclick: () => reveal(it.path) }, icon('external', 16), t('d.reveal')),
        isDir && it.open && it.id != null ? h('button', { class: 'btn ghost', onclick: () => openNode(it.id) }, icon('folder', 16), t('d.open')) : null,
        h('button', { class: 'btn ghost', onclick: (e) => copyText(it.path, e.currentTarget) }, icon('copy', 16), h('span', { class: 'lbl' }, t('d.copy')))),
      h('p', { class: 'ro-note' }, icon('shield', 14), t('app.readonly.tip')));
    return h('div', { class: 'drawer-wrap', onclick: (e) => { if (e.target.classList.contains('drawer-wrap')) closeDrawer(); } }, panel);
  }

  // ── tooltip, keyboard, resize ──────────────────────────────────────────

  const tip = $('#tip');
  function showTip(text, x, y) {
    tip.textContent = text;
    tip.hidden = false;
    const r = tip.getBoundingClientRect();
    tip.style.left = Math.max(8, Math.min(window.innerWidth - r.width - 8, x + 14)) + 'px';
    tip.style.top = (y + 18 + r.height > window.innerHeight ? y - r.height - 10 : y + 18) + 'px';
  }
  document.addEventListener('mousemove', (e) => {
    const el = e.target.closest ? e.target.closest('[data-tip]') : null;
    if (!el || !el.dataset.tip) { tip.hidden = true; return; }
    showTip(el.dataset.tip, e.clientX, e.clientY);
  });
  document.addEventListener('focusin', (e) => {
    const el = e.target.closest ? e.target.closest('[data-tip]') : null;
    if (!el || !el.dataset.tip) { tip.hidden = true; return; }
    const r = el.getBoundingClientRect();
    showTip(el.dataset.tip, r.left, r.bottom - 12);
  });
  document.addEventListener('scroll', () => { tip.hidden = true; }, true);
  document.addEventListener('keydown', (e) => {
    if (e.key !== 'Escape') return;
    if (state.clean.modal && state.clean.modal !== 'running') closeCleanModal();
    else if (state.drawer) closeDrawer();
  });
  let resizeTimer = 0;
  window.addEventListener('resize', () => { clearTimeout(resizeTimer); resizeTimer = setTimeout(afterRender, 120); });

  boot();
})();
