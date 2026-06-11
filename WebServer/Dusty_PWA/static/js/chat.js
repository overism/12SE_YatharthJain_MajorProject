/* ================================================================
   chat.js  –  Dusty AI Assistant
   Quiz renders as collapsible card inside the message stream.
   File attachment sends alongside the question for extra context.
   ================================================================ */

const Chat = {
    mode:       'tutor',
    quiz:       null,
    activeQuizId: null,
    busy:       false,
    thinkId:    null,
    sessionID:  null,
    sessions:   [],
    user:       { username: '', pfp: '' },
};

const EL = {};
let attachedFile = null;

const HINTS = {
    tutor:    'Tutor mode — scaffolded HSC guidance',
    feedback: 'Feedback mode — band estimate and specific improvements',
    generate: 'Question mode — exam-style question with marking guidelines',
    quiz:     'Quiz mode — generates an interactive quiz in the chat',
};

const PLACEHOLDERS = {
    tutor:    'Ask Dusty about any HSC topic, concept, or technique…',
    feedback: 'Paste your essay or response here for band feedback…',
    generate: 'Enter a topic or module to generate a practice question…',
    quiz:     'Describe a focus topic, or just click Send to generate a quiz…',
};

// ── INIT ─────────────────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', () => {
    const userDataEl = document.getElementById('chatUserData');
    try { Chat.user = JSON.parse(userDataEl?.textContent || '{}') || {}; } catch { Chat.user = {}; }

    EL.form        = document.getElementById('chatForm');
    EL.input       = document.getElementById('questionInput');
    EL.messages    = document.getElementById('messages');
    EL.toast       = document.getElementById('statusToast');
    EL.subject     = document.getElementById('subjectSelect');
    EL.module      = document.getElementById('moduleInput');
    EL.difficulty  = document.getElementById('difficultySelect');
    EL.qCount      = document.getElementById('questionCount');
    EL.sendBtn     = document.getElementById('sendBtn');
    EL.sendLabel   = document.getElementById('sendLabel');
    EL.hint        = document.getElementById('composerHint');
    EL.kbStatus    = document.getElementById('kbStatus');
    EL.kbText      = document.getElementById('kbStatusText');
    EL.qCountGroup = document.getElementById('quizCountGroup');
    EL.chatHistory = document.getElementById('chatHistoryList');
    EL.newChatBtn  = document.getElementById('newChatBtn');
    EL.attachBtn   = document.getElementById('attachBtn');
    EL.fileInput   = document.getElementById('fileInput');
    EL.filePreview = document.getElementById('filePreview');

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
    EL.attachBtn?.addEventListener('click', () => EL.fileInput?.click());
    EL.fileInput?.addEventListener('change', e => handleFileAttach(e.target));

    setMode('tutor');
    checkKB();
    loadChatSessions();
});

// ── MODE ─────────────────────────────────────────────────────────
function setMode(mode) {
    Chat.mode = mode;
    document.querySelectorAll('.mode-btn').forEach(b => {
        const active = b.dataset.mode === mode;
        b.classList.toggle('active', active);
        b.setAttribute('aria-pressed', String(active));
    });
    if (EL.hint)        EL.hint.textContent        = HINTS[mode]        || HINTS.tutor;
    if (EL.input)       EL.input.placeholder       = PLACEHOLDERS[mode] || PLACEHOLDERS.tutor;
    if (EL.sendLabel)   EL.sendLabel.textContent   = mode === 'quiz' ? 'Generate Quiz' : 'Send';
    if (EL.qCountGroup) EL.qCountGroup.style.display = mode === 'quiz' ? '' : 'none';
}

