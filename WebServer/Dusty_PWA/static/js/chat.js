/* ================================================================
   chat.js  –  Dusty AI Assistant
   Fix: PLACEHOLDERS constant added so setMode() never throws,
        which also fixes history not loading on page reload.
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

// ── WELCOME SCREEN ────────────────────────────────────────────────
function showWelcome() {
    document.getElementById('chatWelcome')?.classList.remove('hidden');
    EL.messages?.classList.add('welcome-active');
}

function hideWelcome() {
    document.getElementById('chatWelcome')?.classList.add('hidden');
    EL.messages?.classList.remove('welcome-active');
}

function insertWelcomePrompt(text) {
    hideWelcome();
    if (EL.input) {
        EL.input.value = text;
        resizeTextarea();
        EL.input.focus();
    }
}

// ── CONSTANTS ────────────────────────────────────────────────────
const PLACEHOLDERS = {
    tutor:    'Ask Dusty about any HSC topic…',
    feedback: 'Paste your response here for band feedback…',
    generate: 'Describe the type of question you want…',
    quiz:     'Quiz mode — use the Generate button above',
};

const HINTS = {
    tutor:    'General mode — scaffolded HSC guidance',
    feedback: 'Feedback mode — paste a response for a band estimate',
    generate: 'Practice Question mode — generates one exam-style question',
};

// Human-readable labels shown in the mode button
const MODE_LABELS = {
    tutor:    'General',
    feedback: 'Feedback',
    generate: 'Practice Question',
};

// ── INIT ─────────────────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', async () => {
    const loadingScreen = document.getElementById('chat-loading');
    if (loadingScreen) {
        loadingScreen.classList.remove('is-hidden');
    }
    const userDataEl = document.getElementById('chatUserData');
    try { Chat.user = JSON.parse(userDataEl?.textContent || '{}') || {}; } catch { Chat.user = {}; }

    EL.form        = document.getElementById('chatForm');
    EL.input       = document.getElementById('questionInput');
    EL.messages    = document.getElementById('messages');
    EL.toast       = document.getElementById('statusToast');
    EL.sendBtn     = document.getElementById('sendBtn');
    EL.sendLabel   = document.getElementById('sendLabel');
    EL.hint        = document.getElementById('composerHint');
    EL.chatHistory = document.getElementById('chatHistoryList');
    EL.newChatBtn  = document.getElementById('newChatBtn');
    EL.attachBtn   = document.getElementById('attachBtn');
    EL.fileInput   = document.getElementById('fileInput');
    EL.filePreview = document.getElementById('filePreview');
    EL.modeBtn      = document.getElementById('modeBtn');
    EL.modeBtnLabel = document.getElementById('modeBtnLabel');
    EL.modePopover  = document.getElementById('modePopover');

    EL.modeBtn?.addEventListener('click', toggleModePopover);
    document.addEventListener('click', e => {
        if (!EL.modePopover?.classList.contains('hidden') &&
            !EL.modePopover.contains(e.target) && e.target !== EL.modeBtn) {
            EL.modePopover.classList.add('hidden');
            EL.modeBtn.setAttribute('aria-expanded', 'false');
        }
    });
    document.querySelectorAll('.mode-popover-item').forEach(btn =>
        btn.addEventListener('click', () => handleModePopoverClick(btn))
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

    // Initialise mode (PLACEHOLDERS is now defined so this never throws)
    setMode('tutor');
    checkKB();
    await loadChatSessions();
    showWelcome();
    await createNewChat();

    setTimeout(() => {
        const loadingScreen = document.getElementById('chat-loading');
        if (loadingScreen) {
            loadingScreen.classList.add('is-hidden');
        }
    }, 500);
});

// ── MODE ─────────────────────────────────────────────────────────
function setMode(mode) {
    Chat.mode    = mode;
    Chat.subject = 'General';
    Chat.module  = 'General';
    if (EL.input)       EL.input.placeholder = PLACEHOLDERS[mode] || PLACEHOLDERS.tutor;
    if (EL.hint)        EL.hint.textContent  = HINTS[mode]        || HINTS.tutor;
    if (EL.modeBtnLabel) EL.modeBtnLabel.textContent = MODE_LABELS[mode] || 'General';
}

function toggleModePopover() {
    const hidden = EL.modePopover.classList.toggle('hidden');
    EL.modeBtn.setAttribute('aria-expanded', String(!hidden));
}

function handleModePopoverClick(btn) {
    // Quiz: open the modal — everything else just sets Chat.mode
    if (btn.dataset.action === 'quiz') {
        EL.modePopover.classList.add('hidden');
        EL.modeBtn.setAttribute('aria-expanded', 'false');
        openQuizModal();
        return;
    }

    const mode = btn.dataset.mode;
    if (!mode) return;

    // Update active highlight in popover
    document.querySelectorAll('.mode-popover-item').forEach(b => b.classList.remove('active'));
    btn.classList.add('active');

    // Apply mode (updates input placeholder, hint text, AND button label)
    setMode(mode);

    // Close popover
    EL.modePopover.classList.add('hidden');
    EL.modeBtn.setAttribute('aria-expanded', 'false');
}

// ── FILE ATTACHMENT ───────────────────────────────────────────────
function handleFileAttach(input) {
    const file = input.files[0];
    if (!file) return;

    const maxSize = 10 * 1024 * 1024;
    if (file.size > maxSize) { showToast('File too large — maximum 10 MB.', 'error'); input.value = ''; return; }

    const allowed = ['pdf','docx','doc','pptx','ppt','txt','md','png','jpg','jpeg'];
    const ext = file.name.split('.').pop().toLowerCase();
    if (!allowed.includes(ext)) { showToast(`File type .${ext} is not supported.`, 'error'); input.value = ''; return; }

    attachedFile = file;

    if (!EL.filePreview) return;
    EL.filePreview.innerHTML = `
        <div class="file-preview-item">
            <img src="/static/images/file-icon.svg" class="file-preview-icon" alt="File">
            <span class="file-preview-name">${escH(file.name)}</span>
            <span class="file-preview-size">${fmtBytes(file.size)}</span>
            <button class="file-preview-remove" onclick="removeAttachedFile()" type="button" aria-label="Remove attached file">
                <img src="/static/images/cross-brown-icon.svg" alt="Remove" class="btn-icon-sm">
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
 
    const q = EL.input.value.trim();
    if (!q && !attachedFile) { showToast('Type a question or attach a file.', 'error'); return; }
 
    addMsg('user', q || `📎 ${attachedFile?.name}`);
    EL.input.value = ''; resizeTextarea();
    setBusy(true); showThinking();
 
    try {
        let data;
        const subject    = Chat.subject    || 'General';
        const module     = Chat.module     || 'General';
        const difficulty = Chat.difficulty || 'medium';
        // ── FIX: always include the current sessionID ──
        const sessionID  = Chat.sessionID  || null;
 
        if (attachedFile) {
            const fd = new FormData();
            fd.append('question',   q);
            fd.append('subject',    subject);
            fd.append('module',     module);
            fd.append('difficulty', difficulty);
            fd.append('mode',       Chat.mode);
            fd.append('file',       attachedFile);
            if (sessionID) fd.append('sessionID', sessionID);
 
            const res  = await fetch('/api/chat', { method: 'POST', body: fd });
            const json = await res.json().catch(() => ({}));
            if (!res.ok) throw new Error(json.error || `Request failed (${res.status})`);
            data = json;
            removeAttachedFile();
        } else {
            data = await postJSON('/api/chat', {
                question: q, subject, module, difficulty,
                mode: Chat.mode,
                sessionID,   // ← new field — backend uses this, not the cookie
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

// ── QUIZ GENERATOR MODAL ──────────────────────────────────────────
const QuizModal = { subjects: [], modules: [] };

async function openQuizModal() {
    const modal = document.getElementById('quizGenModal');
    modal.classList.remove('hidden');

    const subjSelect = document.getElementById('quizSubjectSelect');
    if (!QuizModal.subjects.length) {
        try {
            const res  = await fetch('/api/subjects');
            const data = await res.json();
            QuizModal.subjects = (data.subjects || []).map(s => s.subjectName);
        } catch { QuizModal.subjects = []; }
    }

    subjSelect.innerHTML = QuizModal.subjects.length
        ? QuizModal.subjects.map(s => `<option value="${escH(s)}">${escH(s)}</option>`).join('')
        : '<option value="General">General</option>';

    subjSelect.onchange = () => loadQuizModules(subjSelect.value);
    await loadQuizModules(subjSelect.value);
}

async function loadQuizModules(subject) {
    const moduleSelect = document.getElementById('quizModuleSelect');
    const topicSelect  = document.getElementById('quizTopicSelect');

    try {
        const res  = await fetch(`/api/syllabus/topics?subject=${encodeURIComponent(subject)}`);
        const data = await res.json();
        QuizModal.modules = data.modules || [];
    } catch { QuizModal.modules = []; }

    if (!QuizModal.modules.length) {
        moduleSelect.innerHTML = '<option value="Custom Topic">Custom Topic</option>';
        topicSelect.innerHTML  = '<option value="">Describe in chat instead</option>';
        return;
    }

    moduleSelect.innerHTML = QuizModal.modules.map((m, i) => `<option value="${i}">${escH(m.module)}</option>`).join('');
    moduleSelect.onchange  = () => loadQuizTopics(Number(moduleSelect.value));
    loadQuizTopics(0);
}

function loadQuizTopics(moduleIdx) {
    const topicSelect = document.getElementById('quizTopicSelect');
    const topics = QuizModal.modules[moduleIdx]?.topics || [];
    topicSelect.innerHTML = topics.length
        ? topics.map(t => `<option value="${escH(t)}">${escH(t)}</option>`).join('')
        : '<option value="">Describe in chat instead</option>';
}

function closeQuizModal() { document.getElementById('quizGenModal').classList.add('hidden'); }

async function submitQuizModal() {
    const subject    = document.getElementById('quizSubjectSelect').value || 'General';
    const moduleIdx  = Number(document.getElementById('quizModuleSelect').value || 0);
    const moduleName = QuizModal.modules[moduleIdx]?.module || 'Custom Topic';
    const topic      = document.getElementById('quizTopicSelect').value;
    const difficulty = document.getElementById('quizDifficultySelect').value;
    const count      = parseInt(document.getElementById('quizCountInput').value) || 5;
    const topicLabel = topic ? `${moduleName} — ${topic}` : moduleName;
    closeQuizModal();
    await generateQuiz(subject, topicLabel, difficulty, count);
}

// ── QUIZ GENERATE ────────────────────────────────────────────────
async function generateQuiz(subject, module, difficulty, questionCount) {
    setBusy(true); showThinking();
    try {
        const data = await postJSON('/api/quiz/generate', { subject, module, difficulty, question_count: questionCount });
        removeThinking();
        Chat.quiz = data.quiz;
        addMsg('assistant', `Quiz ready: **${data.quiz?.title || 'HSC Practice Quiz'}** — ${data.quiz?.questions?.length || 0} question(s). Use the card below to answer, then hit Submit.`);
        addQuizBubble(data.quiz, { messageID: data.quizMessageID });
    } catch (err) {
        removeThinking();
        addMsg('assistant', '⚠️ ' + err.message);
        showToast(err.message, 'error');
    } finally { setBusy(false); }
}

// ── QUIZ BUBBLE ───────────────────────────────────────────────────
function addQuizBubble(quiz, opts = {}) {
    if (!quiz?.questions?.length) { showToast('Quiz data was not in the expected format.', 'error'); return; }

    const readonly = Boolean(opts.readonly);
    const answers  = opts.answers || {};
    const quizId   = 'qz-' + (opts.messageID ? `m${opts.messageID}` : Date.now());

    if (!readonly) {
        Chat.activeQuizId = quizId;
        Chat.activeQuizMessageID = opts.messageID || null;
        Chat.quiz = quiz;
    }

    const questionsHtml = quiz.questions.map((q, i) => {
        const id    = escH(q.id || `q${i + 1}`);
        const marks = q.marks || 1;
        const saved = answers[q.id || `q${i + 1}`] ?? '';

        let inputHtml = '';
        if (q.type === 'multiple_choice' && Array.isArray(q.options)) {
            inputHtml = `<div class="quiz-options">${q.options.map(o => {
                const checked  = readonly && saved === o ? 'checked' : '';
                const disabled = readonly ? 'disabled' : '';
                return `<label><input type="radio" name="${id}" value="${escH(o)}" ${checked} ${disabled}><span>${escH(o)}</span></label>`;
            }).join('')}</div>`;
        } else {
            inputHtml = `<textarea class="quiz-answer" rows="3" placeholder="Type your answer…" aria-label="Answer for question ${i + 1}" ${readonly ? 'readonly' : ''}>${escH(saved)}</textarea>`;
        }

        return `<div class="quiz-question" data-id="${id}" data-type="${escH(q.type || 'short_answer')}">
            <p class="quiz-question-text">${escH(q.question || '')} <span class="quiz-question-meta">(${marks} mark${marks !== 1 ? 's' : ''})</span></p>
            ${inputHtml}
        </div>`;
    }).join('');

    const actionsHtml = readonly
        ? `<p class="quiz-submitted-note">✓ Answers submitted — see feedback below</p>`
        : `<div class="quiz-card-actions">
               <button class="btn btn-primary" onclick="submitQuiz('${quizId}')" type="button">Submit Answers</button>
           </div>`;

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
                ${actionsHtml}
            </div>
        </div>`;

    EL.messages.appendChild(art);
    EL.messages.scrollTop = EL.messages.scrollHeight;

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

    if (!Object.values(answers).some(Boolean)) { showToast('Answer at least one question before submitting.', 'error'); return; }

    const body    = document.getElementById(`${quizId}-body`);
    const actions = body?.querySelector('.quiz-card-actions');
    if (actions) actions.innerHTML = '<p class="quiz-submitted-note">✓ Answers submitted — marking below</p>';
    toggleQuizCard(quizId);
    setBusy(true); showThinking();

    try {
        const data = await postJSON('/api/quiz/mark', { quiz: Chat.quiz, answers, quizMessageID: Chat.activeQuizMessageID });
        removeThinking();
        addQuizResultBubble(data.result);
    } catch (err) {
        removeThinking();
        addMsg('assistant', '⚠️ ' + err.message);
        showToast(err.message, 'error');
    } finally { setBusy(false); }
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

    addRawMsg('assistant', `
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
        </div>`);
}

// ── MESSAGES ─────────────────────────────────────────────────────
function addMsg(role, text) {
    hideWelcome();
    const art = document.createElement('article');
    art.className = `message ${role}`;
    const av  = document.createElement('div');
    av.className = 'msg-av';
    av.innerHTML = role === 'user' ? userAvatarHTML() : '<img src="/static/images/icon-192.png" width="22" height="22" alt="Dusty assistant">';
    const bub = document.createElement('div');
    bub.className = 'msg-bubble';
    bub.innerHTML = renderMD(text);
    renderMath(bub);
    art.appendChild(av); art.appendChild(bub);
    EL.messages.appendChild(art);
    EL.messages.scrollTop = EL.messages.scrollHeight;
}

function addRawMsg(role, html) {
    hideWelcome();
    const art = document.createElement('article');
    art.className = `message ${role}`;
    const av  = document.createElement('div');
    av.className = 'msg-av';
    av.innerHTML = role === 'user' ? userAvatarHTML() : '<img src="/static/images/icon-192.png" width="22" height="22" alt="Dusty assistant">';
    const bub = document.createElement('div');
    bub.className = 'msg-bubble';
    bub.innerHTML = html;
    renderMath(bub);
    art.appendChild(av); art.appendChild(bub);
    EL.messages.appendChild(art);
    EL.messages.scrollTop = EL.messages.scrollHeight;
}

// ── MATH RENDERER (KaTeX) ─────────────────────────────────────────
function renderMath(el) {
    if (!window.renderMathInElement) return;
    try {
        renderMathInElement(el, {
            delimiters: [
                { left: '$$',   right: '$$',   display: true  },
                { left: '$',    right: '$',    display: false },
                { left: '\\[', right: '\\]', display: true  },
                { left: '\\(', right: '\\)', display: false },
            ],
            throwOnError: false,
            output: 'html',
        });
    } catch (e) { /* KaTeX not yet loaded — silently skip */ }
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
 
    // ── HTML entity escape ────────────────────────────────────────
    function esc(v) {
        return String(v ?? '')
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;');
    }
 
    // ── Inline formatting (applied to content text, never to raw bullet prefix) ──
    function fmt(s) {
        // Bold-italic must come before bold and italic
        s = s.replace(/\*\*\*(?!\s)(.+?)(?<!\s)\*\*\*/g, '<strong><em>$1</em></strong>');
        // Bold
        s = s.replace(/\*\*(?!\s)(.+?)(?<!\s)\*\*/g, '<strong>$1</strong>');
        // Italic — asterisk NOT followed by whitespace, content, closing asterisk NOT preceded by whitespace
        // This correctly handles *word*, *two words*, *phrase with spaces* etc.
        s = s.replace(/\*(?!\s)([^*\n]+?)(?<!\s)\*/g, '<em>$1</em>');
        // Inline code
        s = s.replace(/`([^`\n]+)`/g, '<code>$1</code>');
        // Dusty colour spans  [text]{colour}
        s = s.replace(
            /\[(.+?)\]\{(red|green|blue|orange|purple|yellow|teal|pink)\}/g,
            '<span class="chat-colour-$2">$1</span>'
        );
        return s;
    }
 
    // ── Escape then handle block-level headings and rules ─────────
    let s = esc(raw);
 
    s = s.replace(/^######\s+(.+)$/gm, (_, t) => `<h3>${fmt(t)}</h3>`);
    s = s.replace(/^#####\s+(.+)$/gm,  (_, t) => `<h3>${fmt(t)}</h3>`);
    s = s.replace(/^####\s+(.+)$/gm,   (_, t) => `<h3>${fmt(t)}</h3>`);
    s = s.replace(/^###\s+(.+)$/gm,    (_, t) => `<h3>${fmt(t)}</h3>`);
    s = s.replace(/^##\s+(.+)$/gm,     (_, t) => `<h2>${fmt(t)}</h2>`);
    s = s.replace(/^#\s+(.+)$/gm,      (_, t) => `<h1>${fmt(t)}</h1>`);
    s = s.replace(/^---$/gm, '<hr>');
 
    // ── Split on blank lines ──────────────────────────────────────
    const blocks = s.split(/\n{2,}/);
 
    const rendered = blocks.map(block => {
        block = block.trim();
        if (!block) return '';
 
        // Already-converted block-level element
        if (/^<(h[1-6]|hr)/.test(block)) return block;
 
        const lines = block.split('\n').map(l => l.trim()).filter(Boolean);
 
        // ── Raw-line classifiers ─────────────────────────────────
        // A bullet line starts with "- ", "* " (asterisk SPACE), or "• "
        const isBullet  = l => /^[-*•]\s/.test(l);
        const isOrdered = l => /^\d+\.\s/.test(l);
        const isQuote   = l => /^>\s/.test(l);
 
        const allBullet  = lines.every(isBullet);
        const allOrdered = lines.every(isOrdered);
        const allQuote   = lines.every(isQuote);
 
        if (allBullet) {
            return `<ul>${
                lines.map(l => `<li>${fmt(l.replace(/^[-*•]\s/, ''))}</li>`).join('')
            }</ul>`;
        }
 
        if (allOrdered) {
            return `<ol>${
                lines.map(l => `<li>${fmt(l.replace(/^\d+\.\s/, ''))}</li>`).join('')
            }</ol>`;
        }
 
        if (allQuote) {
            return `<blockquote>${
                lines.map(l => fmt(l.replace(/^>\s/, ''))).join('<br>')
            }</blockquote>`;
        }
 
        // ── Mixed block (bullets + plain prose in same paragraph) ─
        const hasMixedList = lines.some(isBullet) || lines.some(isOrdered);
 
        if (hasMixedList) {
            let html = '';
            let inUL = false;
            let inOL = false;
 
            lines.forEach(l => {
                if (isBullet(l)) {
                    if (inOL) { html += '</ol>'; inOL = false; }
                    if (!inUL) { html += '<ul>'; inUL = true; }
                    html += `<li>${fmt(l.replace(/^[-*•]\s/, ''))}</li>`;
                } else if (isOrdered(l)) {
                    if (inUL) { html += '</ul>'; inUL = false; }
                    if (!inOL) { html += '<ol>'; inOL = true; }
                    html += `<li>${fmt(l.replace(/^\d+\.\s/, ''))}</li>`;
                } else {
                    if (inUL) { html += '</ul>'; inUL = false; }
                    if (inOL) { html += '</ol>'; inOL = false; }
                    html += `<p>${fmt(l)}</p>`;
                }
            });
 
            if (inUL) html += '</ul>';
            if (inOL) html += '</ol>';
            return html;
        }
 
        // ── Plain paragraph ───────────────────────────────────────
        return `<p>${lines.map(fmt).join('<br>')}</p>`;
    });
 
    return rendered.join('') || '<p>No response.</p>';
}

// ── INGEST ───────────────────────────────────────────────────────
async function triggerIngest() {
    const btn = document.getElementById('ingestBtn');
    if (btn) btn.disabled = true;
    try {
        const data = await postJSON('/api/ingest', {});
        showToast(data.status || 'Ingestion started.', 'info');
        setTimeout(checkKB, 5000);
    } catch (err) { showToast(err.message, 'error'); }
    finally { setTimeout(() => { if (btn) btn.disabled = false; }, 3000); }
}

// ── KB STATUS ────────────────────────────────────────────────────
async function checkKB() {
    try {
        const res  = await fetch('/api/status');
        const data = await res.json();
        if (!res.ok) throw new Error(data.error || 'Status check failed');
        const n = data.chunks_in_database || 0;
        if (EL.kbText) EL.kbText.textContent = n > 0 ? `${n.toLocaleString()} chunks` : 'No chunks — Rebuild KB';
    } catch {
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
                <button class="chat-item-action" title="Rename" onclick="renameChatSession(${sess.sessionID}); event.stopPropagation();" aria-label="Rename chat"><img src="/static/images/rename-icon.svg" alt="Rename" class="btn-icon-xs"></button>
                <button class="chat-item-action" title="Delete" onclick="deleteChatSession(${sess.sessionID}); event.stopPropagation();" aria-label="Delete chat"><img src="/static/images/trash-grey-icon.svg" alt="Delete" class="btn-icon-xs"></button>
            </span>
        </div>`).join('');

    EL.chatHistory.querySelectorAll('.chat-history-item').forEach(item =>
        item.addEventListener('click', () => loadChat(parseInt(item.dataset.sessionId)))
    );
}

