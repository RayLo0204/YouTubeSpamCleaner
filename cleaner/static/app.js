'use strict';
const $ = id => document.getElementById(id);
const el = (tag, cls, text) => { const node = document.createElement(tag); if (cls) node.className = cls; if (text !== undefined) node.textContent = text; return node; };
const supplied = new URLSearchParams(location.hash.slice(1)).get('session');
if (supplied) { sessionStorage.setItem('cleaner-session', supplied); history.replaceState(null, '', location.pathname); }
const session = sessionStorage.getItem('cleaner-session') || '';
let state = null, page = 'overview', view = 'flagged', offset = 0, selected = new Set(), visibleComments = [];
let polling = false, firstState = true, commentsSignature = '', rulesSignature = '', jobsSignature = '', eventsSignature = '', lastFinished = '', toastTimer;
const labels = { overview:'Overview', comments:'Comment review', rules:'Detection rules', schedule:'Auto-clean', history:'Activity history', settings:'Connection' };
const actionNames = { hold:'move to review', reject:'remove from public view', ban:'remove and block the author', publish:'publish held comments' };

function toast(message, error = false) {
  $('toast').textContent = message; $('toast').classList.toggle('error', error); $('toast').hidden = false;
  clearTimeout(toastTimer); toastTimer = setTimeout(() => { $('toast').hidden = true; }, error ? 9000 : 4500);
}
async function api(path, method = 'GET', body) {
  const response = await fetch('/api/' + path, { method, headers:{ Authorization:'Bearer ' + session, ...(body === undefined ? {} : {'Content-Type':'application/json'}) }, ...(body === undefined ? {} : {body:JSON.stringify(body)}) });
  if (response.status === 401) $('session-error').hidden = false;
  const data = await response.json();
  if (!response.ok) {
    const detail = Array.isArray(data.detail) ? data.detail.map(x => x.msg).join('; ') : data.detail;
    throw new Error(detail || 'The request could not be completed.');
  }
  return data;
}
async function attempt(fn) { try { await fn(); } catch (error) { toast(error.message, true); } }
function navigate(next) {
  page = labels[next] ? next : 'overview';
  document.querySelectorAll('[data-section]').forEach(n => { n.hidden = n.dataset.section !== page; });
  document.querySelectorAll('[data-page]').forEach(n => n.classList.toggle('active', n.dataset.page === page));
  $('page-label').textContent = labels[page];
  if (page === 'comments') attempt(loadComments);
  if (page === 'history') attempt(loadActions);
  window.scrollTo({ top:0, behavior:'instant' });
}
document.querySelectorAll('[data-page]').forEach(n => n.addEventListener('click', () => navigate(n.dataset.page)));
document.querySelectorAll('[data-goto]').forEach(n => n.addEventListener('click', () => navigate(n.dataset.goto)));
document.querySelector('.brand').addEventListener('click', event => { event.preventDefault(); navigate('overview'); });

function confirmAction(title, message) {
  $('confirm-title').textContent = title; $('confirm-message').textContent = message;
  $('confirm-dialog').returnValue = '';
  $('confirm-dialog').showModal();
  return new Promise(resolve => $('confirm-dialog').addEventListener('close', () => resolve($('confirm-dialog').returnValue === 'confirm'), {once:true}));
}
function timeLabel(value) {
  if (!value) return '—';
  return new Date(value).toLocaleString(undefined, {month:'short',day:'numeric',hour:'2-digit',minute:'2-digit'});
}
function tag(text, kind = '') { return el('span', 'tag ' + kind, text); }

