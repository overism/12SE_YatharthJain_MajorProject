/* ================================================================
   progress.js  –  Dusty Progress Dashboard
   Pulls from /api/progress and /api/timer/sessions
   Renders Chart.js charts consistent with app colour palette
   ================================================================ */

const ORANGE  = '#f5761c';
const RED     = '#ee4319';
const DARK    = 'rgba(43,26,10,0.85)';
// Prefer a shared palette from subject-colours.js, fall back to the built-in palette values.
const SUBJECT_COLOURS = window.SUBJECT_COLOURS || Object.values(window.SUBJECT_COLOR_PALETTE || {
    orange:'#f5761c', blue:'#2563eb', green:'#15803d',
    red:'#ee4319', purple:'#7c3aed', yellow:'#d97706',
    brown:'#92400e', teal:'#0891b2', pink:'#be185d',
});
// Expose both names so other scripts can rely on either `SUBJ_COLOURS` or `SUBJECT_COLOURS`.
window.SUBJ_COLOURS = window.SUBJ_COLOURS || SUBJECT_COLOURS;
window.SUBJECT_COLOURS = window.SUBJECT_COLOURS || SUBJECT_COLOURS;

let SUBJECT_NAME_COLOURS = {};

const CHARTS_AVAILABLE = typeof window.Chart !== 'undefined';
if (CHARTS_AVAILABLE) {
    Chart.defaults.font.family = "'Roboto', 'Segoe UI', sans-serif";
    Chart.defaults.color = '#888';
}

function paletteColour(keyOrIndex) {
    if (typeof keyOrIndex === 'string' && window.getSubjectColour) {
        return window.getSubjectColour(keyOrIndex);
    }
    if (Array.isArray(SUBJECT_COLOURS)) {
        return SUBJECT_COLOURS[Number(keyOrIndex || 0) % SUBJECT_COLOURS.length] || ORANGE;
    }
    const values = Object.values(SUBJECT_COLOURS || {});
    return values[Number(keyOrIndex || 0) % values.length] || ORANGE;
}

let charts = {};

document.addEventListener('DOMContentLoaded', loadProgress);

async function loadProgress() {
    try {
        const [progRes, sessRes, subjRes] = await Promise.all([
            fetch('/api/progress'),
            fetch('/api/timer/sessions'),
            fetch('/api/subjects')
        ]);

        const prog = await progRes.json();
        const sessData = await sessRes.json();
        const subjData = await subjRes.json().catch(() => ({}));

        if (!progRes.ok) throw new Error(prog.error || 'Could not load progress');

        if (subjRes.ok && Array.isArray(subjData.subjects)) {
            SUBJECT_NAME_COLOURS = {};
            subjData.subjects.forEach((subject, idx) => {
                const colour = window.getSubjectColour ? window.getSubjectColour(subject.colourScheme || 'orange') : window.SUBJECT_COLOURS?.[subject.colourScheme] || paletteColour(idx);
                SUBJECT_NAME_COLOURS[subject.subjectName] = colour;
            });
        }

        const sessions = sessData.sessions || [];
        renderMetrics(prog, sessions);
        renderTaskStatusChart(prog.tasks?.stats || []);
        renderStudyTimeBySubject(sessions);
        renderSubjectProgressBars(prog.tasks?.by_subject || []);
        renderSessionOutcomesChart(prog.sessions || {});
        renderFlashcardStats(prog.flashcard_stats || []);
        renderTimeBySubject(prog.time_by_subject || []);
        renderWeeklyChart(sessions);
        renderUpcoming(prog.tasks?.upcoming || []);
        renderSessionsTable(sessions.slice(0, 8));
        showStatus('Data loaded.', 'success');
    } catch (e) {
        renderMetrics({ tasks: { stats: [] }, sessions: {} }, []);
        renderSubjectProgressBars([]);
        renderUpcoming([]);
        renderSessionsTable([]);
        showStatus(e.message, 'error');
    }
}

