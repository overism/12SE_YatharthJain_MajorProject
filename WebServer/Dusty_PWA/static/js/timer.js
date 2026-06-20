/* ================================================================
   timer.js  –  Dusty Ambient Study Timer
   Preserves ALL existing DustyStudyTimer logic (presets, sessions,
   subject selection, popout widget).
   Adds: ambience dock, background picker, ambient sound mixer,
         per-user upload support, localStorage persistence.
================================================================ */

'use strict';

// ── STATE ─────────────────────────────────────────────────────────
let timerState = {
    subjects: [],
    presets:  []
};

const colorSchemes = window.SUBJECT_COLOURS || window.SUBJECT_COLOR_PALETTE || {
    orange: '#f5761c', blue: '#2563eb', green: '#15803d', red: '#dc2626',
    purple: '#7c3aed', yellow: '#f5c21c', brown: '#92400e', teal: '#0891b2', pink: '#be185d',
};

let editingPresetID      = null;
let pendingStartAfterSubject = false;
let statusTimeout        = null;
const PREF_KEY           = 'dusty.timer.ambience';

// ── PRESET BACKGROUNDS ────────────────────────────────────────────
const BG_PRESETS = [
    { id: 'gradient-amber',  label: 'Amber Dusk',    type: 'gradient', value: 'linear-gradient(135deg,#2b1a0a 0%,#6b3a12 55%,#c2691f 100%)' },
    { id: 'gradient-night',  label: 'Deep Night',    type: 'gradient', value: 'linear-gradient(135deg,#0a0e1a 0%,#1a2340 50%,#0f1628 100%)' },
    { id: 'gradient-forest', label: 'Forest',        type: 'gradient', value: 'linear-gradient(135deg,#0a1a0c 0%,#1a3a1e 50%,#2d5a31 100%)' },
    { id: 'gradient-ocean',  label: 'Deep Ocean',    type: 'gradient', value: 'linear-gradient(135deg,#020c1b 0%,#0d2137 55%,#0a3d62 100%)' },
    { id: 'gradient-purple', label: 'Cosmic',        type: 'gradient', value: 'linear-gradient(135deg,#0d001a 0%,#260040 55%,#3d006b 100%)' },
    { id: 'gradient-rose',   label: 'Rose Dusk',     type: 'gradient', value: 'linear-gradient(135deg,#1a0a0f 0%,#3d1220 50%,#7a1f3a 100%)' },
    // Video presets — drop MP4s at /static/videos/ambience/
    { id: 'video-rain',    label: 'Rainy Window', type: 'video', value: '/static/videos/ambience/rain.mp4' },
    { id: 'video-fire',    label: 'Fireplace',    type: 'video', value: '/static/videos/ambience/fire.mp4' },
    { id: 'video-forest',  label: 'Forest Path',  type: 'video', value: '/static/videos/ambience/forest.mp4' },
    { id: 'video-snow',    label: 'Snowfall',     type: 'video', value: '/static/videos/ambience/snow.mp4' },
    { id: 'video-stars', label: 'Starry Sky', type: 'video', value: '/static/videos/ambience/stars.mp4' },
    { id: 'video-cafe',  label: 'Café',       type: 'video', value: '/static/videos/ambience/cafe.mp4' },
];

