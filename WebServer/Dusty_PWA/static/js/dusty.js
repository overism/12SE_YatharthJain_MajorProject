if ('serviceWorker' in navigator) {
  navigator.serviceWorker.register('/static/sw.js')
    .then(function(registration) {
      console.log('Service Worker registered with scope:', registration.scope);
    })
    .catch(function(error) {
      console.error('Service Worker registration failed:', error);
    });
}

function showPopup(title, message, onClose = null) {
    const popup = document.createElement("div");
    popup.className = "popup";

    popup.innerHTML = `
        <div class="popup-box">
            <h2>${title}</h2>
            <p>${message}</p>
            <button id="popup-close">OK</button>
        </div>
    `;

    document.body.appendChild(popup);

    document.getElementById("popup-close").onclick = () => {
        popup.remove();
        if (typeof onClose === "function") {
            onClose();
        }
    };
}

const loginForm = document.getElementById('loginForm');
if (loginForm) {
    loginForm.addEventListener('submit', function(event) {
        event.preventDefault();

        fetch('/login_validation', {
            method: 'POST',
            body: new FormData(this)
        })
        .then(response => response.json())
        .then(data => {
            if (data.success) {
                showPopup("Login Successful", data.message, () => {
                    window.location.href = "/home";
                });
            } else {
                showPopup("Login Failed", data.message);
            }
        })
        .catch(() => {
            showPopup("Error", "Unable to login. Please try again.");
        });
    });
}

const signupForm = document.getElementById('signupForm');
if (signupForm) {
    signupForm.addEventListener('submit', function(e) {
        e.preventDefault();

        if (!this.checkValidity()) {
            this.reportValidity();
            return;
        }

        const pw = document.getElementById('password').value;
        const cpw = document.getElementById('confirmPassword').value;

        if (pw !== cpw) {
            showPopup("Signup Error", "Passwords do not match.");
            return;
        }

        fetch("/add_user", {
            method: "POST",
            body: new FormData(this)
        })
        .then(res => res.json())
        .then(data => {
            showPopup(data.title, data.message, () => {
                if (data.success) {
                    openPrefsModal();
                }
            });
        })
        .catch(() => {
            showPopup("Server Error", "Something went wrong. Please try again later.");
        });
    });
}

document.querySelectorAll('.game-card').forEach(card => {
  card.addEventListener('click', () => {
    const banner = card.dataset.banner;
    const link = card.dataset.link;
    const overlay = document.getElementById('overlay');

    overlay.style.backgroundImage = `url(${banner})`;
    overlay.classList.add('active');

    setTimeout(() => {
      window.location.href = link;
    }, 600);
  });
});

const saveBioBtn = document.getElementById('saveBio');
if (saveBioBtn) {
  saveBioBtn.addEventListener('click', (e) => {
    e.preventDefault();
    saveBio();
  });
}

async function saveBio() {
  const bio = document.getElementById('bioEditor').value;
  const bioStatus = document.getElementById('bioStatus');
  bioStatus.textContent = 'Saving...';

  try {
    const response = await fetch('/save-bio', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ bio: bio })
    });

    if (response.ok) {
      bioStatus.textContent = 'Saved';
      setTimeout(() => bioStatus.textContent = '', 2000);
    } else {
      bioStatus.textContent = 'Error saving bio';
    }
  } catch (error) {
    bioStatus.textContent = 'Error saving bio';
  }
}

const resetBioBtn = document.getElementById('resetBio');
if (resetBioBtn) {
  resetBioBtn.addEventListener('click', (e) => {
    e.preventDefault();
    const bioEditor = document.getElementById('bioEditor');
    const bioStatus = document.getElementById('bioStatus');
    if (bioEditor) bioEditor.value = '{{ user.userBio }}';
    if (bioStatus) {
      bioStatus.textContent = 'Reset';
      setTimeout(() => bioStatus.textContent = '', 1400);
    }
  });
}