function renderMetrics(prog, sessions) {
    const tasks = prog.tasks || {};
    const s = prog.sessions || {};
    const totalTasks = (tasks.stats || []).reduce((a,b) => a + Number(b.count||0), 0);
    const completed = (tasks.stats || []).find(x => x.status === 'completed')?.count || 0;
    const pct = totalTasks ? Math.round(completed / totalTasks * 100) : 0;
    const hrs = (Number(s.total_time_spent_seconds || 0) / 3600).toFixed(1);
    const completedSess = Number(s.completed_sessions || 0);

    document.getElementById('metricRow').innerHTML = `
        ${metCard('📋', totalTasks, 'Total Tasks', '', '')}
        ${metCard('✅', completed, 'Tasks Completed', pct + '% done', pct >= 50 ? 'change-pos' : 'change-neu')}
        ${metCard('⏱', hrs + 'h', 'Study Time', s.total_sessions + ' sessions', 'change-neu')}
        ${metCard('🏆', completedSess, 'Sessions Done', fmtTime(s.total_time_spent_seconds || 0) + ' tracked', 'change-pos')}
        ${metCard('📚', sessions.length, 'All Sessions', '', '')}
    `;
}

function metCard(icon, val, label, change, changeClass) {
    return `<div class="metric-card">
        <span class="metric-icon">${icon}</span>
        <div class="metric-value">${val}</div>
        <div class="metric-label">${label}</div>
        ${change ? `<span class="metric-change ${changeClass}">${change}</span>` : ''}
    </div>`;
}

function renderTaskStatusChart(stats) {
    destroyChart('chartTaskStatus');
    if (!CHARTS_AVAILABLE) { showEmpty('chartTaskStatus', 'Charts unavailable.'); return; }
    if (!stats.length) { showEmpty('chartTaskStatus'); return; }

    const labels = stats.map(s => capitalise(s.status || 'Unknown'));
    const values = stats.map(s => Number(s.count || 0));
    const colours = ['#00bf63','#f5761c','#ffd359','#ff3131','#2563eb'];

    charts.taskStatus = new Chart(document.getElementById('chartTaskStatus'), {
        type: 'doughnut',
        data: { labels, datasets: [{ data: values, backgroundColor: colours.slice(0, labels.length), borderWidth: 3, borderColor: '#fff', hoverOffset: 8 }] },
        options: {
            responsive: true, maintainAspectRatio: false,
            cutout: '62%',
            plugins: {
                legend: { position: 'bottom', labels: { padding: 16, font: { size: 12, weight: '600' } } },
                tooltip: { callbacks: { label: ctx => ` ${ctx.label}: ${ctx.raw} tasks` } }
            }
        }
    });
}

function renderStudyTimeBySubject(sessions) {
    destroyChart('chartStudyTime');
    if (!CHARTS_AVAILABLE) { showEmpty('chartStudyTime', 'Charts unavailable.'); return; }
    if (!sessions.length) { showEmpty('chartStudyTime'); return; }

    const map = {};
    sessions.forEach(s => {
        const name = s.subjectName || 'Unknown';
        map[name] = (map[name] || 0) + Number(s.timeSpentSeconds || 0);
    });

    const sorted = Object.entries(map).sort((a,b) => b[1]-a[1]).slice(0,7);
    const labels = sorted.map(e => e[0]);
    const values = sorted.map(e => +(e[1]/3600).toFixed(2));
    const total = values.reduce((a,b)=>a+b,0);
    document.getElementById('studyTimeTotal').textContent = `Total: ${total.toFixed(1)}h`;
    const colours = labels.map((name, idx) => SUBJECT_NAME_COLOURS[name] || window.getSubjectColour?.('orange') || paletteColour(idx));

    charts.studyTime = new Chart(document.getElementById('chartStudyTime'), {
        type: 'bar',
        data: {
            labels,
            datasets: [{
                label: 'Hours',
                data: values,
                backgroundColor: colours,
                borderRadius: 8, borderSkipped: false,
            }]
        },
        options: {
            indexAxis: 'y',
            responsive: true, maintainAspectRatio: false,
            plugins: { legend: { display: false } },
            scales: {
                x: { grid: { color: 'rgba(0,0,0,0.05)' }, ticks: { callback: v => v + 'h' } },
                y: { grid: { display: false } }
            }
        }
    });
}

