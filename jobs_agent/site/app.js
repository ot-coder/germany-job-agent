// Germany Job Agent — static dashboard + application tracker.
// All personal data lives in this browser's localStorage under STORE_KEY.

const STORE_KEY = 'gja:v1';
const LEGACY_PREFIX = 'job:';
const STATUSES = ['applied', 'waiting', 'interview', 'offer', 'rejected', 'ghosted'];
const STATUS_LABELS = {
  applied: 'Applied', waiting: 'Waiting for response', interview: 'Interview',
  offer: 'Offer', rejected: 'Rejected', ghosted: 'Ghosted',
};
const GHOST_AFTER_DAYS = 14;
const FOLLOW_UP_WINDOW_DAYS = 60; // older silences are not worth chasing
const PROMPT_TTL_MS = 3 * 24 * 60 * 60 * 1000;

const $ = (sel) => document.querySelector(sel);
const esc = (s) => String(s ?? '').replace(/[&<>'"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', "'": '&#39;', '"': '&quot;' }[c]));
const safeUrl = (u) => { try { const url = new URL(String(u)); return /^https?:$/.test(url.protocol) ? url.href : ''; } catch { return ''; } };
const todayISO = () => new Date().toISOString().slice(0, 10);
const newId = () => (crypto.randomUUID ? crypto.randomUUID() : `${Date.now().toString(36)}-${Math.random().toString(36).slice(2)}`);
const dayDiff = (iso) => { const t = Date.parse(iso); return Number.isNaN(t) ? 0 : Math.floor((Date.now() - t) / 86400000); };
const fmtDate = (iso) => { const t = Date.parse(iso); return Number.isNaN(t) ? '—' : new Date(t).toISOString().slice(0, 10); };

// ---------- storage ----------
function emptyState() {
  return { version: 1, jobStates: {}, applications: [], pending: null, settings: {}, migratedLegacy: false };
}
function loadState() {
  try {
    const raw = localStorage.getItem(STORE_KEY);
    if (raw) return { ...emptyState(), ...JSON.parse(raw) };
  } catch { /* private mode or corrupt data: start fresh */ }
  return emptyState();
}
let state = loadState();
let storageOk = true;
function save() {
  try { localStorage.setItem(STORE_KEY, JSON.stringify(state)); storageOk = true; }
  catch { if (storageOk) toast('This browser blocked local storage — changes will be lost when you close the tab.'); storageOk = false; }
}

// ---------- data ----------
let config = { title: 'Germany Job Agent', subtitle: '', categories: [], city: '', gmail_client_id: '' };
let jobs = [];
let jobsById = new Map();
let ui = { view: 'jobs', category: '', appFilter: 'all' };
try { ui.category = sessionStorage.getItem('gja:category') || ''; } catch { /* ignore */ }

function effectiveStatus(app) {
  if (app.status === 'applied' && dayDiff(app.applicationDate) > GHOST_AFTER_DAYS) return 'ghosted';
  return STATUSES.includes(app.status) ? app.status : 'applied';
}
function applicationForJob(jobId) { return state.applications.find((a) => a.jobId === jobId); }
function jobStatus(job) {
  if (applicationForJob(job.id)) return 'applied';
  return state.jobStates[job.id] || 'new';
}

function normalizeApplication(raw) {
  if (!raw || typeof raw !== 'object') return null;
  const company = String(raw.company || '').trim().slice(0, 200);
  const position = String(raw.position || raw.title || '').trim().slice(0, 200);
  if (!company && !position) return null;
  const now = new Date().toISOString();
  const date = Date.parse(raw.applicationDate) ? new Date(raw.applicationDate).toISOString() : now;
  const app = {
    id: String(raw.id || newId()),
    company: company || 'Unknown Company',
    position: position || 'Unknown Position',
    applicationDate: date,
    status: STATUSES.includes(raw.status) ? raw.status : 'applied',
    lastUpdate: Date.parse(raw.lastUpdate) ? new Date(raw.lastUpdate).toISOString() : now,
    createdAt: Date.parse(raw.createdAt) ? new Date(raw.createdAt).toISOString() : now,
    notes: String(raw.notes || '').slice(0, 5000),
  };
  for (const key of ['jobId', 'emailId', 'location', 'source']) if (raw[key]) app[key] = String(raw[key]).slice(0, 300);
  if (safeUrl(raw.url)) app.url = safeUrl(raw.url);
  if (Date.parse(raw.followUpDate)) app.followUpDate = new Date(raw.followUpDate).toISOString();
  return app;
}

