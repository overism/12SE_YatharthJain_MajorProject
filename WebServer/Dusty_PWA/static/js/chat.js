/* ================================================================
   chat.js  –  Dusty AI Assistant
   Matches chat.html element IDs exactly.
   Fixes: thinking indicator, markdown rendering, quiz display,
          mode switching, composer resize, error handling.
   ================================================================ */

const Chat = {
    mode:           'tutor',
    quiz:           null,
    busy:           false,
    thinkId:        null,
    sessionID:      null,
    sessions:       [],
};

const EL = {};

const HINTS = {
    tutor:    'Tutor mode — scaffolded HSC guidance',
    feedback: 'Feedback mode — band estimate and specific improvements',
    generate: 'Question mode — exam-style question with marking guidelines',
    quiz:     'Quiz mode — answer interactively then submit for marking',
};

const PLACEHOLDERS = {
    tutor:    'Ask Dusty about any HSC topic, concept, or technique…',
    feedback: 'Paste your essay or response here for band feedback…',
    generate: 'Enter a topic or module to generate a practice question…',
    quiz:     'Optionally describe a focus topic, or just click Generate Quiz…',
};

// ── INIT ─────────────────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', () => {
    EL.form         = document.getElementById('chatForm');
    EL.input        = document.getElementById('questionInput');
    EL.messages     = document.getElementById('messages');
    EL.sources      = document.getElementById('sourcesList');
    EL.toast        = document.getElementById('statusToast');
    EL.subject      = document.getElementById('subjectSelect');
    EL.module       = document.getElementById('moduleInput');
    EL.difficulty   = document.getElementById('difficultySelect');
    EL.qCount       = document.getElementById('questionCount');
    EL.sendBtn      = document.getElementById('sendBtn');
    EL.hint         = document.getElementById('composerHint');
    EL.quizArea     = document.getElementById('quizArea');
    EL.kbStatus     = document.getElementById('kbStatus');
    EL.kbText       = document.getElementById('kbStatusText');
    EL.qCountGroup  = document.getElementById('quizCountGroup');
    EL.chatHistory  = document.getElementById('chatHistoryList');
    EL.newChatBtn   = document.getElementById('newChatBtn');

    document.querySelectorAll('.mode-btn').forEach(btn =>
        btn.addEventListener('click', () => setMode(btn.dataset.mode))
    );

    document.querySelectorAll('.quick-prompts button').forEach(btn =>
        btn.addEventListener('click', () => {
            EL.input.value = btn.dataset.prompt || '';
            EL.input.focus();
            resizeTextarea();
        })
    );

    EL.newChatBtn?.addEventListener('click', createNewChat);
    document.getElementById('ingestBtn')?.addEventListener('click', triggerIngest);
    EL.form?.addEventListener('submit', handleSubmit);
    EL.input?.addEventListener('input', resizeTextarea);
    EL.input?.addEventListener('keydown', e => {
        if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); EL.form.requestSubmit(); }
    });

    setMode('tutor');
    checkKB();
    loadChatSessions();
});

// ── MODE ─────────────────────────────────────────────────────────
function setMode(mode) {
    Chat.mode = mode;
    document.querySelectorAll('.mode-btn').forEach(b =>
        b.classList.toggle('active', b.dataset.mode === mode)
    );
    EL.hint.textContent        = HINTS[mode]        || HINTS.tutor;
    EL.input.placeholder       = PLACEHOLDERS[mode] || PLACEHOLDERS.tutor;
    EL.sendBtn.textContent     = mode === 'quiz' ? 'Generate Quiz' : 'Send';
    EL.qCountGroup.style.display = mode === 'quiz' ? '' : 'none';
}