// Handle Avatar Upload
const avatarForm = document.getElementById('avatarForm');
if (avatarForm) {
  avatarForm.addEventListener('submit', (e) => {
    e.preventDefault();

    const formData = new FormData(e.target);
    fetch('/upload-avatar', {
      method: 'POST',
      body: formData
    })
    .then(response => response.json())
    .then(data => {
      if (data.status === 'success') {
        const avatar = document.getElementById('profileAvatar');
        if (avatar) avatar.src = data.filepath;
      }
    });
  });
}

const searchForm = document.getElementById('searchForm');
const searchSlot = document.querySelector('.search-slot');
const menuSearch = document.querySelector('.menu-search');

function moveSearch() {
  if (!searchForm || !searchSlot || !menuSearch) {
    return;
  }

  if (window.innerWidth <= 640) {
    if (!menuSearch.contains(searchForm)) {
      menuSearch.appendChild(searchForm);
    }
  } else {
    if (!searchSlot.contains(searchForm)) {
      searchSlot.appendChild(searchForm);
    }
  }
}

window.addEventListener('resize', moveSearch);
window.addEventListener('load', moveSearch);

(function initDustyStudyTimer() {
  const STORAGE_KEY = 'dusty.studyTimer.state';
  const AUTOSAVE_SECONDS = 60;
  const DEFAULT_STATE = {
    isRunning: false,
    isPaused: false,
    totalSeconds: 3600,
    remainingSeconds: 3600,
    elapsedSeconds: 0,
    currentSubject: null,
    currentSubjectName: null,
    currentPresetID: null,
    currentPresetName: 'Custom Timer',
    sessionID: null,
    popout: false,
    lastTickAt: null,
    lastAutosaveElapsed: 0,
    completedNotified: false
  };

  const listeners = new Set();

  function readState() {
    try {
      return Object.assign({}, DEFAULT_STATE, JSON.parse(localStorage.getItem(STORAGE_KEY) || '{}'));
    } catch (error) {
      return Object.assign({}, DEFAULT_STATE);
    }
  }

  function writeState(state, emit = true) {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(state));
    if (emit) {
      listeners.forEach(listener => listener(Object.assign({}, state)));
    }
  }

  function deriveState(emit = false) {
    const state = readState();
    if (!state.isRunning || !state.lastTickAt) {
      return state;
    }

    const now = Date.now();
    const delta = Math.max(0, Math.floor((now - state.lastTickAt) / 1000));
    if (delta < 1) {
      return state;
    }

    state.remainingSeconds = Math.max(0, Number(state.remainingSeconds || 0) - delta);
    state.elapsedSeconds = Number(state.elapsedSeconds || 0) + delta;
    state.lastTickAt = now;

    if (state.remainingSeconds <= 0) {
      state.isRunning = false;
      state.isPaused = false;
      state.remainingSeconds = 0;
    }

    writeState(state, emit);
    return state;
  }

  function formatTime(seconds) {
    const safeSeconds = Math.max(0, Number(seconds || 0));
    const minutes = Math.floor(safeSeconds / 60);
    const secs = safeSeconds % 60;
    return `${String(minutes).padStart(2, '0')}:${String(secs).padStart(2, '0')}`;
  }

  async function postJson(url, method, payload) {
    const response = await fetch(url, {
      method,
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload)
    });
    const data = await response.json().catch(() => ({}));
    if (!response.ok) {
      throw new Error(data.error || 'Timer save failed');
    }
    return data;
  }

  function sessionPayload(state, status, extras = {}) {
    return Object.assign({
      subjectID: state.currentSubject,
      presetID: state.currentPresetID,
      durationSeconds: Number(state.totalSeconds || 0),
      timeSpentSeconds: Number(state.elapsedSeconds || 0),
      status
    }, extras);
  }

  async function createSession(state) {
    const data = await postJson('/api/timer/sessions', 'POST', sessionPayload(state, 'in_progress'));
    state.sessionID = data.sessionID;
    writeState(state);
    return state;
  }

  async function autosave(status = null, extras = {}) {
    const state = deriveState();
    if (!state.sessionID) {
      return state;
    }

    const nextStatus = status || (state.isRunning ? 'in_progress' : state.isPaused ? 'paused' : 'completed');
    await postJson(`/api/timer/sessions/${state.sessionID}`, 'PATCH', sessionPayload(state, nextStatus, extras));
    state.lastAutosaveElapsed = Number(state.elapsedSeconds || 0);
    writeState(state);
    return state;
  }

  async function startTimer(subject = null) {
    const state = deriveState();
    if (subject) {
      state.currentSubject = subject.subjectID || subject.currentSubject;
      state.currentSubjectName = subject.subjectName || subject.currentSubjectName;
    }

    if (!state.currentSubject) {
      window.location.href = '/timer';
      return state;
    }

    state.isRunning = true;
    state.isPaused = false;
    state.lastTickAt = Date.now();
    state.completedNotified = false;
    if (!state.sessionID) {
      await createSession(state);
    }
    writeState(state);
    return state;
  }

  async function pauseTimer() {
    const state = deriveState();
    state.isRunning = false;
    state.isPaused = true;
    state.lastTickAt = null;
    writeState(state);
    await autosave('paused');
    return state;
  }

  async function resetTimer(markAbandoned = true) {
    const state = deriveState();
    const shouldSaveAbandoned = markAbandoned && state.sessionID && Number(state.elapsedSeconds || 0) > 0;
    state.isRunning = false;
    state.isPaused = false;
    state.remainingSeconds = Number(state.totalSeconds || DEFAULT_STATE.totalSeconds);
    state.elapsedSeconds = 0;
    state.lastTickAt = null;
    state.lastAutosaveElapsed = 0;
    state.completedNotified = false;

    if (shouldSaveAbandoned) {
      await autosave('abandoned', { endTime: true });
    }

    state.sessionID = null;
    writeState(state);
    return state;
  }

  async function completeTimer(notes = '') {
    const state = deriveState();
    state.isRunning = false;
    state.isPaused = false;
    state.remainingSeconds = 0;
    state.lastTickAt = null;
    writeState(state);
    await autosave('completed', { notes, endTime: true });
    state.completedNotified = true;
    writeState(state);
    return state;
  }

  function setPreset(preset) {
    const state = deriveState();
    state.currentPresetID = preset?.presetID || null;
    state.currentPresetName = preset?.presetName || 'Custom Timer';
    state.totalSeconds = Number(preset?.durationSeconds || DEFAULT_STATE.totalSeconds);
    state.remainingSeconds = state.totalSeconds;
    state.elapsedSeconds = 0;
    state.isRunning = false;
    state.isPaused = false;
    state.sessionID = null;
    state.lastTickAt = null;
    state.lastAutosaveElapsed = 0;
    state.completedNotified = false;
    writeState(state);
    return state;
  }

  function setSubject(subject) {
    const state = deriveState();
    state.currentSubject = subject?.subjectID || null;
    state.currentSubjectName = subject?.subjectName || null;
    writeState(state);
    return state;
  }

  function setPopout(value) {
    const state = deriveState();
    state.popout = Boolean(value);
    writeState(state);
    return state;
  }

  function subscribe(listener) {
    listeners.add(listener);
    listener(deriveState());
    return () => listeners.delete(listener);
  }

  window.DustyStudyTimer = {
    getState: deriveState,
    saveState: writeState,
    subscribe,
    formatTime,
    startTimer,
    pauseTimer,
    resetTimer,
    completeTimer,
    autosave,
    setPreset,
    setSubject,
    setPopout
  };

  function createWidget() {
    if (document.getElementById('dustyTimerWidget')) {
      return;
    }

    const widget = document.createElement('section');
    widget.id = 'dustyTimerWidget';
    widget.className = 'dusty-timer-widget';
    widget.innerHTML = `
      <div class="dusty-widget-top">
        <div>
          <p class="dusty-widget-label" id="dustyWidgetPreset">Custom Timer</p>
          <strong id="dustyWidgetTime">60:00</strong>
          <span id="dustyWidgetSubject">No subject</span>
        </div>
        <button class="dusty-widget-close" type="button" id="dustyWidgetClose" aria-label="Hide timer">x</button>
      </div>
      <div class="dusty-widget-actions">
        <button class="btn btn-secondary" type="button" id="dustyWidgetReset">Reset</button>
        <button class="btn btn-primary" type="button" id="dustyWidgetToggle">Start</button>
      </div>
    `;

    document.body.appendChild(widget);
    document.getElementById('dustyWidgetClose')?.addEventListener('click', () => setPopout(false));
    document.getElementById('dustyWidgetToggle')?.addEventListener('click', async () => {
      const state = deriveState();
      if (state.isRunning) {
        await pauseTimer();
      } else {
        await startTimer();
      }
    });
    document.getElementById('dustyWidgetReset')?.addEventListener('click', () => resetTimer(true));
  }

  function renderWidget(state) {
    const widget = document.getElementById('dustyTimerWidget');
    if (!widget) {
      return;
    }

    widget.classList.toggle('is-visible', Boolean(state.popout));
    document.getElementById('dustyWidgetPreset').textContent = state.currentPresetName || 'Custom Timer';
    document.getElementById('dustyWidgetTime').textContent = formatTime(state.remainingSeconds);
    document.getElementById('dustyWidgetSubject').textContent = state.currentSubjectName || 'No subject';
    document.getElementById('dustyWidgetToggle').textContent = state.isRunning ? 'Pause' : 'Start';
  }

  const dustyAppPages = ['/home', '/timer', '/tasks', '/chat', '/calendar', '/flashcards', '/resources', '/progress'];

  function isDustyAppPage() {
    const normalizedPath = window.location.pathname.replace(/\/$/, '');
    return dustyAppPages.some(page => normalizedPath === page || normalizedPath.startsWith(page + '/'));
  }

  document.addEventListener('DOMContentLoaded', () => {
    if (!isDustyAppPage()) {
      return;
    }

    createWidget();
    subscribe(renderWidget);
  });

  setInterval(async () => {
    const state = deriveState(true);
    if (state.isRunning && state.sessionID && Number(state.elapsedSeconds || 0) - Number(state.lastAutosaveElapsed || 0) >= AUTOSAVE_SECONDS) {
      try {
        await autosave('in_progress');
      } catch (error) {
        console.error('Timer autosave failed:', error);
      }
    }

    if (!state.isRunning && state.remainingSeconds === 0 && state.sessionID && !state.completedNotified) {
      try {
        const completedState = await completeTimer('');
        listeners.forEach(listener => listener(Object.assign({}, completedState, { justCompleted: true })));
      } catch (error) {
        console.error('Timer completion save failed:', error);
      }
    }
  }, 1000);
})();