function addApplication(raw) {
  const app = normalizeApplication(raw);
  if (!app) return null;
  state.applications.push(app);
  return app;
}

function applicationFromJob(job, extra = {}) {
  return {
    jobId: job.id, company: job.company, position: job.title, location: job.location,
    url: job.url, source: job.source, applicationDate: new Date().toISOString(), status: 'applied', ...extra,
  };
}

function markApplied(job) {
  if (applicationForJob(job.id)) return;
  addApplication(applicationFromJob(job));
  delete state.jobStates[job.id];
  if (state.pending?.jobId === job.id) state.pending = null;
  save();
  toast(`Logged “${job.title}” in My applications.`);
}

// Move per-job states from the previous dashboard (job:<id> keys) into the tracker once.
function migrateLegacy() {
  if (state.migratedLegacy) return;
  let moved = 0;
  try {
    for (let i = 0; i < localStorage.length; i += 1) {
      const key = localStorage.key(i);
      if (!key || !key.startsWith(LEGACY_PREFIX)) continue;
      const id = key.slice(LEGACY_PREFIX.length);
      const value = localStorage.getItem(key);
      if (value === 'saved' || value === 'dismissed') { state.jobStates[id] = value; moved += 1; }
      if (value === 'applied' && !applicationForJob(id)) {
        const job = jobsById.get(id);
        addApplication(job ? applicationFromJob(job, { notes: 'Marked applied on the old dashboard' })
          : { jobId: id, company: 'Unknown Company', position: 'Job no longer listed', notes: 'Marked applied on the old dashboard' });
        moved += 1;
      }
    }
  } catch { return; }
  state.migratedLegacy = true;
  save();
  if (moved) toast(`Moved ${moved} saved/applied marks from the previous dashboard.`);
}

// ---------- rendering: jobs ----------
const ROLE_TYPES = [
  ['werkstudent', 'Werkstudent'], ['internship', 'Internship'], ['entry-level', 'Entry level'],
  ['regular', 'Regular'], ['part-time', 'Part-time'], ['minijob', 'Minijob'],
];

function renderCategoryTabs() {
  const tabs = config.categories.length ? config.categories : [{ id: '', label: 'All jobs' }];
  if (!tabs.some((c) => c.id === ui.category)) ui.category = tabs[0].id;
  const el = $('#category-tabs');
  el.hidden = tabs.length < 2;
  el.innerHTML = tabs.map((c) => `<button type="button" role="tab" class="tab ${c.id === ui.category ? 'active' : ''}" aria-selected="${c.id === ui.category}" data-action="category" data-id="${esc(c.id)}" data-category="${esc(c.id)}">${esc(c.label)}</button>`).join('');
  renderTypeFilter();
}

function activeCategory() {
  return config.categories.find((c) => c.id === ui.category);
}

// Categories with several role families filter by family; others by role type.
function renderTypeFilter() {
  const select = $('#job-type');
  const families = activeCategory()?.families || [];
  const byFamily = families.length > 1;
  const options = byFamily ? families.map((f) => [f.id, f.label]) : ROLE_TYPES;
  const previous = select.value;
  select.dataset.field = byFamily ? 'role_family' : 'role_type';
  select.setAttribute('aria-label', byFamily ? 'Role family' : 'Role type');
  select.innerHTML = `<option value="">${byFamily ? 'All role families' : 'All role types'}</option>`
    + options.map(([value, label]) => `<option value="${esc(value)}">${esc(label)}</option>`).join('');
  if (options.some(([value]) => value === previous)) select.value = previous;
}