// ── PRESET SOUNDS ─────────────────────────────────────────────────
const SOUND_PRESETS = [
    { id: 'rain',     label: 'Rain',           icon: '🌧️', src: '/static/audio/ambience/rain.mp3' },
    { id: 'fire',     label: 'Fireplace',       icon: '🔥', src: '/static/audio/ambience/fire.mp3' },
    { id: 'cafe',     label: 'Café Chatter',    icon: '☕', src: '/static/audio/ambience/cafe.mp3' },
    { id: 'forest',   label: 'Forest Birds',    icon: '🌲', src: '/static/audio/ambience/forest.mp3' },
    { id: 'waves',    label: 'Ocean Waves',     icon: '🌊', src: '/static/audio/ambience/waves.mp3' },
    { id: 'thunder',  label: 'Thunderstorm',    icon: '⛈️', src: '/static/audio/ambience/thunder.mp3' },
    { id: 'keyboard', label: 'Keyboard',        icon: '⌨️', src: '/static/audio/ambience/keyboard.mp3' },
    { id: 'whitenoise',label: 'White Noise',    icon: '📡', src: '/static/audio/ambience/whitenoise.mp3' },
    { id: 'brownoise', label: 'Brown Noise',    icon: '✈️', src: '/static/audio/ambience/brownnoise.mp3' },
    { id: 'lofihip',  label: 'Lo-Fi Hip-Hop',   icon: '🎶', src: '/static/audio/ambience/lofi.mp3' },
];

// Active audio nodes: { [soundId]: { audio: HTMLAudioElement, volume: number, active: bool } }
const soundNodes = {};
// Custom uploads: { backgrounds: [{id, label, type, value}], sounds: [{id, label, src}] }
let customMedia = { backgrounds: [], sounds: [] };

// ── INIT ──────────────────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', () => {
    setupEventListeners();
    loadSubjects();
    loadPresets();
    DustyStudyTimer.subscribe(renderTimerPage);
    loadAmbiencePrefs();
    renderBgPresets();
    renderSoundPresets();
    loadCustomUploads();

    setTimeout(() => {
        document.getElementById('timer-loading')?.classList.add('is-hidden');
    }, 700);
});

// ── CORE TIMER EVENT LISTENERS ────────────────────────────────────
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

    document.querySelectorAll('.quick-preset-btn').forEach(btn =>
        btn.addEventListener('click', e => {
            document.getElementById('presetDuration').value = parseInt(e.currentTarget.dataset.minutes, 10);
        })
    );

    // Dock toggle
    const dockToggleBtn = document.getElementById('dockToggleBtn');
    const ambienceDock  = document.getElementById('ambienceDock');
    dockToggleBtn?.addEventListener('click', () => {
        const isOpen = ambienceDock.classList.toggle('open');
        dockToggleBtn.setAttribute('aria-expanded', String(isOpen));
        ambienceDock.setAttribute('aria-hidden', String(!isOpen));
    });

    // Dock handle drag-to-close
    document.getElementById('dockHandle')?.addEventListener('click', () => {
        document.getElementById('ambienceDock')?.classList.remove('open');
        dockToggleBtn?.setAttribute('aria-expanded', 'false');
    });

    // Dock tab switching
    document.querySelectorAll('.dock-tab').forEach(tab =>
        tab.addEventListener('click', () => switchDockTab(tab.dataset.tab))
    );

    // Background upload
    document.getElementById('bgUploadInput')?.addEventListener('change', e => handleBgUpload(e.target));
    // Sound upload
    document.getElementById('soundUploadInput')?.addEventListener('change', e => handleSoundUpload(e.target));
}

// ── SUBJECTS ──────────────────────────────────────────────────────
async function loadSubjects() {
    try {
        const res = await fetch('/api/subjects');
        const data = await res.json();
        if (!res.ok) throw new Error(data.error || 'Could not load subjects');
        timerState.subjects = data.subjects || [];
        renderSubjectGrid();
    } catch (err) {
        showNotification(err.message, 'error');
    }
}

async function loadPresets() {
    try {
        const res = await fetch('/api/timer/presets');
        const data = await res.json();
        if (!res.ok) throw new Error(data.error || 'Could not load presets');
        timerState.presets = data.presets || [];
        renderPresets();
    } catch (err) {
        showNotification(err.message, 'error');
    }
}

