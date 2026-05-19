/* ================================================================
   home.js  –  Dusty Dashboard
   Loaded via <script defer> in home.html.
   Handles: greeting, stats, subjects, tasks, timer widget,
            search, draggable widget layout (SortableJS).
   ================================================================ */

'use strict';

/* ── CONSTANTS ── */
const SUBJECT_COLOURS = window.SUBJECT_COLOURS || {
    orange: '#f5761c', blue: '#2563eb', green: '#15803d',
    red: '#dc2626', purple: '#7c3aed', yellow: '#d97706', amber: '#d97706', brown: '#92400e',
    teal: '#0891b2', pink: '#be185d',
};

const TASK_BG = [
    'rgba(248,165,163,.30)', 'rgba(255,229,153,.30)',
    'rgba(170,230,220,.30)', 'rgba(216,183,234,.30)',
    'rgba(183,220,228,.30)',
];
const TASK_COL = ['#dc2626', '#d97706', '#0891b2', '#7c3aed', '#2563eb'];
const CIRCUMFERENCE = 2 * Math.PI * 58; // SVG arc r=58
const LAYOUT_KEY = 'dusty.dashboard.layout';

/* ── BOOT ── */
document.addEventListener('DOMContentLoaded', () => {
    renderGreeting();
    loadDashboard();
    initSortable();
    renderTimerFromShared();
    initSearch();
});

/* ── GREETING ── */
function renderGreeting() {
    const h = new Date().getHours();
    const msg = h < 12
        ? "Good morning! Let's make today count."
        : h < 17
        ? "Good afternoon! Keep up the momentum."
        : "Good evening! A great time to review.";
    const el = document.getElementById('greetingSub');
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

/* ── FIXED STATS STRIP ── */
function renderStats(prog) {
    const strip = document.getElementById('statsStrip');
    if (!strip) return;

    const tasks = prog.tasks    || {};
    const sess  = prog.sessions || {};
    const stats = tasks.stats   || [];

    const total     = stats.reduce((a, b) => a + Number(b.count || 0), 0);
    const done      = stats.find(s => s.status === 'completed')?.count || 0;
    const hrs       = ((sess.total_time_spent_seconds || 0) / 3600).toFixed(1);
    const streak    = Math.min(sess.completed_sessions || 0, 7);
    const weekGoal  = total > 0
        ? Math.min(Math.round(done / total * 100), 100) + '%'
        : '0%';

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
            <div class="stat-card-val">${weekGoal}</div>
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
    subjectStats.forEach(item => {
        statsByName[item.subjectName] = item;
    });

    el.innerHTML = subjects.map(s => {
        const col = window.getSubjectColour ? window.getSubjectColour(s.colourScheme || 'orange') : (SUBJECT_COLOURS[s.colourScheme] || SUBJECT_COLOURS.orange);
        const stat = statsByName[s.subjectName] || {};
        const count = Number(stat.count || 0);
        const progress = Math.round(Number(stat.avg_progress || 0));
        const summary = count ? `${count} task${count === 1 ? '' : 's'} · ${progress}% avg` : 'No tasks yet';
        return `
            <a class="subject-card" href="/tasks" style="background:${col}">
                ${escH(s.subjectName)}
                <div class="subject-card-sub">${escH(summary)}</div>
            </a>`;
    }).join('');
}

/* ── UPCOMING TASKS (coloured rows) ── */
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
        const col     = TASK_COL[i % TASK_COL.length];
        const bg      = TASK_BG[i % TASK_BG.length];
        const isDone  = Number(t.progress) >= 100;
        const daysStr = days > 0 ? days + 'd' : days === 0 ? 'Today' : 'Overdue';

        return `
            <div class="task-row ${isDone ? 'done' : ''}" style="background:${bg};color:${col}">
                <div class="task-check" onclick="toggleTask(this)">${isDone ? '✓' : ''}</div>
                <span class="task-name" style="color:#22140b">${escH(t.title)}</span>
                <div class="task-days" style="background:${bg};color:${col}">${daysStr}</div>
            </div>`;
    }).join('');
}

/* Toggle task done state (visual only — full edit is in /tasks) */
function toggleTask(btn) {
    const row = btn.closest('.task-row');
    if (!row) return;
    row.classList.toggle('done');
    btn.textContent = row.classList.contains('done') ? '✓' : '';
}

/* ── TIMER WIDGET — reads DustyStudyTimer from dusty.js ── */
function renderTimerFromShared() {
    if (!window.DustyStudyTimer) {
        // dusty.js loads with defer — retry until available
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

/* Called by inline onclick in home.html */
function dashTimerToggle() {
    if (!window.DustyStudyTimer) return;
    const s = DustyStudyTimer.getState();
    if (s.isRunning) DustyStudyTimer.pauseTimer();
    else             DustyStudyTimer.startTimer();
}

function dashTimerReset() {
    if (!window.DustyStudyTimer) return;
    DustyStudyTimer.resetTimer(true);
}

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
    if (typeof Sortable === 'undefined') {
        // SortableJS not yet loaded (edge case) — retry
        setTimeout(initSortable, 200);
        return;
    }

    const rows = ['sortRow0', 'sortRow1', 'sortRow2'];
    rows.forEach(rowId => {
        const el = document.getElementById(rowId);
        if (!el) return;
        Sortable.create(el, {
            animation: 200,
            handle: '.drag-handle',
            ghostClass: 'sortable-ghost',
            chosenClass: 'sortable-chosen',
            onEnd: saveLayout,
        });
    });

    restoreLayout();
}

function saveLayout() {
    const rows = ['sortRow0', 'sortRow1', 'sortRow2'];
    const layout = {};
    rows.forEach(rowId => {
        const row = document.getElementById(rowId);
        if (!row) return;
        layout[rowId] = [...row.children]
            .map(w => w.dataset.widgetId)
            .filter(Boolean);
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
function escH(v) {
    return String(v ?? '')
        .replace(/&/g, '&amp;').replace(/</g, '&lt;')
        .replace(/>/g, '&gt;').replace(/"/g, '&quot;').replace(/'/g, '&#039;');
}