// jobs.json written before categories existed has no category: show it in the first tab.
function jobCategory(j) {
  return j.category || config.categories[0]?.id || '';
}

function categoryLabel(id) {
  return config.categories.find((c) => c.id === id)?.label || id;
}

function familyLabel(j) {
  const category = config.categories.find((c) => c.id === jobCategory(j));
  const family = category?.families?.find((f) => f.id === j.role_family);
  if (family && category.families.length > 1) return family.label;
  return categoryLabel(jobCategory(j));
}

function renderJobs() {
  const q = $('#job-search').value.trim().toLowerCase();
  const type = $('#job-type').value;
  const status = $('#job-status').value;
  const inCategory = jobs.filter((j) => !ui.category || jobCategory(j) === ui.category);
  const typeField = $('#job-type').dataset.field || 'role_type';
  const rows = inCategory.filter((j) => {
    const st = jobStatus(j);
    if (status ? st !== status : st === 'dismissed') return false;
    if (type && j[typeField] !== type) return false;
    return !q || `${j.title} ${j.company} ${j.location}`.toLowerCase().includes(q);
  });
  const count = (s) => inCategory.filter((j) => jobStatus(j) === s).length;
  $('#job-stats').innerHTML = [
    `${rows.length} shown`, config.categories.length > 1 ? `${inCategory.length} in this category` : `${inCategory.length} live matches`, `${count('saved')} saved`, `${count('applied')} applied`,
  ].map((t) => `<span class="pill">${esc(t)}</span>`).join('');
  $('#jobs').innerHTML = rows.length ? rows.map(jobCard).join('') : '<div class="empty">No jobs match these filters.</div>';
  $('#jobs-count').textContent = jobs.length ? `(${jobs.length})` : '';
}

function jobCard(j) {
  const st = jobStatus(j);
  const url = safeUrl(j.url);
  const id = esc(j.id);
  const btn = (action, label, on) => `<button type="button" class="${on ? 'active' : ''}" aria-pressed="${on}" data-action="${action}" data-id="${id}">${label}</button>`;
  return `<article class="card ${st === 'dismissed' ? 'is-dismissed' : ''}">
    <div class="row"><div>
      ${url ? `<a class="title" href="${esc(url)}" target="_blank" rel="noreferrer" data-action="open-posting" data-id="${id}">${esc(j.title)}</a>` : `<span class="title">${esc(j.title)}</span>`}
      <div class="company">${esc(j.company)}</div></div>
      <div class="score" title="Match score">${esc(j.score)}</div></div>
    <p class="meta">${esc(j.location)} · ${esc(familyLabel(j))}${j.role_type ? ` · ${esc(j.role_type)}` : ''} · ${esc(j.source)}</p>
    <p class="reasons">${(j.reasons || []).map(esc).join(' · ')}</p>
    <div class="actions">
      ${btn('toggle-saved', 'Save', st === 'saved')}
      ${btn('toggle-applied', st === 'applied' ? 'Applied ✓' : 'Applied', st === 'applied')}
      ${btn('toggle-dismissed', 'Dismiss', st === 'dismissed')}
      ${url ? `<a class="button" href="${esc(url)}" target="_blank" rel="noreferrer" data-action="open-posting" data-id="${id}">Apply ↗</a>` : ''}
    </div></article>`;
}