function renderSubjectGrid() {
    const grid = document.getElementById('subjectGrid');
    if (!grid) return;
    grid.innerHTML = '';
    timerState.subjects.forEach(subject => {
        const btn = document.createElement('button');
        btn.type      = 'button';
        btn.className = 'subject-card';
        const color   = window.getSubjectColour
            ? window.getSubjectColour(subject.colourScheme || 'orange')
            : (colorSchemes[subject.colourScheme] || colorSchemes.orange);
        btn.style.setProperty('--subject-color', color);
        btn.innerHTML = `
            <span class="subject-color-indicator"></span>
            <span class="subject-card-name">${escapeHtml(subject.subjectName)}</span>`;
        btn.addEventListener('click', () => chooseSubject(subject));
        grid.appendChild(btn);
    });
}

// ── PRESETS ───────────────────────────────────────────────────────
function renderPresets() {
    const container = document.getElementById('presetsContainer');
    if (!container) return;
    const active = DustyStudyTimer.getState();
    container.innerHTML = '';
    timerState.presets.forEach(preset => {
        const card        = document.createElement('article');
        card.className    = 'preset-btn' + (active.currentPresetID === preset.presetID ? ' active' : '');
        card.tabIndex     = 0;
        card.setAttribute('role', 'button');
        card.innerHTML = `
            <span class="preset-btn-name">${escapeHtml(preset.presetName)}</span>
            <span class="preset-btn-time">${Math.floor(preset.durationSeconds / 60)} min</span>
            <span class="preset-btn-description">${escapeHtml(preset.description || '')}</span>
            <span class="preset-card-actions">
                <button class="preset-edit-btn"   type="button">Edit</button>
                <button class="preset-delete-btn" type="button">Delete</button>
            </span>`;
        card.addEventListener('click', e => { if (!e.target.closest('button')) selectPreset(preset); });
        card.addEventListener('keydown', e => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); selectPreset(preset); } });
        card.querySelector('.preset-edit-btn').addEventListener('click',   () => openPresetModal(preset.presetID));
        card.querySelector('.preset-delete-btn').addEventListener('click', () => deletePresetConfirm(preset.presetID));
        container.appendChild(card);
    });
}

function selectPreset(preset) {
    DustyStudyTimer.setPreset(preset);
    renderPresets();
}

// ── TIMER CONTROLS ────────────────────────────────────────────────
async function handleStart() {
    const state = DustyStudyTimer.getState();
    if (!state.currentSubject) { openSubjectModal(true); return; }
    try { await DustyStudyTimer.startTimer(); } catch (err) { showNotification(err.message, 'error'); }
}

async function chooseSubject(subject) {
    DustyStudyTimer.setSubject(subject);
    closeSubjectModal();
    if (pendingStartAfterSubject) {
        pendingStartAfterSubject = false;
        try { await DustyStudyTimer.startTimer(subject); } catch (err) { showNotification(err.message, 'error'); }
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
        showNotification('Start a session before finishing it', 'error'); return;
    }
    try {
        const done = await DustyStudyTimer.completeTimer('');
        showSessionCompleteModal(done);
    } catch (err) { showNotification(err.message, 'error'); }
}

function openPresetModal(presetID = null) {
    editingPresetID = presetID;
    const preset = timerState.presets.find(p => p.presetID === presetID);
    document.getElementById('modalTitle').textContent         = preset ? 'Edit Preset' : 'Create New Preset';
    document.getElementById('presetName').value               = preset?.presetName || '';
    document.getElementById('presetDuration').value           = preset ? Math.floor(preset.durationSeconds / 60) : '25';
    document.getElementById('presetDescription').value        = preset?.description || '';
    document.getElementById('savePresetBtn').textContent      = preset ? 'Save Preset' : 'Create Preset';
    document.getElementById('deletePresetBtn').classList.toggle('hidden', !preset);
    document.getElementById('presetModal')?.classList.add('active');
}
function closePresetModal() {
    document.getElementById('presetModal')?.classList.remove('active');
    editingPresetID = null;
}