// Preferences Modal Management
const SUBJECTS = [
    { key: 'biology',       label: 'Biology',               defaultColour: 'green' },
    { key: 'chemistry',     label: 'Chemistry',             defaultColour: 'blue' },
    { key: 'physics',       label: 'Physics',               defaultColour: 'purple' },
    { key: 'ext2_math',     label: 'Extension 2 Maths',     defaultColour: 'red' },
    { key: 'ext1_math',     label: 'Extension 1 Maths',     defaultColour: 'orange' },
    { key: 'advanced_math', label: 'Mathematics Advanced',  defaultColour: 'yellow' },
    { key: 'eng_adv',       label: 'English Advanced',      defaultColour: 'brown' },
    { key: 'eng_std',       label: 'English Standard',      defaultColour: 'brown' },
    { key: 'software_eng',  label: 'Software Engineering',  defaultColour: 'blue' },
    { key: 'economics',     label: 'Economics',             defaultColour: 'green' },
    { key: 'legal',         label: 'Legal Studies',         defaultColour: 'purple' },
    { key: 'history',       label: 'Modern History',        defaultColour: 'red' },
];
 
const COLOURS = {
    orange: { hex: '#f5761c', rgb: '245,118,28', label: 'Orange' },
    blue:   { hex: '#2563eb', rgb: '37,99,235',  label: 'Blue' },
    green:  { hex: '#15803d', rgb: '21,128,61',  label: 'Green' },
    red:    { hex: '#dc2626', rgb: '220,38,38',  label: 'Red' },
    purple: { hex: '#7c3aed', rgb: '124,58,237', label: 'Purple' },
    yellow: { hex: '#d97706', rgb: '217,119,6',  label: 'Amber' },
    brown:  { hex: '#92400e', rgb: '146,64,14',  label: 'Brown' },
    teal:   { hex: '#0891b2', rgb: '8,145,178',  label: 'Teal' },
    pink:   { hex: '#be185d', rgb: '190,24,93',  label: 'Pink' },
};

