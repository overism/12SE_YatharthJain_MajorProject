let timerState = {
  subjects: [],
  presets: []
};

const colorSchemes = window.SUBJECT_COLOURS || window.SUBJECT_COLOR_PALETTE || {
  orange: '#f5761c',
  blue: '#2563eb',
  green: '#15803d',
  red: '#dc2626',
  purple: '#7c3aed',
  yellow: '#f5c21c',
  brown: '#92400e',
  teal: '#0891b2',
  pink: '#be185d',
};

let editingPresetID = null;
let pendingStartAfterSubject = false;
let statusTimeout = null;

document.addEventListener('DOMContentLoaded', () => {
  setupEventListeners();
  loadSubjects();
  loadPresets();
  DustyStudyTimer.subscribe(renderTimerPage);

  setTimeout(() => {
    document.getElementById('timer-loading')?.classList.add('is-hidden');
  }, 700);
});

function setupEventListeners() {
  document.getElementById('playBtn')?.addEventListener('click', handleStart);
  document.getElementById('pauseBtn')?.addEventListener('click', () => DustyStudyTimer.pauseTimer());
  document.getElementById('resetBtn')?.addEventListener('click', () => DustyStudyTimer.resetTimer(true));
  document.getElementById('subjectBtn')?.addEventListener('click', () => openSubjectModal(false));
  document.getElementById('popoutBtn')?.addEventListener('click', togglePopout);
  document.getElementById('finishSessionBtn')?.addEventListener('click', finishSessionNow);

  document.getElementById('addPresetBtn')?.addEventListener('click', () => openPresetModal());
  document.getElementById('closeModalBtn')?.addEventListener('click', closePresetModal);
  document.getElementById('cancelPresetBtn')?.addEventListener('click', closePresetModal);
  document.getElementById('savePresetBtn')?.addEventListener('click', savePreset);
  document.getElementById('deletePresetBtn')?.addEventListener('click', deletePreset);

  document.getElementById('closeSubjectModalBtn')?.addEventListener('click', closeSubjectModal);
  document.getElementById('saveSessionBtn')?.addEventListener('click', saveCompletedSessionNotes);
  document.getElementById('skipSaveBtn')?.addEventListener('click', closeSessionModal);

  document.querySelectorAll('.quick-preset-btn').forEach(btn => {
    btn.addEventListener('click', event => {
      const minutes = parseInt(event.currentTarget.dataset.minutes, 10);
      document.getElementById('presetDuration').value = minutes;
    });
  });
}

async function loadSubjects() {
  try {
    const response = await fetch('/api/subjects');
    const data = await response.json();
    if (!response.ok) {
      throw new Error(data.error || 'Could not load subjects');
    }
    timerState.subjects = data.subjects || [];
    renderSubjectGrid();
  } catch (error) {
    showNotification(error.message, 'error');
  }
}

async function loadPresets() {
  try {
    const response = await fetch('/api/timer/presets');
    const data = await response.json();
    if (!response.ok) {
      throw new Error(data.error || 'Could not load presets');
    }
    timerState.presets = data.presets || [];
    renderPresets();
  } catch (error) {
    showNotification(error.message, 'error');
  }
}

function renderSubjectGrid() {
  const subjectGrid = document.getElementById('subjectGrid');
  if (!subjectGrid) {
    return;
  }

  subjectGrid.innerHTML = '';
  timerState.subjects.forEach(subject => {
    const button = document.createElement('button');
    button.type = 'button';
    button.className = 'subject-card';
    const color = window.getSubjectColour ? window.getSubjectColour(subject.colourScheme || 'orange') : (colorSchemes[subject.colourScheme] || colorSchemes.orange);
    button.style.setProperty('--subject-color', color);
    button.innerHTML = `
      <span class="subject-color-indicator"></span>
      <span class="subject-card-name">${escapeHtml(subject.subjectName)}</span>
    `;
    button.addEventListener('click', () => chooseSubject(subject));
    subjectGrid.appendChild(button);
  });
}