async function savePreset() {
    const name        = document.getElementById('presetName').value.trim();
    const duration    = parseInt(document.getElementById('presetDuration').value, 10);
    const description = document.getElementById('presetDescription').value.trim();
    const wasEditing  = Boolean(editingPresetID);
    if (!name) { showNotification('Please enter a preset name', 'error'); return; }
    if (!Number.isInteger(duration) || duration < 1 || duration > 120) { showNotification('Duration must be between 1 and 120 minutes', 'error'); return; }
    try {
        const res = await fetch('/api/timer/presets', {
            method:  wasEditing ? 'PUT' : 'POST',
            headers: { 'Content-Type': 'application/json' },
            body:    JSON.stringify({ presetID: editingPresetID, presetName: name, durationSeconds: duration * 60, description })
        });
        const data = await res.json().catch(() => ({}));
        if (!res.ok) throw new Error(data.error || 'Could not save preset');
        closePresetModal();
        await loadPresets();
        showNotification(wasEditing ? 'Preset updated' : 'Preset created', 'success');
    } catch (err) { showNotification(err.message, 'error'); }
}

function deletePresetConfirm(presetID) {
    if (confirm('Delete this preset?')) deletePresetFromDB(presetID);
}
async function deletePresetFromDB(presetID) {
    try {
        const res = await fetch('/api/timer/presets', {
            method: 'DELETE', headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ presetID })
        });
        const data = await res.json().catch(() => ({}));
        if (!res.ok) throw new Error(data.error || 'Could not delete preset');
        await loadPresets();
        showNotification('Preset deleted', 'success');
    } catch (err) { showNotification(err.message, 'error'); }
}
async function deletePreset() {
    if (!editingPresetID || !confirm('Delete this preset?')) return;
    await deletePresetFromDB(editingPresetID);
    closePresetModal();
}

// ── TIMER PAGE RENDER (subscribed to DustyStudyTimer) ─────────────
function renderTimerPage(state) {
    document.getElementById('timerDisplay').textContent   = DustyStudyTimer.formatTime(state.remainingSeconds);
    document.getElementById('presetLabel').textContent    = state.currentPresetName || 'Custom Timer';
    document.getElementById('durationValue').textContent  = `${Math.floor(Number(state.totalSeconds || 0) / 60)} min`;
    document.getElementById('statusValue').textContent    = state.isRunning ? 'Running' : state.isPaused ? 'Paused' : 'Ready';
    document.getElementById('subjectBtn').textContent     = state.currentSubjectName || 'Choose subject';
    document.getElementById('popoutBtn').textContent      = state.popout ? 'Hide Widget' : 'Pop Out Timer';

    const finishBtn = document.getElementById('finishSessionBtn');
    finishBtn.disabled = !state.sessionID || Number(state.elapsedSeconds || 0) <= 0 || state.remainingSeconds <= 0;

    document.getElementById('playBtn').classList.toggle('hidden', state.isRunning);
    document.getElementById('pauseBtn').classList.toggle('hidden', !state.isRunning);

    renderPresets();
    if (state.justCompleted) showSessionCompleteModal(state);
}

function showSessionCompleteModal(state) {
    document.getElementById('sessionTimeValue').textContent    = DustyStudyTimer.formatTime(state.elapsedSeconds);
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
    } catch (err) { showNotification(err.message, 'error'); }
}

// ── DOCK TABS ─────────────────────────────────────────────────────
function switchDockTab(tab) {
    document.querySelectorAll('.dock-tab').forEach(t => t.classList.toggle('active', t.dataset.tab === tab));
    document.getElementById('dockPresets').classList.toggle('hidden',     tab !== 'presets');
    document.getElementById('dockBackgrounds').classList.toggle('hidden', tab !== 'backgrounds');
    document.getElementById('dockSounds').classList.toggle('hidden',      tab !== 'sounds');
}

// ── BACKGROUND SYSTEM ─────────────────────────────────────────────
function renderBgPresets() {
    const grid = document.getElementById('bgPresetGrid');
    if (!grid) return;
    grid.innerHTML = '';
    BG_PRESETS.forEach(bg => {
        const prefs = loadAmbiencePrefs();
        const isActive = prefs.bgId === bg.id;
        const card = makeBgCard(bg, isActive);
        grid.appendChild(card);
    });
}