// ── FILE ATTACHMENT ───────────────────────────────────────────────
function handleFileAttach(input) {
    const file = input.files[0];
    if (!file) return;

    const maxSize = 10 * 1024 * 1024; // 10 MB
    if (file.size > maxSize) {
        showToast('File too large — maximum 10 MB.', 'error');
        input.value = ''; return;
    }

    const allowed = ['pdf','docx','doc','pptx','ppt','txt','md','png','jpg','jpeg'];
    const ext = file.name.split('.').pop().toLowerCase();
    if (!allowed.includes(ext)) {
        showToast(`File type .${ext} is not supported.`, 'error');
        input.value = ''; return;
    }

    attachedFile = file;

    if (!EL.filePreview) return;
    EL.filePreview.innerHTML = `
        <div class="file-preview-item">
            <svg class="file-preview-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
                <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/>
                <polyline points="14 2 14 8 20 8"/>
            </svg>
            <span class="file-preview-name">${escH(file.name)}</span>
            <span class="file-preview-size">${fmtBytes(file.size)}</span>
            <button class="file-preview-remove" onclick="removeAttachedFile()" type="button" aria-label="Remove attached file">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>
            </button>
        </div>`;
    EL.filePreview.classList.remove('hidden');
}

function removeAttachedFile() {
    attachedFile = null;
    if (EL.filePreview) { EL.filePreview.innerHTML = ''; EL.filePreview.classList.add('hidden'); }
    if (EL.fileInput)   EL.fileInput.value = '';
}

function fmtBytes(b) {
    if (b < 1024) return b + ' B';
    if (b < 1048576) return (b / 1024).toFixed(1) + ' KB';
    return (b / 1048576).toFixed(1) + ' MB';
}

// ── SUBMIT ───────────────────────────────────────────────────────
async function handleSubmit(e) {
    e.preventDefault();
    if (Chat.busy) return;
    if (Chat.mode === 'quiz') { await generateQuiz(); return; }

    const q = EL.input.value.trim();
    if (!q && !attachedFile) { showToast('Type a question or attach a file.', 'error'); return; }

    addMsg('user', q || `📎 ${attachedFile?.name}`);
    EL.input.value = ''; resizeTextarea();
    setBusy(true); showThinking();

    try {
        let data;

        if (attachedFile) {
            const fd = new FormData();
            fd.append('question', q);
            fd.append('subject',    EL.subject.value);
            fd.append('module',     EL.module.value);
            fd.append('difficulty', EL.difficulty.value);
            fd.append('mode',       Chat.mode);
            fd.append('file',       attachedFile);

            const res  = await fetch('/api/chat', { method: 'POST', body: fd });
            const json = await res.json().catch(() => ({}));
            if (!res.ok) throw new Error(json.error || `Request failed (${res.status})`);
            data = json;
            removeAttachedFile();
        } else {
            data = await postJSON('/api/chat', {
                question: q, subject: EL.subject.value,
                module: EL.module.value, difficulty: EL.difficulty.value,
                mode: Chat.mode,
            });
        }

        removeThinking();
        addMsg('assistant', data.response || 'No response returned.');
        if (data.sessionID) Chat.sessionID = data.sessionID;
        await loadChatSessions();
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
        addMsg('assistant', `Quiz ready: **${data.quiz?.title || 'HSC Practice Quiz'}** — ${data.quiz?.questions?.length || 0} question(s). Use the card below to answer, then hit Submit.`);
        addQuizBubble(data.quiz);
    } catch (err) {
        removeThinking();
        addMsg('assistant', '⚠️ ' + err.message);
        showToast(err.message, 'error');
    } finally {
        setBusy(false);
    }
}