// ── SUBMIT ───────────────────────────────────────────────────────
async function handleSubmit(e) {
    e.preventDefault();
    if (Chat.busy) return;
    if (Chat.mode === 'quiz') { await generateQuiz(); return; }

    const q = EL.input.value.trim();
    if (!q) { showToast('Type a question first.', 'error'); return; }

    addMsg('user', q);
    EL.input.value = ''; resizeTextarea();
    setBusy(true); showThinking();

    try {
        const data = await postJSON('/api/chat', {
            question:   q,
            subject:    EL.subject.value,
            module:     EL.module.value,
            difficulty: EL.difficulty.value,
            mode:       Chat.mode,
        });
        removeThinking();
        addMsg('assistant', data.response || 'No response returned.');
        renderSources(data.sources || [], data.retrieval_error);
    } catch (err) {
        removeThinking();
        addMsg('assistant', '⚠️ ' + err.message);
        showToast(err.message, 'error');
    } finally {
        setBusy(false);
    }
}

// ── QUIZ GENERATE ────────────────────────────────────────────────
async function generateQuiz() {
    setBusy(true);
    EL.quizArea.classList.add('hidden');
    EL.quizArea.innerHTML = '';
    const topic = EL.input.value.trim();
    EL.input.value = ''; resizeTextarea();
    showThinking();

    try {
        const data = await postJSON('/api/quiz/generate', {
            subject:        EL.subject.value,
            module:         EL.module.value || topic || 'General',
            difficulty:     EL.difficulty.value,
            question_count: parseInt(EL.qCount.value) || 5,
        });
        removeThinking();
        Chat.quiz = data.quiz;
        renderQuiz(data.quiz);
        renderSources(data.sources || [], data.retrieval_error);
        addMsg('assistant', `I've generated "${data.quiz?.title || 'your quiz'}" — ${data.quiz?.questions?.length || 0} question(s) below. Answer each one then hit Submit.`);
    } catch (err) {
        removeThinking();
        addMsg('assistant', '⚠️ ' + err.message);
        showToast(err.message, 'error');
    } finally {
        setBusy(false);
    }
}

// ── QUIZ RENDER ──────────────────────────────────────────────────
function renderQuiz(quiz) {
    if (!quiz?.questions?.length) { showToast('Quiz data was not in the expected format.', 'error'); return; }

    const html = quiz.questions.map((q, i) => {
        const id    = escH(q.id || `q${i+1}`);
        const marks = escH(String(q.marks || 1));
        const text  = escH(q.question || '');
        const label = marks === '1' ? '1 mark' : `${marks} marks`;

        if (q.type === 'multiple_choice' && Array.isArray(q.options)) {
            const opts = q.options.map(o => `
                <label><input type="radio" name="${id}" value="${escH(o)}"><span>${escH(o)}</span></label>
            `).join('');
            return `<div class="quiz-question" data-id="${id}" data-type="multiple_choice">
                <p>${i+1}. ${text} <span>(${label})</span></p>
                <div class="quiz-options">${opts}</div></div>`;
        }
        return `<div class="quiz-question" data-id="${id}" data-type="short_answer">
            <p>${i+1}. ${text} <span>(${label})</span></p>
            <textarea class="quiz-answer" rows="3" placeholder="Type your answer…"></textarea></div>`;
    }).join('');

    EL.quizArea.innerHTML = `
        <h2 class="quiz-title">${escH(quiz.title || 'HSC Practice Quiz')}</h2>
        ${html}
        <div class="quiz-actions">
            <button class="btn btn-primary" id="submitQuizBtn" type="button">Submit Answers</button>
        </div>
        <div class="quiz-result" id="quizResult"></div>`;
    EL.quizArea.classList.remove('hidden');
    document.getElementById('submitQuizBtn')?.addEventListener('click', submitQuiz);
    EL.quizArea.scrollIntoView({ behavior:'smooth', block:'nearest' });
}

// ── QUIZ SUBMIT ──────────────────────────────────────────────────
async function submitQuiz() {
    if (!Chat.quiz || Chat.busy) return;
    const answers = {};
    EL.quizArea.querySelectorAll('.quiz-question').forEach(el => {
        const id = el.dataset.id;
        answers[id] = el.dataset.type === 'multiple_choice'
            ? (el.querySelector('input[type="radio"]:checked')?.value || '')
            : (el.querySelector('textarea')?.value.trim() || '');
    });
    if (!Object.values(answers).some(Boolean)) { showToast('Answer at least one question.', 'error'); return; }

    const btn = document.getElementById('submitQuizBtn');
    if (btn) { btn.disabled = true; btn.textContent = 'Marking…'; }
    setBusy(true);

    try {
        const data = await postJSON('/api/quiz/mark', { quiz: Chat.quiz, answers });
        renderQuizResult(data.result);
        renderSources(data.sources || [], data.retrieval_error);
    } catch (err) {
        showToast(err.message, 'error');
        if (btn) { btn.disabled = false; btn.textContent = 'Submit Answers'; }
    } finally {
        setBusy(false);
    }
}

