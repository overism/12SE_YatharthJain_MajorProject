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

function ensureSidebarDrawer() {
  const sidebar = document.querySelector('.sidebar');
  if (!sidebar || document.querySelector('.sidebar-menu-toggle')) {
    return;
  }

  const toggle = document.createElement('button');
  toggle.type = 'button';
  toggle.className = 'sidebar-menu-toggle';
  toggle.setAttribute('aria-label', 'Open navigation menu');
  toggle.setAttribute('aria-expanded', 'false');
  toggle.innerHTML = '<span class="sidebar-menu-icon" aria-hidden="true"></span>';

  const backdrop = document.createElement('div');
  backdrop.className = 'sidebar-backdrop';
  backdrop.setAttribute('aria-hidden', 'true');

  document.body.appendChild(toggle);
  document.body.appendChild(backdrop);

  const closeSidebar = () => {
    document.body.classList.remove('sidebar-open');
    sidebar.classList.remove('is-open');
    toggle.setAttribute('aria-expanded', 'false');
    backdrop.classList.remove('is-visible');
  };

  const openSidebar = () => {
    document.body.classList.add('sidebar-open');
    sidebar.classList.add('is-open');
    toggle.setAttribute('aria-expanded', 'true');
    backdrop.classList.add('is-visible');
  };

  const syncSidebarState = () => {
    if (window.innerWidth > 900) {
      closeSidebar();
    }
  };

  toggle.addEventListener('click', () => {
    if (document.body.classList.contains('sidebar-open')) {
      closeSidebar();
    } else {
      openSidebar();
    }
  });

  backdrop.addEventListener('click', closeSidebar);

  sidebar.querySelectorAll('a').forEach(link => {
    link.addEventListener('click', () => {
      if (window.innerWidth <= 900) {
        closeSidebar();
      }
    });
  });

  window.addEventListener('resize', syncSidebarState);
  window.addEventListener('keydown', event => {
    if (event.key === 'Escape') {
      closeSidebar();
    }
  });

  syncSidebarState();
}

window.addEventListener('DOMContentLoaded', ensureSidebarDrawer);

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
    // Mathematics
    { key: 'advanced_math',  label: 'Mathematics Advanced',       defaultColour: 'blue'   },
    { key: 'std_math',       label: 'Mathematics Standard 2',     defaultColour: 'teal'   },
    { key: 'ext1_math',      label: 'Mathematics Extension 1',    defaultColour: 'orange' },
    { key: 'ext2_math',      label: 'Mathematics Extension 2',    defaultColour: 'red'    },

    // English
    { key: 'eng_adv',        label: 'English Advanced',           defaultColour: 'green'  },
    { key: 'eng_std',        label: 'English Standard',           defaultColour: 'green'  },
    { key: 'eng_ext1',       label: 'English Extension 1',        defaultColour: 'brown'  },
    { key: 'eng_ext2',       label: 'English Extension 2',        defaultColour: 'brown'  },

    // Sciences
    { key: 'biology',        label: 'Biology',                    defaultColour: 'green'  },
    { key: 'chemistry',      label: 'Chemistry',                  defaultColour: 'blue'   },
    { key: 'physics',        label: 'Physics',                    defaultColour: 'purple' },
    { key: 'earth_science',  label: 'Earth and Environmental',    defaultColour: 'teal'   },
    { key: 'psychology',     label: 'Psychology',                 defaultColour: 'pink'   },

    // Humanities and Social Sciences
    { key: 'modern_history', label: 'Modern History',             defaultColour: 'red'    },
    { key: 'ancient_history',label: 'Ancient History',            defaultColour: 'brown'  },
    { key: 'economics',      label: 'Economics',                  defaultColour: 'orange' },
    { key: 'legal',          label: 'Legal Studies',              defaultColour: 'purple' },
    { key: 'business',       label: 'Business Studies',           defaultColour: 'orange' },
    { key: 'geography',      label: 'Geography',                  defaultColour: 'teal'   },
    { key: 'society_culture',label: 'Society and Culture',        defaultColour: 'pink'   },
    { key: 'history_ext',    label: 'History Extension',          defaultColour: 'red'    },

    // Technology
    { key: 'software_eng',   label: 'Software Engineering',       defaultColour: 'blue'   },
    { key: 'ipt',            label: 'Information Processes',      defaultColour: 'teal'   },
    { key: 'engineering',    label: 'Engineering Studies',        defaultColour: 'orange' },
    { key: 'design_tech',    label: 'Design and Technology',      defaultColour: 'yellow' },
    { key: 'industrial_tech',label: 'Industrial Technology',      defaultColour: 'brown'  },

    // Creative Arts
    { key: 'visual_arts',    label: 'Visual Arts',                defaultColour: 'pink'   },
    { key: 'music1',         label: 'Music 1',                    defaultColour: 'purple' },
    { key: 'music2',         label: 'Music 2',                    defaultColour: 'purple' },
    { key: 'drama',          label: 'Drama',                      defaultColour: 'orange' },
    { key: 'dance',          label: 'Dance',                      defaultColour: 'pink'   },

    // PDHPE and Sport
    { key: 'pdhpe',          label: 'PDHPE',                      defaultColour: 'green'  },
    { key: 'community_family',label: 'Community and Family',      defaultColour: 'teal'   },
    { key: 'sport_lifestyle', label: 'Sport, Lifestyle & Recreation', defaultColour: 'green'},

    // Languages
    { key: 'french',         label: 'French',                     defaultColour: 'blue'   },
    { key: 'japanese',       label: 'Japanese',                   defaultColour: 'red'    },
    { key: 'chinese',        label: 'Chinese',                    defaultColour: 'red'    },
    { key: 'spanish',        label: 'Spanish',                    defaultColour: 'orange' },
    { key: 'german',         label: 'German',                     defaultColour: 'brown'  },

    // Other
    { key: 'studies_religion', label: 'Studies of Religion',      defaultColour: 'purple' },
    { key: 'general',          label: 'General',                  defaultColour: 'orange' },
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

