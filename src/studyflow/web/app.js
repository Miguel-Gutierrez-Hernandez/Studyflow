const API = window.location.origin.includes(':8000') ? '' : 'http://localhost:8000';

let pendingFiles = [];
let editingProject = null; // null = create mode, string = update mode
let jobPollTimer = null;

// -- Utilities -----------------------------------------------------------

function fmtDate(iso) {
  if (!iso) return '—';
  const d = new Date(iso);
  return d.toLocaleDateString('es', { day: '2-digit', month: 'short', year: 'numeric' });
}

async function api(path, opts = {}) {
  const res = await fetch(API + path, opts);
  if (!res.ok) {
    let detail = res.statusText;
    try { const j = await res.json(); detail = j.detail || detail; } catch {}
    throw new Error(detail);
  }
  const ct = res.headers.get('content-type') || '';
  return ct.includes('application/json') ? res.json() : res;
}

// -- Project shelf ---------------------------------------------------------

async function loadProjects() {
  const shelf = document.getElementById('shelf');
  const empty = document.getElementById('emptyState');
  try {
    const projects = await api('/projects');
    document.getElementById('projectCount').textContent =
      projects.length ? `${projects.length} proyecto${projects.length === 1 ? '' : 's'}` : '';

    if (!projects.length) {
      shelf.innerHTML = '';
      empty.style.display = 'block';
      return;
    }
    empty.style.display = 'none';
    shelf.innerHTML = projects.map(renderCard).join('');
    shelf.querySelectorAll('[data-action]').forEach(btn => {
      btn.addEventListener('click', () => handleCardAction(btn.dataset.action, btn.dataset.name));
    });
  } catch (e) {
    shelf.innerHTML = `<div class="empty"><div class="glyph">⚠</div><p><strong>No se pudo conectar con la API.</strong></p><p>¿Está corriendo <code>uvicorn api:app</code>?</p></div>`;
  }
}

function renderCard(p) {
  const status = p.has_html ? 'ready' : 'pending';
  return `
    <div class="card" data-status="${status}">
      <div class="title">${escapeHtml(p.name)}</div>
      <div class="meta">${p.n_files} archivo${p.n_files === 1 ? '' : 's'} · ${fmtDate(p.created)}</div>
      <div class="badges">
        <span class="badge ${p.has_html ? 'on' : 'off'}">${p.has_html ? '● HTML' : '○ sin HTML'}</span>
        <span class="badge ${p.has_pdf ? 'on' : 'off'}">${p.has_pdf ? '● PDF' : '○ sin PDF'}</span>
      </div>
      <div class="actions">
        ${p.has_html ? `<button class="btn" data-action="view" data-name="${escapeAttr(p.name)}">Ver material</button>` : ''}
        ${p.has_html ? `<button class="btn" data-action="pdf" data-name="${escapeAttr(p.name)}">PDF</button>` : ''}
        <button class="btn" data-action="update" data-name="${escapeAttr(p.name)}">+ Archivos</button>
        <button class="btn danger" data-action="delete" data-name="${escapeAttr(p.name)}">Eliminar</button>
      </div>
    </div>`;
}

function escapeHtml(s) { return s.replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c])); }
function escapeAttr(s) { return escapeHtml(s); }

async function handleCardAction(action, name) {
  if (action === 'view') window.open(`${API}/projects/${encodeURIComponent(name)}/html`, '_blank');
  if (action === 'pdf') window.open(`${API}/projects/${encodeURIComponent(name)}/pdf`, '_blank');
  if (action === 'update') openCreatePanel(name);
  if (action === 'delete') {
    if (!confirm(`¿Eliminar el proyecto "${name}" y todos sus archivos? Esta acción no se puede deshacer.`)) return;
    try {
      await api(`/projects/${encodeURIComponent(name)}`, { method: 'DELETE' });
      loadProjects();
    } catch (e) {
      alert('No se pudo eliminar: ' + e.message);
    }
  }
}

// -- Create / update panel ------------------------------------------------

function openCreatePanel(updateName = null) {
  editingProject = updateName;
  pendingFiles = [];
  renderFileList();
  document.getElementById('formError').classList.remove('show');
  document.getElementById('qpt').value = 8;
  document.getElementById('modelInput').value = '';
  document.getElementById('exportPdf').checked = false;

  const nameField = document.getElementById('nameField');
  const pname = document.getElementById('pname');
  const formTitle = document.getElementById('formTitle');
  const submitBtn = document.getElementById('submitCreate');

  if (updateName) {
    formTitle.textContent = `Añadir archivos a "${updateName}"`;
    nameField.style.display = 'none';
    submitBtn.textContent = 'Añadir y regenerar';
  } else {
    formTitle.textContent = 'Nuevo proyecto';
    nameField.style.display = 'block';
    pname.value = '';
    submitBtn.textContent = 'Generar material';
  }
  document.getElementById('createOverlay').classList.add('open');
}

function closeCreatePanel() {
  document.getElementById('createOverlay').classList.remove('open');
}

function renderFileList() {
  const el = document.getElementById('fileList');
  el.innerHTML = pendingFiles.map((f, i) => `
    <div class="f"><span>${escapeHtml(f.name)}</span><button data-i="${i}">✕ quitar</button></div>
  `).join('');
  el.querySelectorAll('button').forEach(b => b.addEventListener('click', () => {
    pendingFiles.splice(Number(b.dataset.i), 1);
    renderFileList();
  }));
}

function addFiles(fileArray) {
  for (const f of fileArray) pendingFiles.push(f);
  renderFileList();
}