// ── QUIZ BUBBLE ───────────────────────────────────────────────────
function addQuizBubble(quiz) {
    if (!quiz?.questions?.length) {
        showToast('Quiz data was not in the expected format.', 'error'); return;
    }

    const quizId = 'qz-' + Date.now();
    Chat.activeQuizId = quizId;

    const questionsHtml = quiz.questions.map((q, i) => {
        const id    = escH(q.id || `q${i + 1}`);
        const marks = q.marks || 1;

        let inputHtml = '';
        if (q.type === 'multiple_choice' && Array.isArray(q.options)) {
            inputHtml = `<div class="quiz-options">${q.options.map(o =>
                `<label><input type="radio" name="${id}" value="${escH(o)}"><span>${escH(o)}</span></label>`
            ).join('')}</div>`;
        } else {
            inputHtml = `<textarea class="quiz-answer" rows="3" placeholder="Type your answer…" aria-label="Answer for question ${i + 1}"></textarea>`;
        }

        return `<div class="quiz-question" data-id="${id}" data-type="${escH(q.type || 'short_answer')}">
            <p class="quiz-question-text">${escH(q.question || '')} <span class="quiz-question-meta">(${marks} mark${marks !== 1 ? 's' : ''})</span></p>
            ${inputHtml}
        </div>`;
    }).join('');

    const art = document.createElement('article');
    art.className = 'message assistant';
    art.id = quizId;

    art.innerHTML = `
        <div class="msg-av">
            <img src="/static/images/icon-192.png" width="22" height="22" alt="Dusty assistant">
        </div>
        <div class="msg-bubble quiz-msg-bubble">
            <div class="quiz-card-header" onclick="toggleQuizCard('${quizId}')" role="button" tabindex="0" aria-expanded="true" aria-label="Toggle quiz card">
                <div class="quiz-card-header-left">
                    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M9 5H7a2 2 0 0 0-2 2v12a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V7a2 2 0 0 0-2-2h-2"/><rect x="9" y="3" width="6" height="4" rx="1"/><line x1="9" y1="12" x2="15" y2="12"/><line x1="9" y1="16" x2="11" y2="16"/></svg>
                    <span class="quiz-card-title">${escH(quiz.title || 'HSC Practice Quiz')}</span>
                    <span class="quiz-card-badge">${quiz.questions.length} question${quiz.questions.length !== 1 ? 's' : ''}</span>
                </div>
                <button class="quiz-card-chevron" id="${quizId}-chevron" type="button" aria-label="Collapse quiz">
                    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><polyline points="18 15 12 9 6 15"/></svg>
                </button>
            </div>
            <div class="quiz-card-body" id="${quizId}-body">
                ${questionsHtml}
                <div class="quiz-card-actions">
                    <button class="btn btn-primary" onclick="submitQuiz('${quizId}')" type="button">
                        Submit Answers
                    </button>
                </div>
            </div>
        </div>`;

    EL.messages.appendChild(art);
    EL.messages.scrollTop = EL.messages.scrollHeight;

    // Keyboard support for quiz header
    art.querySelector('.quiz-card-header')?.addEventListener('keydown', e => {
        if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); toggleQuizCard(quizId); }
    });
}

function toggleQuizCard(quizId) {
    const body    = document.getElementById(`${quizId}-body`);
    const chevron = document.getElementById(`${quizId}-chevron`);
    const header  = document.querySelector(`#${quizId} .quiz-card-header`);
    if (!body) return;

    const collapsed = body.classList.toggle('collapsed');
    if (chevron) chevron.style.transform = collapsed ? 'rotate(180deg)' : '';
    if (header)  header.setAttribute('aria-expanded', String(!collapsed));
}

// ── QUIZ SUBMIT ───────────────────────────────────────────────────
async function submitQuiz(quizId) {
    if (!Chat.quiz || Chat.busy) return;

    const quizEl = document.getElementById(quizId);
    if (!quizEl) return;

    const answers = {};
    quizEl.querySelectorAll('.quiz-question').forEach(el => {
        const id = el.dataset.id;
        answers[id] = el.dataset.type === 'multiple_choice'
            ? (el.querySelector('input[type="radio"]:checked')?.value || '')
            : (el.querySelector('textarea')?.value.trim() || '');
    });

    if (!Object.values(answers).some(Boolean)) {
        showToast('Answer at least one question before submitting.', 'error'); return;
    }

    // Mark quiz as submitted
    const body    = document.getElementById(`${quizId}-body`);
    const actions = body?.querySelector('.quiz-card-actions');
    if (actions) {
        actions.innerHTML = '<p class="quiz-submitted-note">✓ Answers submitted — marking below</p>';
    }
    toggleQuizCard(quizId); // collapse it

    setBusy(true); showThinking();

    try {
        const data = await postJSON('/api/quiz/mark', { quiz: Chat.quiz, answers });
        removeThinking();
        addQuizResultBubble(data.result);
    } catch (err) {
        removeThinking();
        addMsg('assistant', '⚠️ ' + err.message);
        showToast(err.message, 'error');
    } finally {
        setBusy(false);
    }
}