function renderPresets() {
  const presetsContainer = document.getElementById('presetsContainer');
  if (!presetsContainer) {
    return;
  }

  const activeState = DustyStudyTimer.getState();
  presetsContainer.innerHTML = '';
  timerState.presets.forEach(preset => {
    const card = document.createElement('article');
    card.className = 'preset-btn';
    if (activeState.currentPresetID === preset.presetID) {
      card.classList.add('active');
    }
    card.tabIndex = 0;
    card.setAttribute('role', 'button');
    card.innerHTML = `
      <span class="preset-btn-name">${escapeHtml(preset.presetName)}</span>
      <span class="preset-btn-time">${Math.floor(preset.durationSeconds / 60)} min</span>
      <span class="preset-btn-description">${escapeHtml(preset.description || '')}</span>
      <span class="preset-card-actions">
        <button class="preset-edit-btn" type="button">Edit</button>
        <button class="preset-delete-btn" type="button">Delete</button>
      </span>
    `;
    card.addEventListener('click', event => {
      if (event.target.closest('button')) {
        return;
      }
      selectPreset(preset);
    });
    card.addEventListener('keydown', event => {
      if (event.key === 'Enter' || event.key === ' ') {
        event.preventDefault();
        selectPreset(preset);
      }
    });
    card.querySelector('.preset-edit-btn').addEventListener('click', () => openPresetModal(preset.presetID));
    card.querySelector('.preset-delete-btn').addEventListener('click', () => deletePresetConfirm(preset.presetID));
    presetsContainer.appendChild(card);
  });
}

function selectPreset(preset) {
  DustyStudyTimer.setPreset(preset);
  renderPresets();
}

async function handleStart() {
  const state = DustyStudyTimer.getState();
  if (!state.currentSubject) {
    openSubjectModal(true);
    return;
  }

  try {
    await DustyStudyTimer.startTimer();
  } catch (error) {
    showNotification(error.message, 'error');
  }
}

async function chooseSubject(subject) {
  DustyStudyTimer.setSubject(subject);
  closeSubjectModal();

  if (pendingStartAfterSubject) {
    pendingStartAfterSubject = false;
    try {
      await DustyStudyTimer.startTimer(subject);
    } catch (error) {
      showNotification(error.message, 'error');
    }
  }
}

function openSubjectModal(startAfterSelection) {
  pendingStartAfterSubject = Boolean(startAfterSelection);
  document.getElementById('subjectModal')?.classList.add('active');
}

function closeSubjectModal() {
  pendingStartAfterSubject = false;
  document.getElementById('subjectModal')?.classList.remove('active');
}

function togglePopout() {
  const state = DustyStudyTimer.getState();
  DustyStudyTimer.setPopout(!state.popout);
}

async function finishSessionNow() {
  const state = DustyStudyTimer.getState();
  if (!state.sessionID || Number(state.elapsedSeconds || 0) <= 0) {
    showNotification('Start a session before finishing it', 'error');
    return;
  }

  try {
    const completedState = await DustyStudyTimer.completeTimer('');
    showSessionCompleteModal(completedState);
  } catch (error) {
    showNotification(error.message, 'error');
  }
}

function openPresetModal(presetID = null) {
  editingPresetID = presetID;
  const preset = timerState.presets.find(item => item.presetID === presetID);
  document.getElementById('modalTitle').textContent = preset ? 'Edit Preset' : 'Create New Preset';
  document.getElementById('presetName').value = preset?.presetName || '';
  document.getElementById('presetDuration').value = preset ? Math.floor(preset.durationSeconds / 60) : '25';
  document.getElementById('presetDescription').value = preset?.description || '';
  document.getElementById('savePresetBtn').textContent = preset ? 'Save Preset' : 'Create Preset';
  document.getElementById('deletePresetBtn').classList.toggle('hidden', !preset);
  document.getElementById('presetModal')?.classList.add('active');
}

function closePresetModal() {
  document.getElementById('presetModal')?.classList.remove('active');
  editingPresetID = null;
}

