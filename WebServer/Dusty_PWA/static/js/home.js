/* ================================================================
   home.js  –  Dusty Dashboard
   Fixes:
   - taskID included in upcoming tasks from /api/progress
   - Subject colours read from colourScheme (consistent with preferences)
   - Task completion writes to DB and fires BroadcastChannel so
     tasks.html / progress.html stay in sync without a reload
   - Subscribes to the same channel so external completions reflect here
   ================================================================ */

'use strict';

/* ── CONSTANTS ── */
const TASK_BG = [
    'rgba(248,165,163,.20)', 'rgba(255,229,153,.20)',
    'rgba(170,230,220,.20)', 'rgba(216,183,234,.20)',
    'rgba(183,220,228,.20)',
];
const TASK_COL = ['#dc2626', '#d97706', '#0891b2', '#7c3aed', '#2563eb'];
const CIRCUMFERENCE = 2 * Math.PI * 58;
const LAYOUT_KEY    = 'dusty.dashboard.layout';

// BroadcastChannel for cross-page task updates
const _taskChannel = typeof BroadcastChannel !== 'undefined'
    ? new BroadcastChannel('dusty_tasks')
    : null;

/* ── BOOT ── */
document.addEventListener('DOMContentLoaded', () => {
    renderGreeting();
    loadDashboard();
    initSortable();
    renderTimerFromShared();
    initSearch();

    // Listen for task completions from other pages (tasks.html, progress.html)
    if (_taskChannel) {
        _taskChannel.onmessage = () => loadDashboard();
    }
});

/* ── GREETING ── */
function renderGreeting() {
    const h   = new Date().getHours();
    const msg = h < 12
        ? "Good morning! Let's make today count."
        : h < 17
        ? "Good afternoon! Keep up the momentum."
        : "Good evening! A great time to review.";
    const el  = document.getElementById('greetingSub');
    if (el) el.textContent = msg;
}

/* ── LOAD DASHBOARD DATA ── */
async function loadDashboard() {
    try {
        const [progRes, subjRes] = await Promise.all([
            fetch('/api/progress'),
            fetch('/api/subjects'),
        ]);

        const prog = progRes.ok ? await progRes.json() : {};
        const subj = subjRes.ok ? await subjRes.json() : {};

        renderStats(prog);
        renderSubjects(subj.subjects || [], prog.tasks?.by_subject || []);
        renderTasks(prog.tasks?.upcoming || []);

    } catch (e) {
        console.error('[Dashboard] Load error:', e);
        renderStats({});
        renderSubjects([], []);
        renderTasks([]);
    }
}

/* ── STATS STRIP ── */
function renderStats(prog) {
    const strip = document.getElementById('statsStrip');
    if (!strip) return;

    const tasks  = prog.tasks    || {};
    const sess   = prog.sessions || {};
    const stats  = tasks.stats   || [];

    const total   = stats.reduce((a, b) => a + Number(b.count || 0), 0);
    const done    = stats.find(s => s.status === 'completed')?.count || 0;
    const hrs     = ((sess.total_time_spent_seconds || 0) / 3600).toFixed(1);
    const streak  = Math.min(sess.completed_sessions || 0, 7);
    const weekPct = total > 0 ? Math.min(Math.round(done / total * 100), 100) + '%' : '0%';

    strip.innerHTML = `
        <div class="stat-card">
            <div class="stat-card-val">${done}</div>
            <div class="stat-card-lbl">Tasks Completed</div>
        </div>
        <div class="stat-card">
            <div class="stat-card-val">${hrs}h</div>
            <div class="stat-card-lbl">Study Hours</div>
        </div>
        <div class="stat-card">
            <div class="stat-card-val">${streak}</div>
            <div class="stat-card-lbl">Current Streak</div>
        </div>
        <div class="stat-card">
            <div class="stat-card-val">${weekPct}</div>
            <div class="stat-card-lbl">Weekly Goal</div>
        </div>
    `;
}