// ---------- rendering: tracker ----------
function renderTracker() {
  const apps = state.applications.map((a) => ({ ...a, eff: effectiveStatus(a) }));
  const total = apps.length;
  const by = (s) => apps.filter((a) => a.eff === s).length;
  const active = apps.filter((a) => ['applied', 'waiting', 'interview'].includes(a.eff)).length;
  const responseRate = total ? Math.round(((total - by('ghosted')) / total) * 100) : 0;
  $('#tracker-tiles').innerHTML = [
    ['Total applications', total], ['Active', active], ['Interviews', by('interview')],
    ['Offers', by('offer')], ['Response rate', `${responseRate}%`],
  ].map(([label, value]) => `<div class="tile"><div class="label">${label}</div><div class="value">${esc(value)}</div></div>`).join('');
  $('#tracker-count').textContent = total ? `(${total})` : '';

  const ghosted = apps
    .filter((a) => a.eff === 'ghosted' && dayDiff(a.applicationDate) <= FOLLOW_UP_WINDOW_DAYS)
    .sort((a, b) => b.applicationDate.localeCompare(a.applicationDate));
  const ghostRow = (a) => `<li><span><strong>${esc(a.position)}</strong> at ${esc(a.company)} · applied ${fmtDate(a.applicationDate)}</span>
    <button type="button" data-action="follow-up" data-id="${esc(a.id)}">Mark followed up</button></li>`;
  $('#followups').innerHTML = ghosted.length ? `<div class="alert"><h3>Follow-up needed (${ghosted.length})</h3>
    <p>No response for ${GHOST_AFTER_DAYS}–${FOLLOW_UP_WINDOW_DAYS} days. A short, polite follow-up often gets a reply.</p>
    <ul>${ghosted.slice(0, 5).map(ghostRow).join('')}</ul>
    ${ghosted.length > 5 ? `<details><summary>Show ${ghosted.length - 5} more</summary><ul>${ghosted.slice(5).map(ghostRow).join('')}</ul></details>` : ''}</div>` : '';

  const filters = ['all', ...STATUSES];
  $('#status-chips').innerHTML = filters.map((s) => {
    const n = s === 'all' ? total : by(s);
    return `<button type="button" role="tab" class="chip ${ui.appFilter === s ? 'active' : ''}" aria-selected="${ui.appFilter === s}" data-action="app-filter" data-id="${s}">${s === 'all' ? 'All' : STATUS_LABELS[s]} (${n})</button>`;
  }).join('');

  const q = $('#app-search').value.trim().toLowerCase();
  const rows = apps
    .filter((a) => ui.appFilter === 'all' || a.eff === ui.appFilter)
    .filter((a) => !q || `${a.company} ${a.position} ${a.notes} ${a.location || ''}`.toLowerCase().includes(q))
    .sort((a, b) => b.applicationDate.localeCompare(a.applicationDate));
  $('#applications').innerHTML = rows.length ? rows.map(appCard).join('') : (total
    ? '<div class="empty">No applications match.</div>'
    : '<div class="empty">No applications yet. Press <strong>Applied</strong> on a job, add one manually, or import a backup in Settings.</div>');
}

function appCard(a) {
  const url = safeUrl(a.url);
  const id = esc(a.id);
  const days = dayDiff(a.applicationDate);
  const options = STATUSES.map((s) => `<option value="${s}" ${s === a.status ? 'selected' : ''}>${STATUS_LABELS[s]}</option>`).join('');
  return `<article class="card app-card">
    <div class="app-head"><div>
      <div class="app-title">${esc(a.position)}</div>
      <div class="company">${esc(a.company)}</div></div>
      <span class="badge s-${a.eff}">${esc(STATUS_LABELS[a.eff])}</span></div>
    <p class="meta">Applied ${fmtDate(a.applicationDate)} · ${days} day${days === 1 ? '' : 's'} ago${a.location ? ` · ${esc(a.location)}` : ''}${a.followUpDate ? ` · followed up ${fmtDate(a.followUpDate)}` : ''}${a.emailId ? ' · <span class="tag">from Gmail</span>' : ''}${a.jobId && jobsById.has(a.jobId) ? ' · <span class="tag">still listed</span>' : ''}</p>
    ${a.notes ? `<p class="notes">${esc(a.notes)}</p>` : ''}
    <div class="actions">
      <select class="status-select" data-action="set-status" data-id="${id}" aria-label="Status for ${esc(a.position)}">${options}</select>
      ${a.eff === 'ghosted' ? `<button type="button" data-action="follow-up" data-id="${id}">Mark followed up</button>` : ''}
      <button type="button" data-action="edit-app" data-id="${id}">Edit</button>
      ${url ? `<a class="button" href="${esc(url)}" target="_blank" rel="noreferrer">Posting ↗</a>` : ''}
    </div></article>`;
}