const prefsState = {
    selected: new Set(),
    colours: {}
};

function openPrefsModal() {
    // Use setTimeout to ensure popup is fully removed before showing modal
    setTimeout(() => {
        const modal = document.getElementById('prefsModal');
        if (modal) {
            modal.classList.remove('hidden');
            // Reset to first step
            document.getElementById('stepPanel0')?.classList.add('visible');
            document.getElementById('stepPanel1')?.classList.remove('visible');
            document.getElementById('step0')?.classList.add('active');
            document.getElementById('step0')?.classList.remove('done');
            document.getElementById('step1')?.classList.remove('active');
            document.getElementById('step1')?.classList.remove('done');
            // Load subjects and build grid
            loadSignupSubjects().then(() => {
                prefsState.selected.clear();
                prefsState.colours = {};
                buildSubjectGrid();
            }).catch(err => {
                console.error('Failed to load subjects for preferences modal:', err);
                showPopup('Error', 'Could not load subjects. Please try again.');
            });
        }
    }, 50);
}

function closePrefsModal() {
    const modal = document.getElementById('prefsModal');
    if (modal) {
        modal.classList.add('hidden');
    }
}

async function loadSignupSubjects() {
  try {
    const res = await fetch('/api/subjects');
    const data = await res.json();
    if (res.ok && Array.isArray(data.subjects)) {
      // Map to expected lightweight shape used in prefs modal
      window.signupSubjects = data.subjects.map(s => ({
        subjectID: s.subjectID,
        subjectKey: String(s.subjectID),
        subjectName: s.subjectName,
        colourScheme: s.colourScheme || 'orange'
      }));
      return window.signupSubjects;
    }
  } catch (e) {
    console.error('Could not fetch /api/subjects for signup modal', e);
  }
  // Fallback to built-in SUBJECTS list
  window.signupSubjects = SUBJECTS.map(s => ({ subjectKey: s.key, subjectName: s.label, colourScheme: s.defaultColour }));
  return window.signupSubjects;
}