function renderFlashcardStats(stats) {
    destroyChart('chartFlashcards');
    const canvas = document.getElementById('chartFlashcards');
    if (!canvas) return;
    if (!stats.length) { showEmpty('chartFlashcards'); return; }
    if (!CHARTS_AVAILABLE) { showEmpty('chartFlashcards', 'Charts unavailable.'); return; }
 
    const labels   = stats.map(s => escHtml(s.subject));
    const knew     = stats.map(s => Number(s.total_knew   || 0));
    const unsure   = stats.map(s => Number(s.total_unsure || 0));
    const missed   = stats.map(s => Number(s.total_missed || 0));
 
    charts.flashcards = new Chart(canvas, {
        type: 'bar',
        data: {
            labels,
            datasets: [
                { label: 'Knew it',  data: knew,   backgroundColor: '#00bf63', borderRadius: 4 },
                { label: 'Unsure',   data: unsure,  backgroundColor: '#ffd359', borderRadius: 4 },
                { label: 'Missed',   data: missed,  backgroundColor: '#ff3131', borderRadius: 4 },
            ],
        },
        options: {
            responsive: true, maintainAspectRatio: false,
            plugins: {
                legend: { position: 'bottom', labels: { padding: 14, font: { size: 12, weight: '600' } } },
                tooltip: { callbacks: { label: ctx => ` ${ctx.dataset.label}: ${ctx.raw} cards` } },
            },
            scales: {
                x: { stacked: true, grid: { display: false } },
                y: { stacked: true, grid: { color: 'rgba(0,0,0,0.05)' }, ticks: { precision: 0 } },
            },
        },
    });
}
 
// ── TIME ON TASK PER SUBJECT (supplement renderStudyTimeBySubject) ─────────
function renderTimeBySubject(rows) {
    const el = document.getElementById('timeBySubjectList');
    if (!el) return;
    if (!rows.length) { el.innerHTML = '<p class="empty-state" style="padding:16px 0">No study sessions recorded yet.</p>'; return; }
 
    el.innerHTML = rows.map((r, i) => {
        const hrs = (Number(r.total_seconds || 0) / 3600).toFixed(1);
        const col = SUBJECT_NAME_COLOURS[r.subjectName] || window.getSubjectColour?.('orange') || '#f5761c';
        const maxSecs = rows[0].total_seconds || 1;
        const pct = Math.round(Number(r.total_seconds) / maxSecs * 100);
        return `<div class="subject-bar-row">
            <div class="subject-bar-top">
                <span class="subject-bar-name">${r.subjectName}</span>
                <span class="subject-bar-stats">${r.session_count} session${r.session_count !== 1 ? 's' : ''} · ${hrs}h</span>
            </div>
            <div class="subject-bar-track">
                <div class="subject-bar-fill" style="width:${pct}%;background:${col}"></div>
            </div>
        </div>`;
    }).join('');
}

function renderSubjectProgressBars(bySubject) {
    const el = document.getElementById('subjectBars');
    if (!el) return;
    if (!bySubject.length) { el.innerHTML = '<p class="empty-state" style="padding:24px 0">No subject data yet.</p>'; return; }

    el.innerHTML = bySubject.slice(0,8).map((item, i) => {
        const pct = Math.round(Number(item.avg_progress || 0));
        const col = SUBJECT_NAME_COLOURS[item.subjectName] || window.getSubjectColour?.('orange') || paletteColour(i);
        return `<div class="subject-bar-row">
            <div class="subject-bar-top">
                <span class="subject-bar-name">${escHtml(item.subjectName)}</span>
                <span class="subject-bar-stats">${item.count} tasks · ${pct}% avg</span>
            </div>
            <div class="subject-bar-track">
                <div class="subject-bar-fill" style="width:${pct}%;background:${col}"></div>
            </div>
        </div>`;
    }).join('');
}