// ---------- "did you apply?" prompt ----------
function renderPrompt() {
  const el = $('#prompt');
  const p = state.pending;
  if (p && !jobsById.size) { el.hidden = true; return; } // jobs not loaded yet
  const job = p && jobsById.get(p.jobId);
  if (!p || !job || applicationForJob(p.jobId) || Date.now() - p.at > PROMPT_TTL_MS) {
    el.hidden = true;
    if (p && (!job || applicationForJob(p.jobId) || Date.now() - p.at > PROMPT_TTL_MS)) { state.pending = null; save(); }
    return;
  }
  el.innerHTML = `<p>Did you apply to <strong>${esc(job.title)}</strong> at ${esc(job.company)}?</p>
    <button type="button" class="primary" data-action="prompt-yes" data-id="${esc(job.id)}">Yes, log it</button>
    <button type="button" data-action="prompt-no">Not yet</button>`;
  el.hidden = false;
}

// ---------- view switching ----------
function setView(view) {
  ui.view = view === 'tracker' ? 'tracker' : 'jobs';
  $('#view-jobs').hidden = ui.view !== 'jobs';
  $('#view-tracker').hidden = ui.view !== 'tracker';
  document.querySelectorAll('.view-link').forEach((a) => {
    const on = a.dataset.view === ui.view;
    a.classList.toggle('active', on);
    if (on) a.setAttribute('aria-current', 'page'); else a.removeAttribute('aria-current');
  });
}
function renderAll() {
  renderCategoryTabs();
  renderJobs();
  renderTracker();
  renderPrompt();
}

// ---------- dialogs ----------
function openAppDialog(app) {
  const form = $('#app-form');
  form.reset();
  form.status.innerHTML = STATUSES.map((s) => `<option value="${s}">${STATUS_LABELS[s]}</option>`).join('');
  $('#app-dialog-title').textContent = app ? 'Edit application' : 'Add application';
  $('#delete-app').hidden = !app;
  form.id.value = app?.id || '';
  form.company.value = app?.company || '';
  form.position.value = app?.position || '';
  form.applicationDate.value = app ? fmtDate(app.applicationDate) : todayISO();
  form.status.value = app?.status || 'applied';
  form.location.value = app?.location || '';
  form.url.value = app?.url || '';
  form.notes.value = app?.notes || '';
  $('#app-dialog').showModal();
}

function saveAppForm(event) {
  event.preventDefault();
  const form = event.target;
  const values = Object.fromEntries(new FormData(form));
  values.applicationDate = new Date(`${values.applicationDate}T12:00:00Z`).toISOString();
  const existing = state.applications.find((a) => a.id === values.id);
  if (existing) {
    const updated = normalizeApplication({ ...existing, ...values, lastUpdate: new Date().toISOString() });
    if (!safeUrl(values.url)) delete updated.url;
    if (!values.location) delete updated.location;
    Object.keys(existing).forEach((k) => delete existing[k]);
    Object.assign(existing, updated);
  } else {
    delete values.id;
    addApplication(values);
  }
  save();
  $('#app-dialog').close();
  renderAll();
}

function openSettings() {
  $('#gmail-client-id').value = state.settings.gmailClientId || config.gmail_client_id || '';
  $('#gmail-status').textContent = state.settings.lastGmailScan ? `Last scan: ${new Date(state.settings.lastGmailScan).toLocaleString()}` : '';
  $('#settings-dialog').showModal();
  if ($('#gmail-client-id').value) import('./gmail.js').then((m) => m.preload()).catch(() => {});
}