function buildSubjectGrid() {
    const grid = document.getElementById('subjectPresetGrid');
    grid.innerHTML = SUBJECTS.map(s => {
        const col = COLOURS[s.defaultColour] || COLOURS.orange;
        return `
            <button class="subject-preset-btn" type="button"
                    data-key="${s.key}"
                    style="--subj-col:${col.hex};--subj-col-rgb:${col.rgb}"
                    onclick="toggleSubject(this, '${s.key}', '${s.defaultColour}')">
                <span class="subj-check"></span>
                <span>${s.label}</span>
                <span class="subj-colour-dot"></span>
            </button>`;
    }).join('');
}

function toggleSubject(btn, key, defaultColour) {
    if (prefsState.selected.has(key)) {
        prefsState.selected.delete(key);
        delete prefsState.colours[key];
        btn.classList.remove('selected');
    } else {
        prefsState.selected.add(key);
        prefsState.colours[key] = defaultColour;
        btn.classList.add('selected');
    }
    /* Update button icon */
    btn.querySelector('.subj-check').textContent = prefsState.selected.has(key) ? '✓' : '';
    /* Enable/disable next button */
    document.getElementById('nextStepBtn').disabled = prefsState.selected.size === 0;
}

function goToStep2() {
    if (prefsState.selected.size === 0) return;
    buildColourAssignments();
    setStep(1);
}
 