function renderCustomBgs() {
    const grid     = document.getElementById('bgCustomGrid');
    const heading  = document.getElementById('bgCustomHeading');
    if (!grid) return;
    if (!customMedia.backgrounds.length) { grid.innerHTML = ''; heading.style.display = 'none'; return; }
    heading.style.display = '';
    grid.innerHTML = '';
    const prefs = loadAmbiencePrefs();
    customMedia.backgrounds.forEach(bg => {
        const card = makeBgCard(bg, prefs.bgId === bg.id, true);
        grid.appendChild(card);
    });
}

function makeBgCard(bg, isActive, canRemove = false) {
    const card = document.createElement('div');
    card.className = 'ambience-card' + (isActive ? ' active' : '');
    card.title     = bg.label;

    if (bg.type === 'gradient') {
        card.style.background = bg.value;
    } else if (bg.type === 'video') {
        const vid = document.createElement('video');
        vid.src = bg.value; vid.autoplay = true; vid.loop = true; vid.muted = true;
        vid.playsInline = true;
        vid.onerror = () => { card.style.background = 'rgba(255,255,255,.06)'; };
        card.appendChild(vid);
    } else {
        const img = document.createElement('img');
        img.src = bg.value; img.alt = bg.label;
        img.onerror = () => { card.style.background = 'rgba(255,255,255,.06)'; };
        card.appendChild(img);
    }

    const label = document.createElement('div');
    label.className = 'ambience-card-label';
    label.textContent = bg.label;
    card.appendChild(label);

    if (canRemove) {
        const rem = document.createElement('button');
        rem.className = 'ambience-card-remove'; rem.type = 'button'; rem.title = 'Remove'; rem.innerHTML = '×';
        rem.addEventListener('click', e => { e.stopPropagation(); removeCustomBg(bg.id); });
        card.appendChild(rem);
    }

    card.addEventListener('click', () => applyBackground(bg));
    return card;
}

function applyBackground(bg) {
    const video = document.getElementById('ambientVideo');
    const image = document.getElementById('ambientImage');
    const grad  = document.getElementById('ambientGradient');

    [video, image, grad].forEach(el => el.classList.add('hidden'));
    video.src = ''; image.src = '';

    if (bg.type === 'gradient') {
        grad.style.background = bg.value;
        grad.classList.remove('hidden');
    } else if (bg.type === 'video') {
        video.src = bg.value;
        video.classList.remove('hidden');
        video.play().catch(() => {
            grad.classList.remove('hidden'); // fallback
        });
    } else {
        image.src = bg.value;
        image.classList.remove('hidden');
    }

    saveAmbiencePref('bgId', bg.id);
    saveAmbiencePref('bgType', bg.type);
    saveAmbiencePref('bgValue', bg.value);

    // Update active state in grid
    document.querySelectorAll('#bgPresetGrid .ambience-card, #bgCustomGrid .ambience-card').forEach(c =>
        c.classList.remove('active')
    );
    // Find and mark active — just re-render is simpler:
    renderBgPresets();
    renderCustomBgs();
}

async function handleBgUpload(input) {
    const file = input.files[0];
    if (!file) return;
    const maxMB = 40;
    if (file.size > maxMB * 1024 * 1024) { showNotification(`Max ${maxMB} MB for backgrounds`, 'error'); input.value = ''; return; }

    const fd = new FormData();
    fd.append('file', file);
    fd.append('category', 'background');
    try {
        const res  = await fetch('/api/timer/ambience/upload', { method: 'POST', body: fd });
        const data = await res.json();
        if (!res.ok) throw new Error(data.error || 'Upload failed');
        showNotification('Background uploaded!', 'success');
        await loadCustomUploads();
    } catch (err) {
        showNotification(err.message, 'error');
    }
    input.value = '';
}