function renderEvents(items, root) {
  root.replaceChildren();
  if (!items.length) { root.append(el('p', 'helper', 'No activity yet. Your first task starts the story.')); return; }
  for (const item of items) {
    const row = el('div', 'event-row ' + item.level);
    row.append(el('span', 'event-icon', item.level === 'error' ? '!' : item.level === 'warning' ? '◇' : '✓'));
    const copy = el('div', 'event-copy'); copy.append(el('p', '', item.message)); row.append(copy, el('time', '', timeLabel(item.at))); root.append(row);
  }
}
function renderRules() {
  const root = $('rules-list'); root.replaceChildren(); $('rule-count').textContent = state.rules.length + ' RULES';
  if (!state.rules.length) root.append(el('p', 'helper', 'No rules yet. Add a pattern or import your keyword list.'));
  const names = { contains:'Contains text', phrase:'Whole phrase', regex:'Regular expression', allow_author:'Allowed author channel ID' };
  for (const rule of state.rules) {
    const row = el('div', 'rule-row'), copy = el('div', 'rule-copy');
    copy.append(el('strong', '', rule.pattern), el('small', '', names[rule.kind]));
    const remove = el('button', 'delete-rule', '×'); remove.type = 'button'; remove.setAttribute('aria-label', 'Remove rule ' + rule.pattern); remove.disabled = state.busy;
    remove.addEventListener('click', () => attempt(async () => {
      await api('rules/' + encodeURIComponent(rule.id), 'DELETE'); rulesSignature = ''; commentsSignature = ''; await refresh(); toast('Rule removed. Saved comments have been reclassified.');
    }));
    row.append(el('span', 'rule-symbol', rule.kind === 'allow_author' ? '✓' : '◇'), copy, remove); root.append(row);
  }
}
function renderTask() {
  const job = state.jobs.find(j => j.id === state.active_job) || state.jobs[0];
  $('task-dot').classList.toggle('working', state.busy);
  $('cancel-task').hidden = !state.busy;
  $('task-state').textContent = state.busy ? 'Working in the background.' : job ? 'Last task: ' + job.state : 'Ready when you are.';
  const root = $('task-body'); root.replaceChildren();
  if (!job) { root.append(el('div','idle-graphic','✓'), el('h3','','Ready for a fresh start.'), el('p','','Connect your channel, add your rules, and start a scan.')); return; }
  const p = job.progress;
  root.append(el('div','task-count', String(p.processed ?? ((p.threads || 0) + (p.replies || 0)))));
  root.append(el('h3','', job.kind === 'login' ? 'Complete sign-in in your browser' : p.processed !== undefined ? 'comments processed' : 'comments scanned'));
  root.append(el('p','task-detail', job.error || (p.partial ? 'Partial scan saved. Use Resume to continue.' : state.busy ? 'You can keep browsing while this task runs.' : job.state === 'cancelled' ? 'Remaining work was cancelled.' : 'Your progress and results are saved locally.')));
}
function renderJobs() {
  const root = $('jobs-body'); root.replaceChildren();
  if (!state.jobs.length) { const tr=el('tr'), td=el('td','','No tasks yet.'); td.colSpan=4; tr.append(td); root.append(tr); }
  for (const job of state.jobs) {
    const tr = el('tr'), status = el('td');
    status.append(tag(job.state, job.state === 'completed' ? 'green' : job.state === 'failed' ? '' : 'gray'));
    const p = job.progress;
    const detail = job.error || (p.processed !== undefined ? `${p.processed} / ${p.selected} processed` : p.threads !== undefined ? `${p.threads} threads · ${p.replies} replies${p.partial ? ' · partial' : ''}` : '');
    tr.append(el('td','',job.kind),el('td','',timeLabel(job.created)),status,el('td','',detail)); root.append(tr);
  }
}
async function refresh() {
  if (polling) return;
  polling = true;
  try {
    state = await api('state');
    $('demo-banner').hidden = !state.demo; $('mode-badge').textContent = state.demo ? 'OFFLINE DEMO' : 'LOCAL APP';
    $('account-pill').textContent = state.connected ? state.account.title : 'Not connected';
    $('version').textContent = 'Version ' + state.version;
    $('metric-total').textContent = state.stats.total.toLocaleString(); $('metric-flagged').textContent = state.stats.flagged.toLocaleString(); $('metric-handled').textContent = state.stats.handled.toLocaleString(); $('nav-flagged').textContent = state.stats.flagged;
    $('scan-start').disabled = state.busy || !state.connected;
    $('connect').disabled = state.demo || state.busy || !state.configured;
    $('disconnect').disabled = state.demo || state.busy || !state.connected;
    $('oauth-file').disabled = state.demo || state.busy;
    $('credentials-state').textContent = state.demo ? 'Credentials are disabled in the isolated demo.' : state.configured ? 'Desktop app credentials imported' : 'No credentials imported';
    $('connection-detail').textContent = state.connected ? 'Connected to ' + state.account.title : state.busy ? 'Waiting for Google authorization…' : 'Not connected yet';
    $('storage-detail').textContent = 'Credential storage: ' + state.credential_storage + '. Local app sessions are separate from Google authorization.';
    const schedule = state.schedule;
    $('schedule-state').textContent = schedule.enabled ? 'Enabled · next run ' + new Date(schedule.next_run * 1000).toLocaleTimeString() : 'Currently paused';
    if (firstState) {
      $('auto-target').value = schedule.target || ''; $('auto-interval').value = schedule.interval_minutes || 15;
      $('auto-limit').value = schedule.max_threads || 500; $('auto-action').value = schedule.action || 'hold'; $('auto-enabled').checked = !!schedule.enabled;
    }
    renderTask();
    const rs = JSON.stringify(state.rules) + state.busy;
    if (rs !== rulesSignature) { rulesSignature = rs; renderRules(); }
    const js = JSON.stringify(state.jobs);
    if (js !== jobsSignature) { jobsSignature = js; renderJobs(); if (page === 'comments') await loadComments(); if (page === 'history') await loadActions(); }
    const es = JSON.stringify(state.events);
    if (es !== eventsSignature) { eventsSignature = es; renderEvents(state.events.slice(0,4), $('recent-events')); renderEvents(state.events, $('all-events')); }
    const finished = state.jobs.find(j => ['completed','failed','cancelled'].includes(j.state));
    if (!firstState && finished && finished.id !== lastFinished) {
      toast(finished.state === 'failed' ? finished.error : `${finished.kind.charAt(0).toUpperCase() + finished.kind.slice(1)} ${finished.state}.`, finished.state === 'failed');
      if (page === 'comments') await loadComments();
    }
    if (finished) lastFinished = finished.id;
    updateSelection(); firstState = false;
  } catch (error) { if (firstState) { $('session-error').hidden = false; $('session-error').textContent = error.message; } }
  finally { polling = false; }
}
function updateSelection() {
  $('selected-count').textContent = selected.size + ' selected';
  $('select-all').checked = visibleComments.length > 0 && visibleComments.every(c => selected.has(c.id));
  $('select-all').indeterminate = selected.size > 0 && ! $('select-all').checked;
  $('process').disabled = !state?.connected || state?.busy || !selected.size;
}
async function loadComments() {
  const result = await api('comments?' + new URLSearchParams({view,search:$('search').value,offset,limit:50}));
  const signature = JSON.stringify(result);
  if (signature === commentsSignature) { updateSelection(); return; }
  commentsSignature = signature; visibleComments = result.items;
  selected = new Set([...selected].filter(id => result.items.some(c => c.id === id)));
  const root = $('comments-body'); root.replaceChildren();
  for (const comment of result.items) {
    const tr = el('tr'), checkCell = el('td','check-cell'), checkbox = el('input'); checkbox.type='checkbox'; checkbox.checked = selected.has(comment.id); checkbox.setAttribute('aria-label','Select comment by ' + comment.author);
    checkbox.addEventListener('change', () => { checkbox.checked ? selected.add(comment.id) : selected.delete(comment.id); updateSelection(); }); checkCell.append(checkbox);
    const content = el('td'), author = el('div','author-line'), authorCopy = el('div');
    authorCopy.append(el('div','author-name',comment.author),el('div','comment-date',timeLabel(comment.published) + (comment.parent_id ? ' · Reply' : '')));
    author.append(el('span','avatar',comment.author.slice(0,2).toUpperCase()),authorCopy);
    content.append(author,el('div','comment-text',comment.text));
    if (!state?.demo && /^[\w-]{11}$/.test(comment.video_id)) {
      const link = el('a','comment-link','View on YouTube ↗'); link.href='https://www.youtube.com/watch?' + new URLSearchParams({v:comment.video_id,lc:comment.id}); link.target='_blank'; link.rel='noreferrer'; content.append(link);
    }
    const matches = el('td');
    if (comment.reasons.length) comment.reasons.forEach(reason => matches.append(tag(reason)));
    else matches.append(tag('No match','gray'));
    const status = el('td'); status.append(tag(comment.last_action || comment.moderation,comment.last_action ? 'green' : 'gray'));
    tr.append(checkCell,content,matches,status); root.append(tr);
  }
  $('comments-empty').hidden = result.total !== 0;
  $('page-count').textContent = result.total ? `${offset + 1}–${offset + result.items.length} of ${result.total} comments` : '0 comments';
  $('previous-page').disabled = offset === 0; $('next-page').disabled = offset + 50 >= result.total;
  updateSelection();
}
async function loadActions() {
  const {items} = await api('actions'); const root=$('actions-list'); root.replaceChildren();
  if (!items.length) root.append(el('p','helper','No moderation actions yet.'));
  for (const action of items.slice(0,100)) {
    const row=el('div','event-row ' + (action.state === 'unknown' ? 'warning' : '')), copy=el('div','event-copy');
    copy.append(el('p','',`${action.action} · ${action.comment_id} · ${action.state}`),el('small','',action.detail));
    if (action.state === 'unknown') {
      const reconcile=el('button','text-button','Reconcile after checking YouTube Studio');
      reconcile.addEventListener('click', () => attempt(async () => {
        const applied=await confirmAction('Did YouTube apply this action?', 'Check the comment in YouTube Studio first. Confirm only if the action was applied. Choosing Go back leaves it unresolved.');
        if (applied) { await api('actions/'+action.id+'/resolve','POST',{state:'confirmed'}); await loadActions(); await refresh(); }
      }));
      const notApplied=el('button','text-button','Verified not applied');
      notApplied.addEventListener('click', () => attempt(async () => {
        if (await confirmAction('Allow a new attempt?', 'Confirm that you checked YouTube Studio and the previous action was not applied.')) { await api('actions/'+action.id+'/resolve','POST',{state:'failed'}); await loadActions(); }
      }));
      copy.append(reconcile,notApplied);
    }
    row.append(el('span','event-icon', action.state === 'confirmed' ? '✓' : '◇'), copy, el('time','',timeLabel(action.at))); root.append(row);
  }
}