// ── QUIZ RESULT ──────────────────────────────────────────────────
function renderQuizResult(result) {
    const el = document.getElementById('quizResult');
    if (!el || !result) return;
    const score = result.score ?? 0, total = result.total ?? 0;
    const pct = total ? Math.round(score/total*100) : 0;

    const feedback = (result.feedback || []).map(f => `
        <div class="quiz-feedback-item">
            <strong>${escH(f.id||'')}: ${escH(String(f.awarded??0))}/${escH(String(f.marks??0))} mark${f.marks===1?'':'s'}</strong>
            <p>${escH(f.comment||'')}</p>
            ${f.correct_answer ? `<p><strong>Answer:</strong> ${escH(f.correct_answer)}</p>` : ''}
        </div>`).join('');

    const steps = (result.next_steps||[]).length
        ? `<ul style="margin:8px 0 0 18px;color:#555;font-size:13.5px">${(result.next_steps).map(s=>`<li>${escH(s)}</li>`).join('')}</ul>`
        : '';

    el.innerHTML = `
        <div class="score-badge">🏆 ${score}/${total} · ${pct}%</div>
        ${result.summary ? `<p style="font-size:14px;color:#555;margin-top:8px">${escH(result.summary)}</p>` : ''}
        ${feedback}${steps}`;

    const btn = document.getElementById('submitQuizBtn');
    if (btn) { btn.disabled = true; btn.textContent = '✓ Submitted'; }
}

// ── MESSAGES ─────────────────────────────────────────────────────
function addMsg(role, text) {
    const art = document.createElement('article');
    art.className = `message ${role}`;

    const av = document.createElement('div');
    av.className = 'msg-av';
    av.textContent = role === 'user' ? 'Y' : 'D';

    const bub = document.createElement('div');
    bub.className = 'msg-bubble';
    bub.innerHTML = renderMD(text);

    art.appendChild(av); art.appendChild(bub);
    EL.messages.appendChild(art);
    EL.messages.scrollTop = EL.messages.scrollHeight;
}

function showThinking() {
    Chat.thinkId = 'think-' + Date.now();
    const art = document.createElement('article');
    art.className = 'message thinking'; art.id = Chat.thinkId;

    const av = document.createElement('div');
    av.className = 'msg-av'; av.textContent = 'D';

    const bub = document.createElement('div');
    bub.className = 'msg-bubble';
    bub.innerHTML = `<span style="color:#aaa;font-size:13px">Thinking</span><span class="thinking-dots"><span></span><span></span><span></span></span>`;

    art.appendChild(av); art.appendChild(bub);
    EL.messages.appendChild(art);
    EL.messages.scrollTop = EL.messages.scrollHeight;
}

function removeThinking() {
    if (Chat.thinkId) { document.getElementById(Chat.thinkId)?.remove(); Chat.thinkId = null; }
}