function addQuizResultBubble(result) {
    if (!result) return;

    const score = result.score ?? 0;
    const total = result.total ?? 0;
    const pct   = total ? Math.round(score / total * 100) : 0;

    const feedbackHtml = (result.feedback || []).map(f => `
        <div class="quiz-fb-item ${f.is_correct ? 'correct' : 'incorrect'}">
            <div class="quiz-fb-header">
                <span class="quiz-fb-icon">${f.is_correct ? '✓' : '✗'}</span>
                <span class="quiz-fb-q">Question ${escH(String(f.id || ''))}</span>
                <span class="quiz-fb-score">${escH(String(f.awarded ?? 0))}/${escH(String(f.marks ?? 1))} mark${(f.marks ?? 1) !== 1 ? 's' : ''}</span>
            </div>
            <p class="quiz-fb-comment">${escH(f.comment || '')}</p>
            ${f.correct_answer ? `<p class="quiz-fb-answer"><strong>Model answer:</strong> ${escH(f.correct_answer)}</p>` : ''}
        </div>`).join('');

    const stepsHtml = (result.next_steps || []).length
        ? `<div class="quiz-next-steps"><strong>Next Steps</strong><ul>${result.next_steps.map(s => `<li>${escH(s)}</li>`).join('')}</ul></div>`
        : '';

    const html = `
        <div class="quiz-result-card">
            <div class="quiz-result-header">
                <div class="quiz-result-score-row">
                    <span class="quiz-score-big">${score}/${total}</span>
                    <span class="quiz-score-pct">${pct}%</span>
                </div>
                ${result.summary ? `<p class="quiz-result-summary">${escH(result.summary)}</p>` : ''}
            </div>
            ${feedbackHtml ? `<div class="quiz-fb-list">${feedbackHtml}</div>` : ''}
            ${stepsHtml}
        </div>`;

    addRawMsg('assistant', html);
}

// ── MESSAGES ─────────────────────────────────────────────────────
function addMsg(role, text) {
    const art = document.createElement('article');
    art.className = `message ${role}`;

    const av  = document.createElement('div');
    av.className = 'msg-av';
    av.innerHTML = role === 'user' ? userAvatarHTML()
        : '<img src="/static/images/icon-192.png" width="22" height="22" alt="Dusty assistant">';

    const bub = document.createElement('div');
    bub.className = 'msg-bubble';
    bub.innerHTML = renderMD(text);

    art.appendChild(av); art.appendChild(bub);
    EL.messages.appendChild(art);
    EL.messages.scrollTop = EL.messages.scrollHeight;
}

function addRawMsg(role, html) {
    const art = document.createElement('article');
    art.className = `message ${role}`;

    const av  = document.createElement('div');
    av.className = 'msg-av';
    av.innerHTML = role === 'user' ? userAvatarHTML()
        : '<img src="/static/images/icon-192.png" width="22" height="22" alt="Dusty assistant">';

    const bub = document.createElement('div');
    bub.className = 'msg-bubble';
    bub.innerHTML = html;

    art.appendChild(av); art.appendChild(bub);
    EL.messages.appendChild(art);
    EL.messages.scrollTop = EL.messages.scrollHeight;
}

function userAvatarHTML() {
    if (Chat.user?.pfp) return `<img src="${escH(Chat.user.pfp)}" width="32" height="32" alt="You" style="border-radius:50%;object-fit:cover;width:100%;height:100%">`;
    return escH((Chat.user?.username || 'Y').trim().charAt(0).toUpperCase() || 'Y');
}