// ---------- backup ----------
function exportBackup() {
  const data = { app: 'germany-job-agent', exportedAt: new Date().toISOString(), version: 1,
    jobStates: state.jobStates, applications: state.applications };
  const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' });
  const a = document.createElement('a');
  a.href = URL.createObjectURL(blob);
  a.download = `job-agent-backup-${todayISO()}.json`;
  a.click();
  setTimeout(() => URL.revokeObjectURL(a.href), 1000);
}

async function importBackup(file) {
  let data;
  try { data = JSON.parse(await file.text()); } catch { toast('That file is not valid JSON.'); return; }
  // Accept our own backups and the old job-tracker export (a plain array of applications).
  const incoming = Array.isArray(data) ? data : Array.isArray(data?.applications) ? data.applications : null;
  if (!incoming) { toast('No applications found in that file.'); return; }
  const ids = new Set(state.applications.map((a) => a.id));
  const emails = new Set(state.applications.map((a) => a.emailId).filter(Boolean));
  let added = 0;
  for (const raw of incoming) {
    const app = normalizeApplication(raw);
    if (!app || ids.has(app.id) || (app.emailId && emails.has(app.emailId))) continue;
    state.applications.push(app);
    ids.add(app.id);
    if (app.emailId) emails.add(app.emailId);
    added += 1;
  }
  if (data && typeof data.jobStates === 'object' && !Array.isArray(data.jobStates)) {
    for (const [id, st] of Object.entries(data.jobStates)) if (st === 'saved' || st === 'dismissed') state.jobStates[id] ??= st;
  }
  save();
  renderAll();
  toast(`Imported ${added} application${added === 1 ? '' : 's'}${incoming.length - added ? ` (${incoming.length - added} already present or invalid)` : ''}.`);
}

// ---------- gmail ----------
async function scanGmail() {
  const clientId = $('#gmail-client-id').value.trim();
  const status = $('#gmail-status');
  if (!clientId) { status.textContent = 'Add your OAuth client ID first (see the guide).'; return; }
  state.settings.gmailClientId = clientId;
  save();
  const days = Math.min(365, Math.max(1, Number($('#gmail-days').value) || 30));
  try {
    const gmail = await import('./gmail.js');
    const known = new Set(state.applications.map((a) => a.emailId).filter(Boolean));
    const found = await gmail.scan({ clientId, days, skipIds: known, onProgress: (msg) => { status.textContent = msg; } });
    let added = 0;
    for (const hit of found) {
      if (known.has(hit.emailId)) continue;
      const job = gmail.matchJob(hit.company, jobs);
      addApplication(job ? { ...applicationFromJob(job), ...hit, position: hit.position === 'Unknown Position' ? job.title : hit.position } : hit);
      known.add(hit.emailId);
      added += 1;
    }
    state.settings.lastGmailScan = new Date().toISOString();
    save();
    renderAll();
    status.textContent = `Done — ${added} new application${added === 1 ? '' : 's'} added. Review them in My applications; detection is keyword-based and can be wrong.`;
  } catch (error) {
    status.textContent = `Gmail scan failed: ${error.message || error}`;
  }
}

// ---------- events ----------
let toastTimer;
function toast(message) {
  const el = $('#toast');
  el.textContent = message;
  el.hidden = false;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => { el.hidden = true; }, 4500);
}

function toggleJobState(id, value) {
  state.jobStates[id] = state.jobStates[id] === value ? undefined : value;
  if (!state.jobStates[id]) delete state.jobStates[id];
  save();
}