function renderSessionOutcomesChart(s) {
    destroyChart('chartSessionOutcomes');
    if (!CHARTS_AVAILABLE) { showEmpty('chartSessionOutcomes', 'Charts unavailable.'); return; }
    const completed = Number(s.completed_sessions || 0);
    const paused    = Number(s.paused_sessions || 0);
    const abandoned = Number(s.abandoned_sessions || 0);
    if (completed + paused + abandoned === 0) { showEmpty('chartSessionOutcomes'); return; }

    charts.sessionOutcomes = new Chart(document.getElementById('chartSessionOutcomes'), {
        type: 'pie',
        data: {
            labels: ['Completed','Paused','Abandoned'],
            datasets: [{
                data: [completed, paused, abandoned],
                backgroundColor: ['#00bf63','#ffd359','#ff3131'],
                borderWidth: 3, borderColor: '#fff', hoverOffset: 8
            }]
        },
        options: {
            responsive: true, maintainAspectRatio: false,
            plugins: {
                legend: { position: 'bottom', labels: { padding: 16, font: { size: 12, weight: '600' } } }
            }
        }
    });
}

function renderWeeklyChart(sessions) {
    destroyChart('chartWeekly');
    if (!CHARTS_AVAILABLE) { showEmpty('chartWeekly', 'Charts unavailable.'); return; }
    if (!sessions.length) { showEmpty('chartWeekly'); return; }

    const today = new Date();
    const days = [];
    for (let i = 13; i >= 0; i--) {
        const d = new Date(today);
        d.setDate(today.getDate() - i);
        days.push(d.toISOString().slice(0,10));
    }

    const subjectSet = [...new Set(sessions.map(s => s.subjectName || 'Unknown'))].slice(0,5);
    const datasets = subjectSet.map((subj, idx) => {
        const data = days.map(day => {
            return sessions
                .filter(s => s.subjectName === subj && (s.startTime||'').startsWith(day))
                .reduce((a,s) => a + Number(s.timeSpentSeconds||0), 0) / 3600;
        });
        const colour = SUBJECT_NAME_COLOURS[subj] || window.getSubjectColour?.('orange') || paletteColour(idx);
        return {
            label: subj,
            data: data.map(v => +v.toFixed(2)),
            borderColor: colour,
            backgroundColor: colour + '22',
            fill: true, tension: 0.4,
            pointRadius: 4, pointHoverRadius: 6,
            borderWidth: 2.5,
        };
    });

    const totalData = days.map(day =>
        sessions.filter(s => (s.startTime||'').startsWith(day))
                .reduce((a,s) => a + Number(s.timeSpentSeconds||0), 0) / 3600
    );

    datasets.unshift({
        label: 'Total',
        data: totalData.map(v => +v.toFixed(2)),
        borderColor: ORANGE, backgroundColor: ORANGE + '15',
        fill: true, tension: 0.4, borderWidth: 3,
        pointRadius: 4, pointHoverRadius: 7,
        borderDash: [],
    });

    const labels = days.map(d => {
        const dt = new Date(d + 'T00:00:00');
        return dt.toLocaleDateString('en-AU',{weekday:'short',day:'numeric',month:'short'});
    });

    charts.weekly = new Chart(document.getElementById('chartWeekly'), {
        type: 'line',
        data: { labels, datasets },
        options: {
            responsive: true, maintainAspectRatio: false,
            interaction: { mode: 'index', intersect: false },
            plugins: {
                legend: { position: 'top', labels: { font: { size: 12, weight:'600' }, padding: 16 } },
                tooltip: { callbacks: { label: ctx => ` ${ctx.dataset.label}: ${ctx.raw}h` } }
            },
            scales: {
                x: { grid: { color: 'rgba(0,0,0,0.04)' }, ticks: { maxRotation: 35, font: { size: 11 } } },
                y: { grid: { color: 'rgba(0,0,0,0.05)' }, ticks: { callback: v => v + 'h' }, min: 0 }
            }
        }
    });
}