function showThinking() {
    Chat.thinkId = 'think-' + Date.now();
    const art = document.createElement('article');
    art.className = 'message thinking'; art.id = Chat.thinkId;

    const av  = document.createElement('div');
    av.className = 'msg-av';
    av.innerHTML = '<img src="/static/images/icon-192.png" width="22" height="22" alt="Dusty assistant">';

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
function renderMD(raw) {
    if (!raw) return '<p>No response.</p>';
    let s = escH(raw);

    s = s.replace(/^###\s+(.+)$/gm, '<h3>$1</h3>');
    s = s.replace(/^##\s+(.+)$/gm,  '<h2>$1</h2>');
    s = s.replace(/^#\s+(.+)$/gm,   '<h1>$1</h1>');
    s = s.replace(/\*\*\*(.+?)\*\*\*/g, '<strong><em>$1</em></strong>');
    s = s.replace(/\*\*(.+?)\*\*/g,     '<strong>$1</strong>');
    s = s.replace(/\*(.+?)\*/g,         '<em>$1</em>');
    s = s.replace(/`([^`]+)`/g,         '<code>$1</code>');
    s = s.replace(/^---$/gm,            '<hr>');
    s = s.replace(/\[(.+?)\]\{(red|green|blue|orange|purple|yellow|teal|pink)\}/g,
                  '<span class="chat-colour-$2">$1</span>');

    const blocks = s.split(/\n{2,}/);
    return blocks.map(b => {
        b = b.trim();
        if (!b) return '';
        if (b.startsWith('<h') || b.startsWith('<hr')) return b;
        const lines = b.split('\n').map(l => l.trim()).filter(Boolean);
        if (lines.every(l => /^[-*•]\s/.test(l)))
            return `<ul>${lines.map(l => `<li>${l.replace(/^[-*•]\s/, '')}</li>`).join('')}</ul>`;
        if (lines.every(l => /^\d+\.\s/.test(l)))
            return `<ol>${lines.map(l => `<li>${l.replace(/^\d+\.\s/, '')}</li>`).join('')}</ol>`;
        if (lines.every(l => /^>\s/.test(l)))
            return `<blockquote>${lines.map(l => l.replace(/^>\s/, '')).join('<br>')}</blockquote>`;
        return `<p>${lines.join('<br>')}</p>`;
    }).join('') || '<p>No response.</p>';
}

// ── INGEST ───────────────────────────────────────────────────────
async function triggerIngest() {
    const btn = document.getElementById('ingestBtn');
    if (btn) { btn.disabled = true; }
    try {
        const data = await postJSON('/api/ingest', {});
        showToast(data.status || 'Ingestion started.', 'info');
        setTimeout(checkKB, 5000);
    } catch (err) {
        showToast(err.message, 'error');
    } finally {
        setTimeout(() => { if (btn) btn.disabled = false; }, 3000);
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
        EL.kbText.textContent = n > 0 ? `${n.toLocaleString()} chunks` : 'No chunks — Rebuild KB';
    } catch {
        EL.kbStatus?.classList.add('error');
        EL.kbStatus?.classList.remove('ready');
        if (EL.kbText) EL.kbText.textContent = 'KB unavailable';
    }
}

// ── CHAT SESSIONS ────────────────────────────────────────────────
async function loadChatSessions() {
    try {
        const res  = await fetch('/api/chat/sessions');
        if (!res.ok) return;
        const data = await res.json();
        Chat.sessions = data.sessions || [];
        renderChatHistory();
    } catch { /* silent */ }
}

function renderChatHistory() {
    if (!EL.chatHistory) return;
    if (!Chat.sessions.length) {
        EL.chatHistory.innerHTML = '<p class="chat-history-empty">No chats yet. Start a new conversation!</p>';
        return;
    }
    EL.chatHistory.innerHTML = Chat.sessions.map(sess => `
        <div class="chat-history-item ${sess.sessionID === Chat.sessionID ? 'active' : ''}" data-session-id="${sess.sessionID}">
            <span class="chat-item-title">${escH(sess.title || 'Untitled Chat')}</span>
            <span class="chat-item-actions">
                <button class="chat-item-action" title="Rename" onclick="renameChatSession(${sess.sessionID}); event.stopPropagation();" aria-label="Rename chat">✎</button>
                <button class="chat-item-action" title="Delete" onclick="deleteChatSession(${sess.sessionID}); event.stopPropagation();" aria-label="Delete chat">×</button>
            </span>
        </div>`).join('');

    EL.chatHistory.querySelectorAll('.chat-history-item').forEach(item =>
        item.addEventListener('click', () => loadChat(parseInt(item.dataset.sessionId)))
    );
}

async function createNewChat() {
    try {
        const data = await postJSON('/api/chat/session', {
            title: 'Untitled Chat',
            subject: (EL.subject?.value || 'General').trim(),
            module:  (EL.module?.value  || 'General').trim(),
        });
        Chat.sessionID   = data.sessionID;
        Chat.quiz        = null;
        Chat.activeQuizId = null;
        EL.messages.innerHTML = '';
        addMsg('assistant', 'New chat started. What would you like to study?');
        await loadChatSessions();
        showToast('New chat created', 'info');
    } catch (err) {
        showToast(err.message, 'error');
    }
}

async function loadChat(sessionID) {
    try {
        const res  = await fetch(`/api/chat/session/${sessionID}`);
        if (!res.ok) throw new Error('Could not load chat');
        const data = await res.json();
        Chat.sessionID    = sessionID;
        Chat.quiz         = null;
        Chat.activeQuizId = null;
        EL.messages.innerHTML = '';
        (data.messages || []).forEach(msg => addMsg(msg.role, msg.content));
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
        if (Chat.sessionID === sessionID) await createNewChat();
        showToast('Chat deleted', 'info');
    } catch (err) {
        showToast('Could not delete chat', 'error');
    }
}

async function renameChatSession(sessionID) {
    const current  = Chat.sessions.find(s => s.sessionID === sessionID);
    const nextTitle = prompt('Rename chat', current?.title || 'Untitled Chat');
    if (nextTitle === null) return;
    const title = nextTitle.trim();
    if (!title) { showToast('Chat title cannot be empty', 'error'); return; }
    try {
        const res  = await fetch(`/api/chat/session/${sessionID}`, {
            method: 'PATCH',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ title })
        });
        const data = await res.json().catch(() => ({}));
        if (!res.ok) throw new Error(data.error || 'Could not rename chat');
        Chat.sessions = Chat.sessions.map(s => s.sessionID === sessionID ? { ...s, title: data.title } : s);
        renderChatHistory();
        showToast('Chat renamed', 'info');
    } catch (err) {
        showToast(err.message, 'error');
    }
}

// ── UTILITIES ────────────────────────────────────────────────────
async function postJSON(url, body) {
    const res  = await fetch(url, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(data.error || `Request failed (${res.status})`);
    return data;
}

function setBusy(v) {
    Chat.busy = v;
    if (EL.sendBtn) {
        EL.sendBtn.disabled = v;
        if (EL.sendLabel) EL.sendLabel.textContent = v ? '…' : (Chat.mode === 'quiz' ? 'Generate Quiz' : 'Send');
    }
}

function showToast(msg, type = 'info') {
    if (!EL.toast) return;
    EL.toast.textContent = msg;
    EL.toast.className   = `status-toast show ${type}`;
    clearTimeout(EL.toast._t);
    EL.toast._t = setTimeout(() => { EL.toast.className = 'status-toast'; }, 4200);
}

function resizeTextarea() {
    if (!EL.input) return;
    EL.input.style.height = 'auto';
    EL.input.style.height = Math.min(EL.input.scrollHeight, 160) + 'px';
}

function escH(v) {
    return String(v ?? '')
        .replace(/&/g,'&amp;').replace(/</g,'&lt;')
        .replace(/>/g,'&gt;').replace(/"/g,'&quot;').replace(/'/g,'&#039;');
}