/* ── SUBJECT CARDS ── */
function renderSubjects(subjects, subjectStats = []) {
    const el = document.getElementById('subjectsGrid');
    if (!el) return;

    if (!subjects.length) {
        el.innerHTML = '<p class="empty-msg">No subjects yet — add some in Tasks!</p>';
        return;
    }

    const statsByName = {};
    subjectStats.forEach(item => { statsByName[item.subjectName] = item; });

    el.innerHTML = subjects.map(s => {
        // ── FIX: always derive colour from the user's saved colourScheme ──
        const col      = _subjectColour(s.colourScheme);
        const stat     = statsByName[s.subjectName] || {};
        const count    = Number(stat.count || 0);
        const progress = Math.round(Number(stat.avg_progress || 0));
        const summary  = count
            ? `${count} task${count === 1 ? '' : 's'} · ${progress}% avg`
            : 'No tasks yet';
        return `
            <a class="subject-card" href="/tasks" style="background:${col}">
                ${escH(s.subjectName)}
                <div class="subject-card-sub">${escH(summary)}</div>
            </a>`;
    }).join('');
}

/* ── UPCOMING TASKS ── */
function renderTasks(tasks) {
    const el = document.getElementById('tasksList');
    if (!el) return;

    if (!tasks.length) {
        el.innerHTML = '<p class="empty-msg">No upcoming tasks. <a href="/tasks" style="color:#f5761c;font-weight:600">Add one →</a></p>';
        return;
    }

    const today = new Date();
    el.innerHTML = tasks.slice(0, 5).map((t, i) => {
        const due     = new Date(t.dueDate);
        const days    = Math.ceil((due - today) / 86400000);
        // ── FIX: use subject colour if available, else index fallback ──
        const col     = t.colourScheme ? _subjectColour(t.colourScheme) : TASK_COL[i % TASK_COL.length];
        const bg      = TASK_BG[i % TASK_BG.length];
        const isDone  = Number(t.progress) >= 100;
        const daysStr = days > 0 ? days + 'd' : days === 0 ? 'Today' : 'Overdue';

        return `
            <div class="task-row ${isDone ? 'done' : ''}"
                 style="background:${bg};color:${col}"
                 data-task-id="${t.taskID || ''}">
                <div class="task-check"
                     onclick="toggleTask(this)"
                     title="Mark complete">${isDone ? '✓' : ''}</div>
                <span class="task-name" style="color:#22140b">${escH(t.title)}</span>
                <div class="task-days" style="background:${bg};color:${col}">${daysStr}</div>
            </div>`;
    }).join('');
}

/* ── TASK COMPLETION (writes to DB, notifies other tabs) ── */
async function toggleTask(btn) {
    const row    = btn.closest('.task-row');
    if (!row) return;
    const taskID = row.dataset.taskId;
    const isDone = !row.classList.contains('done');

    // Optimistic UI
    row.classList.toggle('done', isDone);
    btn.textContent = isDone ? '✓' : '';

    if (!taskID) return;

    try {
        const res = await fetch('/update_task', {
            method:  'POST',
            headers: { 'Content-Type': 'application/json' },
            body:    JSON.stringify({
                taskID,
                field: 'status',
                value: isDone ? '100%' : '0%',
            }),
        });
        if (!res.ok) throw new Error('Update failed');

        // Notify tasks.html and progress.html via BroadcastChannel
        if (_taskChannel) {
            _taskChannel.postMessage({ type: 'task_updated', taskID, done: isDone });
        }
    } catch (err) {
        // Revert optimistic UI on failure
        row.classList.toggle('done', !isDone);
        btn.textContent = !isDone ? '✓' : '';
        console.error('[toggleTask]', err);
    }
}