function renderUpcoming(upcoming) {
    const el = document.getElementById('upcomingList');
    if (!el) return;
    if (!upcoming.length) {
        el.innerHTML = '<div class="empty-state"><div class="icon">✅</div><p>No upcoming tasks.</p></div>';
        return;
    }
    el.innerHTML = upcoming.map(task => {
        const due = new Date(task.dueDate);
        const daysLeft = Math.ceil((due - Date.now()) / 86400000);
        const urgency = daysLeft <= 2 ? 'urgency-red' : daysLeft <= 7 ? 'urgency-yellow' : 'urgency-green';
        const pct = Number(task.progress || 0);
        return `<div class="upcoming-task">
            <span class="task-urgency ${urgency}"></span>
            <div class="task-info">
                <strong>${escHtml(task.title)}</strong>
                <span>Due ${escHtml(task.dueDate)} · ${daysLeft > 0 ? daysLeft + 'd left' : 'Overdue'}</span>
            </div>
            <div class="task-progress-mini">
                <div class="mini-track"><div class="mini-fill" style="width:${pct}%"></div></div>
                <span class="mini-pct">${pct}%</span>
            </div>
        </div>`;
    }).join('');
}

function renderSessionsTable(sessions) {
    const tbody = document.getElementById('sessionsBody');
    if (!tbody) return;
    if (!sessions.length) {
        tbody.innerHTML = '<tr><td colspan="4"><div class="empty-state" style="padding:24px 0">No sessions recorded yet.</div></td></tr>';
        return;
    }
    tbody.innerHTML = sessions.map(s => `
        <tr>
            <td><strong>${escHtml(s.subjectName || '—')}</strong>${s.presetName ? `<br><span style="font-size:11px;color:#bbb">${escHtml(s.presetName)}</span>` : ''}</td>
            <td>${fmtTime(s.durationSeconds || 0)}</td>
            <td>${fmtTime(s.timeSpentSeconds || 0)}</td>
            <td><span class="status-badge badge-${s.status || 'in_progress'}">${capitalise(s.status || 'unknown')}</span></td>
        </tr>
    `).join('');
}

function destroyChart(id) {
    if (charts[id]) { charts[id].destroy(); delete charts[id]; }
}

function showEmpty(id) {
    const canvas = document.getElementById(id);
    if (!canvas) return;
    const parent = canvas.parentElement;
    canvas.style.display = 'none';
    const p = document.createElement('div');
    p.className = 'empty-state'; p.style.paddingTop = '40px';
    p.innerHTML = '<div class="icon" style="font-size:28px">📊</div><p>Not enough data yet.</p>';
    parent.appendChild(p);
}

function fmtTime(secs) {
    const s = Math.max(0, Number(secs || 0));
    const h = Math.floor(s / 3600);
    const m = Math.round((s % 3600) / 60);
    return h > 0 ? `${h}h ${m}m` : `${m}m`;
}

function capitalise(s) { return String(s).charAt(0).toUpperCase() + String(s).slice(1); }

function escHtml(v) {
    return String(v||'').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
}

function showStatus(msg, type='info') {
    const el = document.getElementById('pgStatus');
    if (!el) return;
    el.textContent = msg; el.className = `status show ${type}`;
    clearTimeout(el._t);
    el._t = setTimeout(() => { el.className = 'status'; }, 4200);
}