async function submitProject() {
  const errorEl = document.getElementById('formError');
  errorEl.classList.remove('show');

  const isUpdate = !!editingProject;
  const name = isUpdate ? editingProject : document.getElementById('pname').value.trim();

  if (!isUpdate && !name) {
    errorEl.textContent = 'Ponle un nombre al proyecto.';
    errorEl.classList.add('show');
    return;
  }
  if (!isUpdate && pendingFiles.length === 0) {
    errorEl.textContent = 'Añade al menos un archivo.';
    errorEl.classList.add('show');
    return;
  }

  const qpt = document.getElementById('qpt').value || 8;
  const model = document.getElementById('modelInput').value.trim();
  const exportPdf = document.getElementById('exportPdf').checked;

  const params = new URLSearchParams();
  if (!isUpdate) params.set('name', name);
  params.set('questions_per_topic', qpt);
  params.set('export_pdf', exportPdf);
  if (model) params.set('model', model);

  const fd = new FormData();
  for (const f of pendingFiles) fd.append('files', f);

  const submitBtn = document.getElementById('submitCreate');
  submitBtn.disabled = true;
  submitBtn.textContent = 'Enviando…';

  try {
    const path = isUpdate
      ? `/projects/${encodeURIComponent(name)}?${params.toString()}`
      : `/projects?${params.toString()}`;
    const job = await api(path, { method: isUpdate ? 'PATCH' : 'POST', body: fd });
    closeCreatePanel();
    openJobPanel(job);
  } catch (e) {
    errorEl.textContent = e.message || 'Algo falló al crear el proyecto.';
    errorEl.classList.add('show');
  } finally {
    submitBtn.disabled = false;
    submitBtn.textContent = isUpdate ? 'Añadir y regenerar' : 'Generar material';
  }
}

// -- Job progress panel (signature element) --------------------------------

const STEP_ORDER = ['setup', 'extract', 'topics', 'material', 'build'];

function openJobPanel(job) {
  document.getElementById('jobTitle').textContent = `Procesando "${job.project_name}"`;
  document.getElementById('jobDone').style.display = 'none';
  setStepperState('setup');
  document.getElementById('jobStatusLine').textContent = `job ${job.job_id.slice(0, 8)} · ${job.status}`;
  document.getElementById('jobOverlay').classList.add('open');
  pollJob(job.job_id);
}

function setStepperState(activeKey, errored = false) {
  const idx = STEP_ORDER.indexOf(activeKey);
  document.querySelectorAll('#stepper li').forEach(li => {
    const liIdx = STEP_ORDER.indexOf(li.dataset.key);
    li.classList.remove('done', 'active', 'error');
    if (liIdx < idx) li.classList.add('done');
    else if (liIdx === idx) li.classList.add(errored ? 'error' : 'active');
  });
}

function pollJob(jobId) {
  clearInterval(jobPollTimer);
  // Simulated progression through steps while status === "running", since the
  // API reports coarse status (queued/running/done/error), not per-step detail.
  let simulated = 0;
  jobPollTimer = setInterval(async () => {
    try {
      const job = await api(`/jobs/${jobId}`);
      document.getElementById('jobStatusLine').textContent = `job ${jobId.slice(0, 8)} · ${job.status}`;

      if (job.status === 'queued') {
        setStepperState('setup');
      } else if (job.status === 'running') {
        simulated = Math.min(simulated + 1, STEP_ORDER.length - 1);
        setStepperState(STEP_ORDER[simulated]);
      } else if (job.status === 'done') {
        setStepperState('build');
        document.querySelectorAll('#stepper li').forEach(li => li.classList.add('done'));
        document.getElementById('jobTitle').textContent = `"${job.project_name}" listo`;
        const doneBtn = document.getElementById('jobDone');
        doneBtn.style.display = 'inline-block';
        doneBtn.onclick = () => window.open(`${API}/projects/${encodeURIComponent(job.project_name)}/html`, '_blank');
        clearInterval(jobPollTimer);
        loadProjects();
      } else if (job.status === 'error') {
        setStepperState(STEP_ORDER[simulated], true);
        document.getElementById('jobTitle').textContent = `Error en "${job.project_name}"`;
        document.getElementById('jobStatusLine').textContent = job.error || 'Error desconocido';
        clearInterval(jobPollTimer);
        loadProjects();
      }
    } catch (e) {
      clearInterval(jobPollTimer);
    }
  }, 1800);
}

// -- Wire up events ---------------------------------------------------------

document.getElementById('openCreate').addEventListener('click', () => openCreatePanel());
document.getElementById('emptyCreate').addEventListener('click', () => openCreatePanel());
document.getElementById('closeCreate').addEventListener('click', closeCreatePanel);
document.getElementById('cancelCreate').addEventListener('click', closeCreatePanel);
document.getElementById('submitCreate').addEventListener('click', submitProject);
document.getElementById('closeJob').addEventListener('click', () => {
  document.getElementById('jobOverlay').classList.remove('open');
  clearInterval(jobPollTimer);
});

const dropzone = document.getElementById('dropzone');
const fileInput = document.getElementById('fileInput');
dropzone.addEventListener('click', () => fileInput.click());
fileInput.addEventListener('change', () => addFiles([...fileInput.files]));
dropzone.addEventListener('dragover', e => { e.preventDefault(); dropzone.classList.add('drag'); });
dropzone.addEventListener('dragleave', () => dropzone.classList.remove('drag'));
dropzone.addEventListener('drop', e => {
  e.preventDefault();
  dropzone.classList.remove('drag');
  addFiles([...e.dataTransfer.files]);
});

document.querySelectorAll('.overlay').forEach(ov => {
  ov.addEventListener('click', e => { if (e.target === ov && ov.id !== 'jobOverlay') ov.classList.remove('open'); });
});

loadProjects();
setInterval(loadProjects, 15000);