const STUDY_TECHNIQUES = [
    { key: 'spaced_repetition', label: 'Spaced Repetition',    desc: 'Review content over increasing intervals to build long-term retention.' },
    { key: 'active_recall',     label: 'Active Recall',         desc: 'Test yourself without notes to strengthen memory and exam readiness.' },
    { key: 'blurting',          label: 'Blurting',              desc: 'Write everything you remember, then compare with your notes.' },
    { key: 'stoplight',         label: 'Stop-Light Method',     desc: 'Rate confidence as Red, Yellow or Green to identify knowledge gaps.' },
    { key: 'interleaving',      label: 'Interleaving',          desc: 'Mix topics and subjects during study instead of blocking one at a time.' },
    { key: 'retrieval',         label: 'Retrieval Practice',    desc: 'Practise recalling information using flashcards and practice questions.' },
    { key: 'exam_questions',    label: 'Exam Style Questions',  desc: 'Practise timed HSC-style questions and review marking criteria.' },
    { key: 'error_analysis',    label: 'Error Analysis',        desc: 'Review mistakes from quizzes and homework to target weak areas.' },
    { key: 'worked_examples',   label: 'Worked Examples',       desc: 'Study model solutions before attempting similar problems yourself.' },
    { key: 'past_papers',       label: 'Past Paper Practice',   desc: 'Complete full past HSC papers under timed exam conditions.' },
];

const prefsState = {
    selected:   new Set(),
    colours:    {},
    techniques: new Set(),
    subjects:   []
};

/* Onboarding */

function openPrefsModal() {
    setTimeout(() => {
        ensurePrefsModal();
        injectPrefsStyles();
        const modal = document.getElementById('prefsModal');
        if (!modal) return;

        modal.classList.remove('hidden');
        loadSignupSubjects().then(() => {
            prefsState.selected.clear();
            prefsState.colours = {};
            buildSubjectGrid();
            setStep(0);
        }).catch(err => {
            console.error('Failed to load subjects for preferences modal:', err);
            showPopup('Error', 'Could not load subjects. Please try again.');
        });
    }, 50);
}