function goToStep1() { setStep(0); }
 
function setStep(n) {
    [0,1].forEach(i => {
        document.getElementById(`stepPanel${i}`).classList.toggle('visible', i === n);
        document.getElementById(`step${i}`).className = 'prefs-step' + (i < n ? ' done' : i === n ? ' active' : '');
    });
}

function buildColourAssignments() {
    const wrap = document.getElementById('colourAssignments');
    const selectedSubjects = SUBJECTS.filter(s => prefsState.selected.has(s.key));
 
    wrap.innerHTML = selectedSubjects.map(s => {
        const swatches = Object.entries(COLOURS).map(([key, c]) => {
            const isActive = prefsState.colours[s.key] === key;
            return `<div class="colour-swatch ${isActive ? 'active' : ''}"
                        style="background:${c.hex}"
                        title="${c.label}"
                        onclick="pickColour('${s.key}', '${key}', this)"></div>`;
        }).join('');
 
        return `
            <div class="colour-row" id="crow-${s.key}">
                <span class="colour-row-name">${s.label}</span>
                <div class="colour-swatches">${swatches}</div>
            </div>`;
    }).join('');
}

function pickColour(subjectKey, colourKey, swatchEl) {
    prefsState.colours[subjectKey] = colourKey;
    /* Deactivate all swatches in this row, activate picked one */
    const row = swatchEl.closest('.colour-row');
    row.querySelectorAll('.colour-swatch').forEach(s => s.classList.remove('active'));
    swatchEl.classList.add('active');
}

async function savePreferences() {
    const btn = document.getElementById('savePrefsBtn');
      if (btn) btn.disabled = true;
      
      if (prefsState.selected.size === 0) {
          showPopup('No Subjects', 'Please select at least one subject.');
          if (btn) btn.disabled = false;
          return;
      }
    
    try {
        const payload = {
            subjects: Array.from(prefsState.selected).map(subjectKey => {
                const subject = SUBJECTS.find(s => s.key === subjectKey);
                return {
                    subjectKey,
                    subjectName: subject ? subject.label : subjectKey,
                    colourScheme: prefsState.colours[subjectKey] || 'orange'
                };
            })
        };

        const response = await fetch('/api/user/preferences', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        });
        const data = await response.json().catch(() => ({}));

        if (response.ok && data.success) {
            const signupSubjects = window.signupSubjects || [];
            const colourMap = {};
            signupSubjects.forEach(s => {
                if (prefsState.selected.has(String(s.subjectID || s.subjectKey))) {
                    colourMap[s.subjectName] = prefsState.colours[String(s.subjectID || s.subjectKey)] || s.colourScheme || 'orange';
                }
            });
            localStorage.setItem('dusty.subjectColours', JSON.stringify(colourMap));
            window.location.href = '/home';
            return;
        } else {
            showPopup('Preferences Error', data.error || 'Could not save preferences. Please try again.');
            if (btn) btn.disabled = false;
        }
    } catch (err) {
        console.error('[Preferences] Save error:', err);
        showPopup('Network Error', 'Unable to save preferences right now. Please try again.');
        if (btn) btn.disabled = false;
    }
}

function skipPrefs() {
    window.location.href = '/home';
}