async function savePreset() {
  const name = document.getElementById('presetName').value.trim();
  const duration = parseInt(document.getElementById('presetDuration').value, 10);
  const description = document.getElementById('presetDescription').value.trim();
  const wasEditing = Boolean(editingPresetID);

  if (!name) {
    showNotification('Please enter a preset name', 'error');
    return;
  }
  if (!Number.isInteger(duration) || duration < 1 || duration > 120) {
    showNotification('Duration must be between 1 and 120 minutes', 'error');
    return;
  }

  try {
    const response = await fetch('/api/timer/presets', {
      method: wasEditing ? 'PUT' : 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        presetID: editingPresetID,
        presetName: name,
        durationSeconds: duration * 60,
        description
      })
    });
    const data = await response.json().catch(() => ({}));
    if (!response.ok) {
      throw new Error(data.error || 'Could not save preset');
    }

    closePresetModal();
    await loadPresets();
    showNotification(wasEditing ? 'Preset updated' : 'Preset created', 'success');
  } catch (error) {
    showNotification(error.message, 'error');
  }
}

function deletePresetConfirm(presetID) {
  if (confirm('Delete this preset?')) {
    deletePresetFromDB(presetID);
  }
}

async function deletePresetFromDB(presetID) {
  try {
    const response = await fetch('/api/timer/presets', {
      method: 'DELETE',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ presetID })
    });
    const data = await response.json().catch(() => ({}));
    if (!response.ok) {
      throw new Error(data.error || 'Could not delete preset');
    }

    await loadPresets();
    showNotification('Preset deleted', 'success');
  } catch (error) {
    showNotification(error.message, 'error');
  }
}

async function deletePreset() {
  if (!editingPresetID || !confirm('Delete this preset?')) {
    return;
  }
  await deletePresetFromDB(editingPresetID);
  closePresetModal();
}

function renderTimerPage(state) {
  document.getElementById('timerDisplay').textContent = DustyStudyTimer.formatTime(state.remainingSeconds);
  document.getElementById('presetLabel').textContent = state.currentPresetName || 'Custom Timer';
  document.getElementById('durationValue').textContent = `${Math.floor(Number(state.totalSeconds || 0) / 60)} min`;
  document.getElementById('statusValue').textContent = state.isRunning ? 'Running' : state.isPaused ? 'Paused' : 'Ready';
  document.getElementById('subjectBtn').textContent = state.currentSubjectName || 'Choose subject';
  document.getElementById('popoutBtn').textContent = state.popout ? 'Hide Widget' : 'Pop Out Timer';
  const finishSessionBtn = document.getElementById('finishSessionBtn');
  finishSessionBtn.disabled = !state.sessionID || Number(state.elapsedSeconds || 0) <= 0 || state.remainingSeconds <= 0;

  document.getElementById('playBtn').classList.toggle('hidden', state.isRunning);
  document.getElementById('pauseBtn').classList.toggle('hidden', !state.isRunning);

  renderPresets();

  if (state.justCompleted) {
    showSessionCompleteModal(state);
  }
}

function showSessionCompleteModal(state) {
  document.getElementById('sessionTimeValue').textContent = DustyStudyTimer.formatTime(state.elapsedSeconds);
  document.getElementById('sessionSubjectValue').textContent = state.currentSubjectName || '-';
  document.getElementById('sessionCompleteModal')?.classList.add('active');
}

function closeSessionModal() {
  document.getElementById('sessionCompleteModal')?.classList.remove('active');
  document.getElementById('sessionNotes').value = '';
  DustyStudyTimer.resetTimer(false);
}

async function saveCompletedSessionNotes() {
  const notes = document.getElementById('sessionNotes').value.trim();
  try {
    await DustyStudyTimer.autosave('completed', { notes, endTime: true });
    showNotification('Session saved', 'success');
    closeSessionModal();
  } catch (error) {
    showNotification(error.message, 'error');
  }
}

function showNotification(message, type = 'info') {
  const statusElement = document.getElementById('status');
  if (!statusElement) {
    return;
  }

  if (statusTimeout) {
    clearTimeout(statusTimeout);
  }

  statusElement.textContent = message;
  statusElement.className = `status show ${type}`;
  statusTimeout = setTimeout(() => {
    statusElement.classList.remove('show');
  }, type === 'error' ? 6000 : 3000);
}

function escapeHtml(value) {
  return String(value || '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#039;');
}