async function createNewChat() {
    // Tell server to clear the active session cookie
    await fetch('/api/chat/clear-session', { method: 'POST' }).catch(() => {});

    // Reset local state
    Chat.sessionID           = null;
    Chat.quiz                = null;
    Chat.activeQuizId        = null;
    Chat.activeQuizMessageID = null;
    attachedFile             = null;
    removeAttachedFile();

    // Clear messages and show welcome screen
    if (EL.messages) EL.messages.innerHTML = '';
    showWelcome();

    // Create a session in the background (session will be assigned on first message)
    await loadChatSessions();
}

async function loadChat(sessionID) {
    // Reset ALL local state before switching sessions
    Chat.sessionID           = null;
    Chat.quiz                = null;
    Chat.activeQuizId        = null;
    Chat.activeQuizMessageID = null;
    attachedFile             = null;
    removeAttachedFile();
 
    // Tell Flask to forget the old active session cookie
    await fetch('/api/chat/clear-session', { method: 'POST' }).catch(() => {});
 
    try {
        const res  = await fetch(`/api/chat/session/${sessionID}`);
        if (!res.ok) throw new Error('Could not load chat');
        const data = await res.json();
        // Set AFTER server call so the loaded session's history
        // is correctly associated from this point forward
        Chat.sessionID = sessionID;
        EL.messages.innerHTML = '';
 
        (data.messages || []).forEach(msg => {
            if (msg.mode === 'quiz') {
                try { addQuizBubble(JSON.parse(msg.content), { messageID: msg.messageID }); }
                catch { addMsg(msg.role, msg.content); }
                return;
            }
            if (msg.mode === 'quiz_result') {
                try {
                    const payload = JSON.parse(msg.content);
                    addQuizBubble(payload.quiz, {
                        messageID: msg.messageID,
                        answers:   payload.answers,
                        readonly:  true,
                    });
                    addQuizResultBubble(payload.result);
                } catch { addMsg(msg.role, msg.content); }
                return;
            }
            addMsg(msg.role, msg.content);
        });

        hideWelcome();
 
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
    } catch { showToast('Could not delete chat', 'error'); }
}

async function renameChatSession(sessionID) {
    const current   = Chat.sessions.find(s => s.sessionID === sessionID);
    const nextTitle = prompt('Rename chat', current?.title || 'Untitled Chat');
    if (nextTitle === null) return;
    const title = nextTitle.trim();
    if (!title) { showToast('Chat title cannot be empty', 'error'); return; }
    try {
        const res  = await fetch(`/api/chat/session/${sessionID}`, {
            method: 'PATCH', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ title })
        });
        const data = await res.json().catch(() => ({}));
        if (!res.ok) throw new Error(data.error || 'Could not rename chat');
        Chat.sessions = Chat.sessions.map(s => s.sessionID === sessionID ? { ...s, title: data.title } : s);
        renderChatHistory();
        showToast('Chat renamed', 'info');
    } catch (err) { showToast(err.message, 'error'); }
}

// ── UTILITIES ────────────────────────────────────────────────────
async function postJSON(url, body) {
    const res  = await fetch(url, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(data.error || `Request failed (${res.status})`);
    return data;
}

function setBusy(v) {
    Chat.busy = v;
    if (EL.sendBtn) {
        EL.sendBtn.disabled = v;
        if (EL.sendLabel) EL.sendLabel.textContent = v ? '…' : 'Send';
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