// ── MARKDOWN RENDERER ────────────────────────────────────────────
// Safe: escapes first, then applies patterns on safe text
function renderMD(raw) {
    if (!raw) return '<p>No response.</p>';
    let s = escH(raw);

    // Headings
    s = s.replace(/^###\s+(.+)$/gm, '<h3>$1</h3>');
    s = s.replace(/^##\s+(.+)$/gm,  '<h3>$1</h3>');
    // Bold / italic / code
    s = s.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>');
    s = s.replace(/\*(.+?)\*/g,     '<em>$1</em>');
    s = s.replace(/`([^`]+)`/g,     '<code>$1</code>');

    // Block split
    const blocks = s.split(/\n{2,}/);
    return blocks.map(b => {
        b = b.trim();
        if (!b) return '';
        if (b.startsWith('<h3>')) return b;
        const lines = b.split('\n').map(l => l.trim()).filter(Boolean);
        if (lines.every(l => /^[-*•]\s/.test(l)))
            return `<ul>${lines.map(l=>`<li>${l.replace(/^[-*•]\s/,'')}</li>`).join('')}</ul>`;
        if (lines.every(l => /^\d+\.\s/.test(l)))
            return `<ol>${lines.map(l=>`<li>${l.replace(/^\d+\.\s/,'')}</li>`).join('')}</ol>`;
        return `<p>${lines.join('<br>')}</p>`;
    }).join('') || '<p>No response.</p>';
}

// ── SOURCES ──────────────────────────────────────────────────────
function renderSources(sources, retriErr) {
    if (!sources?.length) {
        EL.sources.innerHTML = retriErr
            ? `<p class="sources-empty" style="color:#b45309">⚠️ ${escH(retriErr)}</p>`
            : '<p class="sources-empty">Retrieved citations appear here after each response.</p>';
        return;
    }
    EL.sources.innerHTML = sources.map(s => {
        const pct = s.relevance ? Math.round(s.relevance * 100) : null;
        return `<div class="source-item">
            <span class="source-title">${escH(s.label || s.source || 'Source')}</span>
            <div class="source-meta">
                ${s.subject ? `<strong>${escH(s.subject)}</strong>` : ''}
                ${s.module && s.module !== 'General' ? ` · ${escH(s.module)}` : ''}
                ${s.source_type ? `<br>${escH(s.source_type)}` : ''}
            </div>
            ${pct !== null ? `<span class="source-relevance">${pct}% match</span>` : ''}
        </div>`;
    }).join('');
}

// ── CLEAR ────────────────────────────────────────────────────────
async function clearChat() {
    try {
        await postJSON('/api/clear', {});
    } catch { /* ignore */ }
    EL.messages.innerHTML = '';
    EL.quizArea.classList.add('hidden');
    EL.quizArea.innerHTML = '';
    Chat.quiz = null;
    renderSources([], null);
    addMsg('assistant', 'Chat cleared. What would you like to study next?');
}

// ── INGEST ───────────────────────────────────────────────────────
async function triggerIngest() {
    const btn = document.getElementById('ingestBtn');
    if (btn) { btn.disabled = true; btn.textContent = '⟳ Building…'; }
    try {
        const data = await postJSON('/api/ingest', {});
        showToast(data.status || 'Ingestion started.', 'info');
        setTimeout(checkKB, 5000);
    } catch (err) {
        showToast(err.message, 'error');
    } finally {
        setTimeout(() => { if(btn){ btn.disabled=false; btn.textContent='⟳ Rebuild KB'; } }, 3000);
    }
}

// ── KB STATUS ────────────────────────────────────────────────────
async function checkKB() {
    try {
        const res  = await fetch('/api/status');
        const data = await res.json();
        if (!res.ok) throw new Error(data.error || 'Status check failed');
        const n = data.chunks_in_database || 0;
        EL.kbStatus.classList.toggle('ready', n > 0);
        EL.kbStatus.classList.remove('error');
        EL.kbText.textContent = n > 0
            ? `${n.toLocaleString()} chunks indexed`
            : 'No chunks — click Rebuild KB';
    } catch {
        EL.kbStatus.classList.add('error');
        EL.kbStatus.classList.remove('ready');
        EL.kbText.textContent = 'KB unavailable';
    }
}

// ── UTILITIES ────────────────────────────────────────────────────
async function postJSON(url, body) {
    const res  = await fetch(url, {
        method:'POST',
        headers:{'Content-Type':'application/json'},
        body:JSON.stringify(body),
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(data.error || `Request failed (${res.status})`);
    return data;
}

function setBusy(v) {
    Chat.busy = v;
    document.querySelector('.chat-main')?.classList.toggle('loading', v);
    if (EL.sendBtn) {
        EL.sendBtn.disabled = v;
        EL.sendBtn.textContent = v ? 'Working…' : (Chat.mode === 'quiz' ? 'Generate Quiz' : 'Send');
    }
}

function showToast(msg, type = 'info') {
    if (!EL.toast) return;
    EL.toast.textContent = msg;
    EL.toast.className = `status-toast show ${type}`;
    clearTimeout(EL.toast._t);
    EL.toast._t = setTimeout(() => { EL.toast.className = 'status-toast'; }, 4000);
}

function resizeTextarea() {
    if (!EL.input) return;
    EL.input.style.height = 'auto';
    EL.input.style.height = Math.min(EL.input.scrollHeight, 200) + 'px';
}

function escH(v) {
    return String(v ?? '')
        .replace(/&/g,'&amp;').replace(/</g,'&lt;')
        .replace(/>/g,'&gt;').replace(/"/g,'&quot;').replace(/'/g,'&#039;');
}

// ── CHAT SESSIONS ────────────────────────────────────────────────
async function loadChatSessions() {
    try {
        const res = await fetch('/api/chat/sessions');
        if (!res.ok) throw new Error('Could not load chat history');
        const data = await res.json();
        Chat.sessions = data.sessions || [];
        renderChatHistory();
    } catch (err) {
        console.log('Could not load chat history:', err.message);
    }
}

function renderChatHistory() {
    if (!EL.chatHistory) return;
    
    if (!Chat.sessions || Chat.sessions.length === 0) {
        EL.chatHistory.innerHTML = '<p class="chat-history-empty">No chats yet. Start a new conversation!</p>';
        return;
    }

    const html = Chat.sessions.map(sess => `
        <div class="chat-history-item ${sess.sessionID === Chat.sessionID ? 'active' : ''}" data-session-id="${sess.sessionID}">
            <span class="chat-item-title">${escH(sess.title)}</span>
            <span class="chat-history-item-close" onclick="deleteChatSession(${sess.sessionID}); event.stopPropagation();">×</span>
        </div>
    `).join('');
    
    EL.chatHistory.innerHTML = html;
    
    document.querySelectorAll('.chat-history-item').forEach(item =>
        item.addEventListener('click', () => loadChat(parseInt(item.dataset.sessionId)))
    );
}

async function createNewChat() {
    try {
        const subject = (EL.subject?.value || 'General').trim();
        const module = (EL.module?.value || 'General').trim();
        
        const data = await postJSON('/api/chat/session', {
            title: `${subject} - ${new Date().toLocaleDateString()}`,
            subject: subject,
            module: module,
        });
        
        Chat.sessionID = data.sessionID;
        EL.messages.innerHTML = '';
        EL.quizArea.classList.add('hidden');
        EL.quizArea.innerHTML = '';
        Chat.quiz = null;
        renderSources([], null);
        addMsg('assistant', 'New chat started. What would you like to study?');
        
        await loadChatSessions();
        showToast('New chat created', 'info');
    } catch (err) {
        showToast(err.message, 'error');
    }
}

async function loadChat(sessionID) {
    try {
        const res = await fetch(`/api/chat/session/${sessionID}`);
        if (!res.ok) throw new Error('Could not load chat');
        const data = await res.json();
        
        Chat.sessionID = sessionID;
        EL.messages.innerHTML = '';
        EL.quizArea.classList.add('hidden');
        EL.quizArea.innerHTML = '';
        Chat.quiz = null;
        
        // Render all messages
        (data.messages || []).forEach(msg => {
            if (msg.role === 'user') {
                addMsg('user', msg.content);
            } else {
                addMsg('assistant', msg.content);
            }
        });
        
        renderSources([], null);
        renderChatHistory();
    } catch (err) {
        showToast(err.message, 'error');
    }
}

async function deleteChatSession(sessionID) {
    if (!confirm('Delete this chat? This cannot be undone.')) return;
    
    try {
        const res = await fetch(`/api/chat/session/${sessionID}`, { method: 'DELETE' });
        if (!res.ok) throw new Error('Failed to delete');
        
        Chat.sessions = Chat.sessions.filter(s => s.sessionID !== sessionID);
        renderChatHistory();
        
        if (Chat.sessionID === sessionID) {
            await createNewChat();
        }
        showToast('Chat deleted', 'info');
    } catch (err) {
        showToast('Could not delete chat', 'error');
    }
}