async function removeCustomBg(id) {
    try {
        const res = await fetch(`/api/timer/ambience/upload?id=${encodeURIComponent(id)}&category=background`, { method: 'DELETE' });
        if (!res.ok) throw new Error('Delete failed');
        customMedia.backgrounds = customMedia.backgrounds.filter(b => b.id !== id);
        renderCustomBgs();
        showNotification('Background removed', 'info');
    } catch (err) { showNotification(err.message, 'error'); }
}

// ── SOUND SYSTEM ──────────────────────────────────────────────────
function renderSoundPresets() {
    const list = document.getElementById('soundPresetList');
    if (!list) return;
    list.innerHTML = '';
    SOUND_PRESETS.forEach(s => list.appendChild(makeSoundItem(s)));
}

function renderCustomSounds() {
    const list    = document.getElementById('soundCustomList');
    const heading = document.getElementById('soundCustomHeading');
    if (!list) return;
    if (!customMedia.sounds.length) { list.innerHTML = ''; heading.style.display = 'none'; return; }
    heading.style.display = '';
    list.innerHTML = '';
    customMedia.sounds.forEach(s => list.appendChild(makeSoundItem(s, true)));
}

function makeSoundItem(s, canRemove = false) {
    const node = soundNodes[s.id] || (soundNodes[s.id] = { audio: null, volume: 0.5, active: false });
    const item = document.createElement('div');
    item.className  = 'sound-item' + (node.active ? ' active' : '');
    item.id         = `sound-item-${s.id}`;

    item.innerHTML = `
        <div class="sound-icon">${s.icon || '🎵'}</div>
        <div class="sound-info"><div class="sound-label">${escapeHtml(s.label)}</div></div>
        <input type="range" class="sound-volume" min="0" max="1" step="0.05" value="${node.volume}" title="Volume">
        <button class="sound-toggle" type="button" aria-label="${node.active ? 'Pause' : 'Play'} ${s.label}">
            ${node.active ? pauseIcon() : playIcon()}
        </button>
        ${canRemove ? `<button class="sound-remove" type="button" title="Remove">X</button>` : ''}`;

    item.querySelector('.sound-toggle').addEventListener('click', () => toggleSound(s));
    item.querySelector('.sound-volume').addEventListener('input', e => setVolume(s.id, parseFloat(e.target.value)));
    if (canRemove) item.querySelector('.sound-remove').addEventListener('click', () => removeCustomSound(s.id));

    return item;
}

function playIcon()  { return '<img src="/static/images/play-icon.svg" alt="Play" width="16" height="16">'; }
function pauseIcon() { return '<img src="/static/images/pause-icon.svg" alt="Pause" width="16" height="16">'; }

function toggleSound(s) {
    const node = soundNodes[s.id];
    if (!node) return;

    if (node.active) {
        node.audio?.pause();
        node.active = false;
    } else {
        if (!node.audio) {
            const a  = new Audio(s.src);
            a.loop   = true;
            a.volume = node.volume;
            node.audio = a;
        }
        node.audio.volume = node.volume;
        node.audio.play().catch(() => showNotification('Could not load audio file', 'error'));
        node.active = true;
    }

    // Update UI for this item
    const item = document.getElementById(`sound-item-${s.id}`);
    if (item) {
        item.classList.toggle('active', node.active);
        const btn = item.querySelector('.sound-toggle');
        if (btn) { btn.innerHTML = node.active ? pauseIcon() : playIcon(); btn.setAttribute('aria-label', (node.active ? 'Pause' : 'Play') + ' ' + s.label); }
    }

    saveActiveSounds();
}

function setVolume(id, vol) {
    const node = soundNodes[id];
    if (!node) return;
    node.volume = vol;
    if (node.audio) node.audio.volume = vol;
    saveActiveSounds();
}

function saveActiveSounds() {
    const active = {};
    Object.entries(soundNodes).forEach(([id, node]) => {
        if (node.active || node.volume !== 0.5) active[id] = { volume: node.volume, active: node.active };
    });
    saveAmbiencePref('sounds', active);
}