$('scan-form').addEventListener('submit', event => { event.preventDefault(); attempt(async () => {
  await api('scan','POST',{target:$('scan-target').value.trim(),max_threads:Number($('scan-limit').value),status:$('scan-status').value,include_replies:$('scan-replies').checked,resume:$('scan-resume').checked}); await refresh(); toast('Scan started. You can keep using the workspace.');
}); });
$('cancel-task').addEventListener('click', () => attempt(async () => { await api('cancel','POST'); toast('Cancellation requested. An in-flight request may still finish.'); }));
$('comment-tabs').addEventListener('click', event => { const target=event.target.closest('[data-view]'); if (!target) return; view=target.dataset.view; offset=0; selected.clear(); document.querySelectorAll('[data-view]').forEach(b=>b.classList.toggle('active',b===target)); attempt(loadComments); });
let searchTimer;
$('search').addEventListener('input', () => { clearTimeout(searchTimer); searchTimer=setTimeout(()=>{offset=0;selected.clear();attempt(loadComments);},250); });
$('select-all').addEventListener('change', () => { selected=$('select-all').checked ? new Set(visibleComments.map(c=>c.id)) : new Set(); document.querySelectorAll('#comments-body input[type=checkbox]').forEach(c=>{c.checked=$('select-all').checked;}); updateSelection(); });
$('previous-page').addEventListener('click', () => {offset=Math.max(0,offset-50);selected.clear();attempt(loadComments);});
$('next-page').addEventListener('click', () => {offset+=50;selected.clear();attempt(loadComments);});
$('process').addEventListener('click', () => attempt(async () => {
  const action=$('moderation-action').value;
  let message=`${selected.size} selected comments will be processed: ${actionNames[action]}.`;
  if (state.demo) message+='\nThis is an offline simulation. No YouTube comments will change.';
  else if (action==='reject'||action==='ban') message+='\nRejected comments cannot be republished through this app. Blocking also affects additional comments from the author.';
  if (!await confirmAction(state.demo?'Simulate moderation?':'Process selected comments?',message)) return;
  await api('moderate','POST',{ids:[...selected],action}); selected.clear(); commentsSignature=''; await loadComments(); await refresh(); updateSelection();
}));
$('rule-form').addEventListener('submit', event => {event.preventDefault();attempt(async()=>{
  await api('rules','POST',{kind:$('rule-kind').value,pattern:$('rule-pattern').value.trim()}); $('rule-pattern').value=''; await refresh(); toast('Rule added. Saved comments have been reclassified.');
});});
$('import-rules').addEventListener('change', event => attempt(async()=>{const file=event.target.files[0];if(!file)return;if(file.size>50000)throw new Error('Choose a keyword file smaller than 50 KB.');const result=await api('rules/import','POST',{text:await file.text()});await refresh();toast(`${result.imported} keyword entries imported.`);event.target.value='';}));
$('schedule-form').addEventListener('submit',event=>{event.preventDefault();attempt(async()=>{
  const payload={enabled:$('auto-enabled').checked,interval_minutes:Number($('auto-interval').value),max_threads:Number($('auto-limit').value),action:$('auto-action').value,target:$('auto-target').value.trim(),include_replies:true,resume:true,status:'published'};
  if(payload.enabled && !await confirmAction('Enable automatic cleaning?',`Every ${payload.interval_minutes} minutes, matching comments ${payload.target?'on the selected video':'on your connected channel'} will be processed: ${actionNames[payload.action]}.${state.demo?'\nDemo mode only.':'\nThis continues while the application is running, even if you close this browser tab.'}`))return;
  await api('schedule','POST',payload);await refresh();toast(payload.enabled?'Automatic cleaning enabled.':'Automatic cleaning paused.');
});});
$('oauth-file').addEventListener('change',event=>attempt(async()=>{const file=event.target.files[0];if(!file)return;if(file.size>100000)throw new Error('Choose the Google OAuth Desktop app JSON file.');let config;try{config=JSON.parse(await file.text());}catch{throw new Error('The selected file is not valid JSON.');}await api('oauth/config','POST',config);await refresh();toast('Credentials imported. You can connect your channel now.');event.target.value='';}));
$('connect').addEventListener('click',()=>attempt(async()=>{await api('login','POST');await refresh();toast('Complete authorization in the Google browser tab.');}));
$('disconnect').addEventListener('click',()=>attempt(async()=>{await api('logout','POST');await refresh();toast('Disconnected. Automatic cleaning has been paused.');}));
$('export').addEventListener('click',()=>attempt(async()=>{const response=await fetch('/api/export',{headers:{Authorization:'Bearer '+session}});if(!response.ok)throw new Error('Export failed.');const url=URL.createObjectURL(await response.blob()),link=document.createElement('a');link.href=url;link.download='comments.csv';link.click();setTimeout(()=>URL.revokeObjectURL(url),1000);}));
$('quit').addEventListener('click',()=>attempt(async()=>{if(!await confirmAction('Quit YouTube Spam Cleaner?','This stops the local service and automatic cleaning. You can start it again from the application.'))return;await api('shutdown','POST');$('session-error').hidden=false;$('session-error').textContent='Application stopped. You may close this tab.';clearInterval(pollTimer);}));
refresh();
const pollTimer=setInterval(refresh,2000);