document.addEventListener('click', (event) => {
  const el = event.target.closest('[data-action]');
  if (!el || el.tagName === 'SELECT') return;
  const { action, id } = el.dataset;
  const job = id && jobsById.get(id);
  const app = id && state.applications.find((a) => a.id === id);
  switch (action) {
    case 'category': ui.category = id; try { sessionStorage.setItem('gja:category', id); } catch { /* ignore */ } renderCategoryTabs(); renderJobs(); break;
    case 'toggle-saved': toggleJobState(id, 'saved'); renderJobs(); break;
    case 'toggle-dismissed': toggleJobState(id, 'dismissed'); renderJobs(); break;
    case 'toggle-applied': {
      const existing = applicationForJob(id);
      if (existing) {
        if (!confirm(`Remove “${existing.position}” from My applications?`)) return;
        state.applications = state.applications.filter((a) => a !== existing);
        save();
      } else if (job) markApplied(job);
      renderAll();
      break;
    }
    case 'open-posting':
      if (job && !applicationForJob(job.id)) { state.pending = { jobId: job.id, at: Date.now() }; save(); }
      break; // let the link open normally
    case 'prompt-yes': if (job) markApplied(job); renderAll(); break;
    case 'prompt-no': state.pending = null; save(); renderPrompt(); break;
    case 'app-filter': ui.appFilter = id; renderTracker(); break;
    case 'add-app': openAppDialog(null); break;
    case 'edit-app': if (app) openAppDialog(app); break;
    case 'follow-up':
      if (app) {
        app.status = 'waiting';
        app.followUpDate = new Date().toISOString();
        app.lastUpdate = app.followUpDate;
        app.notes = [app.notes, `Follow-up sent ${todayISO()}`].filter(Boolean).join('\n');
        save(); renderAll();
      }
      break;
    case 'delete-app': {
      const target = state.applications.find((a) => a.id === $('#app-form').id.value);
      if (target && confirm(`Delete “${target.position}” at ${target.company}?`)) {
        state.applications = state.applications.filter((a) => a !== target);
        save(); $('#app-dialog').close(); renderAll();
      }
      break;
    }
    case 'close-dialog': el.closest('dialog')?.close(); break;
    case 'open-settings': openSettings(); break;
    case 'export': exportBackup(); break;
    case 'gmail-scan': scanGmail(); break;
    case 'erase':
      if (confirm('Erase every saved job and application in this browser? Export a backup first if unsure.')) {
        state = { ...emptyState(), migratedLegacy: true };
        save(); renderAll(); $('#settings-dialog').close();
      }
      break;
    default: break;
  }
});

document.addEventListener('change', (event) => {
  const el = event.target;
  if (el.dataset.action === 'set-status') {
    const app = state.applications.find((a) => a.id === el.dataset.id);
    if (app) { app.status = el.value; app.lastUpdate = new Date().toISOString(); save(); renderAll(); }
  }
});

$('#app-form').addEventListener('submit', saveAppForm);
$('#import-file').addEventListener('change', (e) => { const f = e.target.files[0]; if (f) importBackup(f); e.target.value = ''; });
$('#job-search').addEventListener('input', renderJobs);
$('#job-type').addEventListener('change', renderJobs);
$('#job-status').addEventListener('change', renderJobs);
$('#app-search').addEventListener('input', renderTracker);
window.addEventListener('hashchange', () => setView(location.hash.slice(1)));
document.addEventListener('visibilitychange', () => { if (!document.hidden) { state = loadState(); renderAll(); } });
window.addEventListener('storage', (e) => { if (e.key === STORE_KEY) { state = loadState(); renderAll(); } });

// ---------- boot ----------
async function boot() {
  setView(location.hash.slice(1));
  try {
    const res = await fetch(`./config.json?${Date.now()}`);
    if (res.ok) config = { ...config, ...(await res.json()) };
  } catch { /* use defaults */ }
  document.title = config.title;
  $('#title').textContent = config.title;
  $('#subtitle').textContent = config.subtitle || '';
  if (config.generated_at) $('#updated').textContent = `Updated ${new Date(config.generated_at).toLocaleString()}`;
  try {
    const res = await fetch(`./jobs.json?${Date.now()}`);
    if (!res.ok) throw new Error(res.statusText);
    jobs = (await res.json()).sort((a, b) => b.score - a.score);
  } catch {
    $('#jobs').innerHTML = '<div class="empty">Could not load jobs. Please refresh.</div>';
  }
  jobsById = new Map(jobs.map((j) => [j.id, j]));
  migrateLegacy();
  renderAll();
}
boot();