function restoreActiveSounds() {
    const prefs  = loadAmbiencePrefs();
    const sounds = prefs.sounds || {};
    Object.entries(sounds).forEach(([id, s]) => {
        if (!soundNodes[id]) soundNodes[id] = { audio: null, volume: 0.5, active: false };
        soundNodes[id].volume = s.volume ?? 0.5;
        if (s.active) {
            // Find the source
            const preset = [...SOUND_PRESETS, ...customMedia.sounds].find(p => p.id === id);
            if (preset) setTimeout(() => toggleSound(preset), 400);
        }
    });
}

async function handleSoundUpload(input) {
    const file = input.files[0];
    if (!file) return;
    const fd = new FormData();
    fd.append('file', file);
    fd.append('category', 'sound');
    try {
        const res  = await fetch('/api/timer/ambience/upload', { method: 'POST', body: fd });
        const data = await res.json();
        if (!res.ok) throw new Error(data.error || 'Upload failed');
        showNotification('Sound uploaded!', 'success');
        await loadCustomUploads();
    } catch (err) { showNotification(err.message, 'error'); }
    input.value = '';
}

async function removeCustomSound(id) {
    if (soundNodes[id]) { soundNodes[id].audio?.pause(); delete soundNodes[id]; }
    try {
        await fetch(`/api/timer/ambience/upload?id=${encodeURIComponent(id)}&category=sound`, { method: 'DELETE' });
        customMedia.sounds = customMedia.sounds.filter(s => s.id !== id);
        renderCustomSounds();
        showNotification('Sound removed', 'info');
    } catch (err) { showNotification(err.message, 'error'); }
}

// ── CUSTOM UPLOADS ────────────────────────────────────────────────
async function loadCustomUploads() {
    try {
        const res  = await fetch('/api/timer/ambience/uploads');
        if (!res.ok) return;
        const data = await res.json();
        customMedia.backgrounds = data.backgrounds || [];
        customMedia.sounds      = data.sounds      || [];
    } catch { /* offline - use cached */ }
    renderCustomBgs();
    renderCustomSounds();
    restoreActiveSounds();
}

// ── AMBIENCE PREF PERSISTENCE ─────────────────────────────────────
function getAmbiencePrefKey() {
    const userId = document.querySelector('meta[name="dusty-uid"]')?.content || '0';
    return `${PREF_KEY}.${userId}`;
}

function loadAmbiencePrefs() {
    try { return JSON.parse(localStorage.getItem(getAmbiencePrefKey()) || '{}'); } catch { return {}; }
}
function saveAmbiencePref(key, value) {
    const prefs = loadAmbiencePrefs();
    prefs[key]  = value;
    try { localStorage.setItem(getAmbiencePrefKey(), JSON.stringify(prefs)); } catch {}
    // Fire-and-forget server sync
    fetch('/api/timer/ambience/prefs', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(prefs)
    }).catch(() => {});
}

function restoreAmbienceFromPrefs() {
    const prefs = loadAmbiencePrefs();
    if (prefs.bgId && prefs.bgType && prefs.bgValue) {
        applyBackground({ id: prefs.bgId, type: prefs.bgType, value: prefs.bgValue, label: '' });
    } else {
        applyBackground(BG_PRESETS[0]);
    }
}

// Restore the user-specific ambience after uploads are loaded and DOM is ready.
(function() {
    setTimeout(restoreAmbienceFromPrefs, 300);
})();

// ── NOTIFICATIONS ─────────────────────────────────────────────────
function showNotification(message, type = 'info') {
    const el = document.getElementById('status');
    if (!el) return;
    if (statusTimeout) clearTimeout(statusTimeout);
    el.textContent = message;
    el.className   = `status show ${type}`;
    statusTimeout  = setTimeout(() => { el.classList.remove('show'); }, type === 'error' ? 6000 : 3000);
}

// ── UTILITIES ─────────────────────────────────────────────────────
function escapeHtml(value) {
    return String(value || '')
        .replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;')
        .replace(/"/g,'&quot;').replace(/'/g,'&#039;');
}