/* ── TIMER WIDGET ── */
function renderTimerFromShared() {
    if (!window.DustyStudyTimer) {
        setTimeout(renderTimerFromShared, 400);
        return;
    }
    DustyStudyTimer.subscribe(state => {
        const display = document.getElementById('dashTimerDisplay');
        const subPill = document.getElementById('dashTimerSubject');
        const playBtn = document.getElementById('dashPlayBtn');
        const arc     = document.getElementById('timerArc');
        if (!display) return;

        display.textContent = DustyStudyTimer.formatTime(state.remainingSeconds);
        if (subPill) subPill.textContent = state.currentSubjectName || 'No subject';
        if (playBtn) playBtn.textContent = state.isRunning ? '⏸' : '▶';

        if (arc) {
            const total = Number(state.totalSeconds) || 3600;
            const pct   = Number(state.remainingSeconds) / total;
            arc.style.strokeDasharray  = CIRCUMFERENCE;
            arc.style.strokeDashoffset = CIRCUMFERENCE * (1 - Math.max(0, Math.min(1, pct)));
        }
    });
}

function dashTimerToggle() {
    if (!window.DustyStudyTimer) return;
    const s = DustyStudyTimer.getState();
    s.isRunning ? DustyStudyTimer.pauseTimer() : DustyStudyTimer.startTimer();
}

function dashTimerReset() {
    if (!window.DustyStudyTimer) return;
    DustyStudyTimer.resetTimer(true);
}

function goToTimer() { window.location.href = '/timer'; }

/* ── SEARCH ── */
function initSearch() {
    const input = document.getElementById('dashSearch');
    if (!input) return;
    input.addEventListener('keydown', e => {
        if (e.key === 'Enter') doSearch();
    });
}

function doSearch() {
    const q = (document.getElementById('dashSearch')?.value || '').trim();
    if (q) window.location.href = '/resources?q=' + encodeURIComponent(q);
}

/* ── WIDGET DRAG-AND-DROP ── */
function initSortable() {
    if (typeof Sortable === 'undefined') { setTimeout(initSortable, 200); return; }
    ['sortRow0', 'sortRow1', 'sortRow2'].forEach(rowId => {
        const el = document.getElementById(rowId);
        if (!el) return;
        Sortable.create(el, {
            animation: 200, handle: '.drag-handle',
            ghostClass: 'sortable-ghost', chosenClass: 'sortable-chosen',
            onEnd: saveLayout,
        });
    });
    restoreLayout();
}

function saveLayout() {
    const layout = {};
    ['sortRow0', 'sortRow1', 'sortRow2'].forEach(rowId => {
        const row = document.getElementById(rowId);
        if (!row) return;
        layout[rowId] = [...row.children].map(w => w.dataset.widgetId).filter(Boolean);
    });
    try { localStorage.setItem(LAYOUT_KEY, JSON.stringify(layout)); } catch {}
}

function restoreLayout() {
    let layout;
    try { layout = JSON.parse(localStorage.getItem(LAYOUT_KEY) || 'null'); } catch { return; }
    if (!layout) return;
    Object.entries(layout).forEach(([rowId, order]) => {
        const row = document.getElementById(rowId);
        if (!row) return;
        order.forEach(widgetId => {
            const el = row.querySelector(`[data-widget-id="${widgetId}"]`);
            if (el) row.appendChild(el);
        });
    });
}

/* ── UTILITIES ── */
function _subjectColour(scheme) {
    if (!scheme) return '#f5761c';
    if (window.getSubjectColour) return window.getSubjectColour(scheme);
    // Fallback map matching subject-colours.js
    const map = {
        orange:'#f5761c', blue:'#2563eb', green:'#15803d',
        red:'#dc2626',    purple:'#7c3aed', yellow:'#d97706',
        amber:'#d97706',  brown:'#92400e',  teal:'#0891b2', pink:'#be185d',
    };
    return map[scheme] || '#f5761c';
}

function escH(v) {
    return String(v ?? '')
        .replace(/&/g,'&amp;').replace(/</g,'&lt;')
        .replace(/>/g,'&gt;').replace(/"/g,'&quot;').replace(/'/g,'&#039;');
}