async function loadSignupSubjects() {
    // Always use the full hardcoded SUBJECTS list for onboarding
    // Never use DB subjects here — the user is choosing what they want
    window.signupSubjects = SUBJECTS.map(s => ({
        subjectKey:   s.key,
        subjectName:  s.label,
        colourScheme: normalizeColour(s.defaultColour || 'orange')
    }));
    prefsState.subjects = window.signupSubjects;

    // Still load scheduler prefs if they exist (for returning users redoing onboarding)
    try {
        const res = await fetch('/api/user/preferences');
        const data = await res.json();
        if (res.ok && data.scheduler) {
            populateSchedulerPrefs(data.scheduler);
        }
    } catch (e) {
        // Ignore — scheduler prefs are optional during onboarding
    }

    return window.signupSubjects;
}

function buildSubjectGrid() {
    const grid = document.getElementById('subjectPresetGrid');
    if (!grid) return;

    const subjects = prefsState.subjects.length ? prefsState.subjects : (window.signupSubjects || []);
    grid.innerHTML = subjects.map(s => {
        const key = String(s.subjectID || s.subjectKey);
        const colour = normalizeColour(s.colourScheme || s.defaultColour || 'orange');
        const col = COLOURS[colour] || COLOURS.orange;
        return `
            <button class="subject-preset-btn" type="button"
                    data-key="${key}"
                    style="--subj-col:${col.hex};--subj-col-rgb:${col.rgb}"
                    onclick="toggleSubject(this, '${key}', '${colour}')">
                <span class="subj-check"></span>
                <span>${escapeHtml(s.subjectName || s.label)}</span>
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
        prefsState.colours[key] = normalizeColour(defaultColour);
        btn.classList.add('selected');
    }

    const check = btn.querySelector('.subj-check');
    if (check) check.textContent = prefsState.selected.has(key) ? '✓' : '';
    const next = document.getElementById('nextStepBtn');
    if (next) next.disabled = prefsState.selected.size === 0;
}

function goToStep1() { setStep(0); }

function goToStep2() {
    if (prefsState.selected.size === 0) return;
    buildColourAssignments();
    setStep(1);
}

function goToStep3() { setStep(2); }

function setStep(n) {
    [0, 1, 2, 3].forEach(i => {
        document.getElementById(`stepPanel${i}`)?.classList.toggle('visible', i === n);
        const step = document.getElementById(`step${i}`);
        if (step) step.className = 'prefs-step' + (i < n ? ' done' : i === n ? ' active' : '');
    });
}

function goToStep4() {
    buildTechniquesGrid();
    setStep(3);
}

function buildColourAssignments() {
    const wrap = document.getElementById('colourAssignments');
    if (!wrap) return;

    const selectedSubjects = (prefsState.subjects || [])
        .filter(s => prefsState.selected.has(String(s.subjectID || s.subjectKey)));

    wrap.innerHTML = selectedSubjects.map(s => {
        const subjectKey = String(s.subjectID || s.subjectKey);
        const swatches = Object.entries(COLOURS).map(([key, c]) => {
            const isActive = prefsState.colours[subjectKey] === key;
            return `<div class="colour-swatch ${isActive ? 'active' : ''}"
                        style="background:${c.hex}"
                        title="${c.label}"
                        onclick="pickColour('${subjectKey}', '${key}', this)"></div>`;
        }).join('');

        return `
            <div class="colour-row" id="crow-${subjectKey}">
                <span class="colour-row-name">${escapeHtml(s.subjectName || s.label)}</span>
                <div class="colour-swatches">${swatches}</div>
            </div>`;
    }).join('');
}

function buildTechniquesGrid() {
    const grid = document.getElementById('techniquesGrid');
    if (!grid) return;
    grid.innerHTML = STUDY_TECHNIQUES.map(t => `
        <div class="technique-card ${prefsState.techniques?.has(t.key) ? 'selected' : ''}"
             id="tech-${t.key}"
             onclick="toggleTechnique('${t.key}', this)">
            <div class="technique-check">${prefsState.techniques?.has(t.key) ? '✓' : ''}</div>
            <div class="technique-info">
                <strong>${escapeHtml(t.label)}</strong>
                <span>${escapeHtml(t.desc)}</span>
            </div>
        </div>
    `).join('');
}

function toggleTechnique(key, card) {
    if (!prefsState.techniques) prefsState.techniques = new Set();
    if (prefsState.techniques.has(key)) {
        prefsState.techniques.delete(key);
        card.classList.remove('selected');
        card.querySelector('.technique-check').textContent = '';
    } else {
        prefsState.techniques.add(key);
        card.classList.add('selected');
        card.querySelector('.technique-check').textContent = '✓';
    }
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
        const subjects = prefsState.subjects || [];

        // Build subject list — for new users subjectID may not exist yet
        const subjectPayload = Array.from(prefsState.selected).map(subjectKey => {
            const subject = subjects.find(s => String(s.subjectID || s.subjectKey) === subjectKey);
            const payload = {
                colourScheme: prefsState.colours[subjectKey] || 'orange'
            };

            // Only include subjectID if it's a real integer (existing DB subject)
            if (subject?.subjectID && Number.isInteger(Number(subject.subjectID))) {
                payload.subjectID = Number(subject.subjectID);
            }

            // Always include subjectName as fallback
            payload.subjectName = subject
                ? (subject.subjectName || subject.label || subjectKey)
                : subjectKey;

            return payload;
        });

        const response = await fetch('/api/user/preferences', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                theme: 'light',
                subjects: subjectPayload,
                scheduler: collectSchedulerPreferences()
            })
        });

        const data = await response.json().catch(() => ({}));

        if (response.ok && data.success) {
            // Always redirect to home — works for both onboarding and profile edits
            const path = window.location.pathname.replace(/\/$/, '');
            if (path === '/onboarding' || path === '/signup') {
                window.location.href = '/home';
            } else {
                closePrefsModal();
                showPopup('Preferences Saved', 'Your scheduler preferences have been saved.');
            }
            return;
        }

        showPopup('Preferences Error', data.error || 'Could not save preferences. Please try again.');
        if (btn) btn.disabled = false;

    } catch (err) {
        console.error('[Preferences] Save error:', err);
        showPopup('Network Error', 'Unable to save preferences right now. Please try again.');
        if (btn) btn.disabled = false;
    }
}

function collectSchedulerPreferences() {
    return {
        study_start:         Number(document.getElementById('studyStartTime')?.value  || 8),
        study_end:           Number(document.getElementById('studyEndTime')?.value    || 22),
        sleep_start:         Number(document.getElementById('sleepStartTime')?.value  || 22),
        sleep_end:           Number(document.getElementById('sleepEndTime')?.value    || 7),
        school_start:        Number(document.getElementById('schoolStartTime')?.value || 9),
        school_end:          Number(document.getElementById('schoolEndTime')?.value   || 15),
        max_daily_hours:     Number(document.getElementById('maxDailyStudy')?.value   || 4),
        session_duration:    Number(document.getElementById('sessionDuration')?.value || 60),
        break_duration:      Number(document.getElementById('breakDuration')?.value   || 10),
        priority_subjects:   Array.from(prefsState.selected),
        study_techniques:    prefsState.techniques && prefsState.techniques.size > 0
                                 ? Array.from(prefsState.techniques).map(k => {
                                       const t = STUDY_TECHNIQUES.find(t => t.key === k);
                                       return t ? t.label : k;
                                   })
                                 : STUDY_TECHNIQUES.map(t => t.label), // default all if none selected
        scheduler_onboarded: true
    };
}

function populateSchedulerPrefs(scheduler) {
    const values = scheduler || {};
    const map = {
        studyStartTime: values.study_start ?? 8,
        studyEndTime: values.study_end ?? 22,
        sleepStartTime: values.sleep_start ?? 22,
        sleepEndTime: values.sleep_end ?? 7,
        schoolStartTime: values.school_start ?? 9,
        schoolEndTime: values.school_end ?? 15,
        maxDailyStudy: values.max_daily_hours ?? 4,
        sessionDuration: values.session_duration ?? 60,
        breakDuration: values.break_duration ?? 10
    };
    Object.entries(map).forEach(([id, value]) => {
        const el = document.getElementById(id);
        if (el) el.value = String(value);
    });
}

function normalizeColour(colour) {
    return colour === 'yellow' ? 'amber' : colour;
}

function escapeHtml(value) {
    return String(value ?? '')
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;');
}

function ensurePrefsModal() {
    if (document.getElementById('prefsModal')) {
        ensureSchedulerFields();
        return;
    }
    const modal = document.createElement('div');
    modal.className = 'prefs-overlay hidden';
    modal.id = 'prefsModal';
    modal.setAttribute('role', 'dialog');
    modal.setAttribute('aria-modal', 'true');
    modal.innerHTML = `
        <div class="prefs-box">
            <div class="prefs-logo"><img src="/static/images/transp192_copy.png" alt="Dusty"></div>
            <h2 class="prefs-heading" id="prefsHeading">Set up your study scheduler</h2>
            <p class="prefs-sub">Choose your subjects, colours, study hours and preferred techniques.</p>
            <div class="prefs-steps">
                <div class="prefs-step active" id="step0"></div>
                <div class="prefs-step" id="step1"></div>
                <div class="prefs-step" id="step2"></div>
                <div class="prefs-step" id="step3"></div>
            </div>

            <!-- Step 0: Subjects -->
            <div class="prefs-step-panel visible" id="stepPanel0">
                <p class="prefs-section-label">Your HSC Subjects</p>
                <div class="subject-preset-grid" id="subjectPresetGrid"></div>
                <div class="prefs-actions">
                    <button class="btn-prefs-skip" type="button" onclick="skipPrefs()">Skip for now</button>
                    <button class="btn-prefs-save" type="button" id="nextStepBtn" onclick="goToStep2()" disabled>Choose Colours →</button>
                </div>
            </div>

            <!-- Step 1: Colours -->
            <div class="prefs-step-panel" id="stepPanel1">
                <p class="prefs-section-label">Subject Colours</p>
                <div class="colour-assignments" id="colourAssignments"></div>
                <div class="prefs-actions">
                    <button class="btn-prefs-skip" type="button" onclick="goToStep1()">← Back</button>
                    <button class="btn-prefs-save" type="button" onclick="goToStep3()">Schedule Settings →</button>
                </div>
            </div>

            <!-- Step 2: Schedule -->
            <div class="prefs-step-panel" id="stepPanel2">
                <p class="prefs-section-label">Study Schedule</p>
                <div class="schedule-prefs-grid" id="schedulePrefsGrid"></div>
                <div class="prefs-actions">
                    <button class="btn-prefs-skip" type="button" onclick="goToStep2()">← Back</button>
                    <button class="btn-prefs-save" type="button" onclick="goToStep4()">Study Techniques →</button>
                </div>
            </div>

            <!-- Step 3: Techniques -->
            <div class="prefs-step-panel" id="stepPanel3">
                <p class="prefs-section-label">Preferred Study Techniques</p>
                <p style="font-size:13px;color:#888;margin:0 0 14px">Select the techniques you want Dusty to prioritise when generating your schedule. You can select multiple.</p>
                <div class="techniques-grid" id="techniquesGrid"></div>
                <div class="prefs-actions">
                    <button class="btn-prefs-skip" type="button" onclick="goToStep3()">← Back</button>
                    <button class="btn-prefs-save" type="button" id="savePrefsBtn" onclick="savePreferences()">Save &amp; Get Started 🚀</button>
                </div>
                <p class="prefs-note">You can change these anytime from your Profile settings.</p>
            </div>
        </div>`;
    document.body.appendChild(modal);
    ensureSchedulerFields();
}

function ensureSchedulerFields() {
    const grid = document.getElementById('schedulePrefsGrid') || document.querySelector('.schedule-prefs-grid');
    if (!grid || document.getElementById('breakDuration')) return;
    grid.innerHTML = `
        <div class="schedule-pref-item"><label class="schedule-pref-label">Study Start Time</label><select id="studyStartTime" class="schedule-pref-select">${hourOptions(6, 10, 8)}</select></div>
        <div class="schedule-pref-item"><label class="schedule-pref-label">Study End Time</label><select id="studyEndTime" class="schedule-pref-select">${hourOptions(20, 23, 22)}</select></div>
        <div class="schedule-pref-item"><label class="schedule-pref-label">Sleep Time</label><select id="sleepStartTime" class="schedule-pref-select">${hourOptions(21, 23, 22)}<option value="0">12:00 AM</option></select></div>
        <div class="schedule-pref-item"><label class="schedule-pref-label">Wake Up Time</label><select id="sleepEndTime" class="schedule-pref-select">${hourOptions(5, 8, 7)}</select></div>
        <div class="schedule-pref-item"><label class="schedule-pref-label">School Start</label><select id="schoolStartTime" class="schedule-pref-select">${hourOptions(7, 10, 9)}</select></div>
        <div class="schedule-pref-item"><label class="schedule-pref-label">School End</label><select id="schoolEndTime" class="schedule-pref-select">${hourOptions(14, 17, 15)}</select></div>
        <div class="schedule-pref-item"><label class="schedule-pref-label">Max Daily Study</label><select id="maxDailyStudy" class="schedule-pref-select">${numberOptions(2, 6, 4, ' hours')}</select></div>
        <div class="schedule-pref-item"><label class="schedule-pref-label">Default Session</label><select id="sessionDuration" class="schedule-pref-select">${minuteOptions([30,45,60,90,120], 60)}</select></div>
        <div class="schedule-pref-item"><label class="schedule-pref-label">Break Length</label><select id="breakDuration" class="schedule-pref-select">${minuteOptions([0,5,10,15,20], 10)}</select></div>
    `;
}

function hourOptions(start, end, selected) {
    let html = '';
    for (let h = start; h <= end; h += 1) {
        const suffix = h >= 12 ? 'PM' : 'AM';
        const display = h === 0 ? 12 : (h > 12 ? h - 12 : h);
        html += `<option value="${h}" ${h === selected ? 'selected' : ''}>${display}:00 ${suffix}</option>`;
    }
    return html;
}

function numberOptions(start, end, selected, suffix) {
    let html = '';
    for (let n = start; n <= end; n += 1) {
        html += `<option value="${n}" ${n === selected ? 'selected' : ''}>${n}${suffix}</option>`;
    }
    return html;
}

function minuteOptions(values, selected) {
    return values.map(v => `<option value="${v}" ${v === selected ? 'selected' : ''}>${v === 60 ? '1 hour' : v + ' minutes'}</option>`).join('');
}

function injectPrefsStyles() {
    if (document.getElementById('dynamicPrefsStyles')) return;
    const style = document.createElement('style');
    style.id = 'dynamicPrefsStyles';
    style.textContent = `
        .prefs-overlay{position:fixed;inset:0;z-index:6000;background:rgba(0,0,0,.62);backdrop-filter:blur(12px);display:flex;align-items:center;justify-content:center;padding:18px}.prefs-overlay.hidden{display:none}
        .prefs-box{width:min(720px,96vw);max-height:92vh;overflow:auto;background:#fff;border-radius:18px;padding:28px;box-shadow:0 30px 80px rgba(0,0,0,.28);color:#22140b}.prefs-logo{text-align:center}.prefs-logo img{width:68px;height:68px;object-fit:contain}
        .prefs-heading{font-family:'Cooper BT',Arial,serif;font-size:26px;text-align:center;margin:8px 0 6px;color:#22140b}.prefs-sub{text-align:center;color:#777;margin:0 0 18px;line-height:1.5}
        .prefs-steps{display:flex;gap:8px;justify-content:center;margin:0 0 18px}.prefs-step{width:42px;height:5px;border-radius:99px;background:#e5e7eb}.prefs-step.active,.prefs-step.done{background:linear-gradient(135deg,#f5761c,#ee4319)}
        .prefs-step-panel{display:none}.prefs-step-panel.visible{display:block}.prefs-section-label{font-weight:800;margin:0 0 12px;color:#22140b}
        .subject-preset-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));gap:10px}.subject-preset-btn{display:flex;align-items:center;gap:10px;border:1.5px solid rgba(34,20,11,.1);background:#fff;border-radius:12px;padding:12px;cursor:pointer;font-weight:700;color:#22140b}.subject-preset-btn.selected{border-color:var(--subj-col);background:rgba(var(--subj-col-rgb),.08)}
        .subj-check{width:20px;height:20px;border-radius:50%;border:1.5px solid var(--subj-col);display:inline-flex;align-items:center;justify-content:center;color:var(--subj-col);font-size:12px}.subj-colour-dot{margin-left:auto;width:12px;height:12px;border-radius:50%;background:var(--subj-col)}
        .colour-assignments{display:grid;gap:10px}.colour-row{display:flex;align-items:center;justify-content:space-between;gap:14px;padding:12px;border:1px solid rgba(0,0,0,.08);border-radius:12px}.colour-row-name{font-weight:700}.colour-swatches{display:flex;gap:8px;flex-wrap:wrap}.colour-swatch{width:24px;height:24px;border-radius:50%;cursor:pointer;border:3px solid transparent}.colour-swatch.active{border-color:#22140b}
        .schedule-prefs-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(170px,1fr));gap:12px}.schedule-pref-item{display:flex;flex-direction:column;gap:6px}.schedule-pref-label{font-size:11px;text-transform:uppercase;letter-spacing:.7px;font-weight:800;color:#888}.schedule-pref-select{padding:11px 12px;border-radius:10px;border:1.5px solid #e1e5e9;background:#fff;color:#22140b}
        .prefs-actions{display:flex;justify-content:flex-end;gap:10px;flex-wrap:wrap;margin-top:18px}.btn-prefs-skip,.btn-prefs-save{border:0;border-radius:12px;padding:11px 18px;font-weight:800;cursor:pointer}.btn-prefs-skip{background:#f3f4f6;color:#555}.btn-prefs-save{background:linear-gradient(135deg,#f5761c,#ee4319);color:#fff}.btn-prefs-save:disabled{opacity:.55;cursor:not-allowed}.prefs-note{font-size:12px;color:#888;margin:12px 0 0;text-align:right}
        .techniques-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(280px,1fr));gap:10px;max-height:340px;overflow-y:auto;padding-right:4px}
        .technique-card{display:flex;align-items:flex-start;gap:12px;padding:13px 14px;border:1.5px solid rgba(0,0,0,.1);border-radius:12px;background:#fff;cursor:pointer;transition:all .18s ease}
        .technique-card:hover{border-color:rgba(245,118,28,.35);background:rgba(245,118,28,.04)}
        .technique-card.selected{border-color:#f5761c;background:rgba(245,118,28,.08)}
        .technique-check{width:22px;height:22px;border-radius:50%;border:1.5px solid #f5761c;display:inline-flex;align-items:center;justify-content:center;color:#f5761c;font-size:12px;font-weight:800;flex-shrink:0;margin-top:1px}
        .technique-card.selected .technique-check{background:#f5761c;color:#fff}
        .technique-info strong{display:block;font-size:13.5px;font-weight:700;color:#22140b;margin-bottom:3px}
        .technique-info span{font-size:12px;color:#888;line-height:1.45}
        @media(max-width:640px){.prefs-box{padding:20px}.colour-row{align-items:flex-start;flex-direction:column}.prefs-actions{justify-content:stretch}.btn-prefs-skip,.btn-prefs-save{flex:1}}
    `;
    document.head.appendChild(style);
}

function skipPrefs() {
    const path = window.location.pathname.replace(/\/$/, '');
    if (path === '/onboarding' || path === '/signup') {
        window.location.href = '/home';
        return;
    }
    sessionStorage.setItem('dusty.skipSchedulerOnboarding', '1');
    closePrefsModal();
}

document.addEventListener('DOMContentLoaded', async () => {
    const path = window.location.pathname.replace(/\/$/, '');
    if (!isDustyAppPage() || path === '/signup' || sessionStorage.getItem('dusty.skipSchedulerOnboarding') === '1') return;
    try {
        const res = await fetch('/api/user/onboarding-status');
        const data = await res.json().catch(() => ({}));
        if (res.ok && data.needsSchedulerOnboarding) {
            openPrefsModal();
        }
    } catch (err) {
        console.warn('Could not check onboarding status:', err);
    }
});
