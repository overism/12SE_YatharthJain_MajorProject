/* ================================================================
   flashcards.js  –  Dusty Flashcard System
   Handles: subject modal, deck generation + DB persistence,
            card flip, traffic-light sorting, result saving
   ================================================================ */

const FC = {
    subjects: [],
    decks: [],          // Decks loaded from the database
    activeDeck: null,   // Currently displayed deck
    currentIndex: 0,
    flipped: false,
    selectedSubject: null,
    sort: { knew: [], unsure: [], missed: [], unsorted: [] },
};

const DEFAULT_FLASHCARD_SUBJECTS = ['Software Engineering', 'English Advanced', 'Mathematics Advanced', 'Chemistry', 'General'];

// ── INIT ──────────────────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', () => {
    loadSubjects();
    loadDecksFromDB();   // persistent: pulls saved decks from the server
    openModal();
});

// ── SUBJECT LOADING ───────────────────────────────────────────────
async function loadSubjects() {
    try {
        const res = await fetch('/api/subjects');
        const data = await res.json();
        FC.subjects = (data.subjects || []).map(s => ({
            subjectID: s.subjectID,
            subjectName: s.subjectName || s.name || 'General',
            colourScheme: s.colourScheme || 'orange',
        }));
    } catch {
        FC.subjects = DEFAULT_FLASHCARD_SUBJECTS.map(name => ({ subjectName: name, colourScheme: 'orange' }));
    }
    renderModalSubjects();
    renderLibSubjectSelect();
}

function renderModalSubjects() {
    const grid = document.getElementById('modalSubjectGrid');
    if (!grid) return;
    grid.innerHTML = FC.subjects.map(s => `
        <button class="modal-subject-btn" data-subject="${s.subjectName}" onclick="selectModalSubject(this,'${s.subjectName}')">
            <span class="modal-dot" style="background:${window.getSubjectColour ? window.getSubjectColour(s.colourScheme || 'orange') : window.SUBJECT_COLOURS?.[s.colourScheme] || '#f5761c'}"></span>
            ${s.subjectName}
        </button>
    `).join('');
}

function renderLibSubjectSelect() {
    const sel = document.getElementById('libSubjectSelect');
    if (!sel) return;
    sel.innerHTML = FC.subjects.map(s => `<option value="${s.subjectName}">${s.subjectName}</option>`).join('');
}

// ── MODAL ─────────────────────────────────────────────────────────
function openModal() {
    document.getElementById('subjectModal').classList.remove('hidden');
    FC.selectedSubject = null;
    document.querySelectorAll('.modal-subject-btn').forEach(b => b.classList.remove('selected'));
}

function closeModal() {
    document.getElementById('subjectModal').classList.add('hidden');
}

function selectModalSubject(btn, subject) {
    document.querySelectorAll('.modal-subject-btn').forEach(b => b.classList.remove('selected'));
    btn.classList.add('selected');
    FC.selectedSubject = subject;
}

async function generateFromModal() {
    const subject = FC.selectedSubject;
    if (!subject) { showStatus('Please select a subject first.', 'error'); return; }
    const module = document.getElementById('modalModule').value.trim() || 'General';
    const count = parseInt(document.getElementById('modalCount').value) || 6;
    closeModal();
    await generateDeckWith(subject, module, count);
}

// ── DECK GENERATION ───────────────────────────────────────────────
async function generateDeck() {
    const subject = document.getElementById('libSubjectSelect').value;
    const module = document.getElementById('libModuleInput').value.trim() || 'General';
    const count = parseInt(document.getElementById('libCardCount').value) || 6;
    await generateDeckWith(subject, module, count);
}

async function generateDeckWith(subject, module, count) {
    const btn = document.getElementById('libGenerateBtn');
    if (btn) { btn.disabled = true; btn.textContent = 'Generating...'; }
    showStatus('Generating flashcards…', 'info');

    try {
        // 1. Generate cards via AI
        const res = await fetch('/api/flashcards', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ subject, module, count })
        });
        const data = await res.json();
        if (!res.ok || data.error) throw new Error(data.error || 'Generation failed');

        const title = data.title || `${subject} — ${module}`;
        const cards = data.flashcards || [];

        // 2. Persist to the database
        const saveRes = await fetch('/api/flashcards/decks', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ title, subject, module, flashcards: cards })
        });
        const saveData = await saveRes.json();
        if (!saveRes.ok || saveData.error) throw new Error(saveData.error || 'Could not save deck');

        // 3. Build local deck object using the DB-assigned ID
        const deck = {
            id:         saveData.deckID,
            deckID:     saveData.deckID,
            title,
            subject:    data.subject || subject,
            module:     data.module  || module,
            flashcards: cards,
            createdAt:  new Date().toISOString(),
        };

        FC.decks.unshift(deck);
        renderDeckGrid();
        showStatus(`Generated and saved ${cards.length} cards for ${subject}.`, 'success');
        loadDeck(deck);

    } catch (e) {
        showStatus(e.message, 'error');
    } finally {
        if (btn) { btn.disabled = false; btn.textContent = 'Generate'; }
    }
}

// ── DECK PERSISTENCE — DATABASE-BACKED ───────────────────────────
async function loadDecksFromDB() {
    const grid = document.getElementById('deckGrid');
    if (grid) grid.innerHTML = '<div class="empty-state"><div class="icon" style="font-size:24px">⏳</div><p>Loading your decks…</p></div>';

    try {
        const res  = await fetch('/api/flashcards/decks');
        const data = await res.json();
        if (!res.ok) throw new Error(data.error || 'Could not load decks');

        FC.decks = (data.decks || []).map(d => ({
            id:         d.deckID,
            deckID:     d.deckID,
            title:      d.title,
            subject:    d.subject,
            module:     d.module,
            flashcards: d.flashcards || [],
            createdAt:  d.createdAt,
        }));

    } catch (e) {
        // Fall back to empty — new user or server error
        FC.decks = [];
        showStatus('Could not load saved decks: ' + e.message, 'error');
    }

    renderDeckGrid();
}

async function deleteDeckFromDB(deckID, e) {
    e.stopPropagation();
    if (!confirm('Delete this deck? This cannot be undone.')) return;

    try {
        const res = await fetch(`/api/flashcards/decks/${deckID}`, { method: 'DELETE' });
        const data = await res.json();
        if (!res.ok) throw new Error(data.error || 'Delete failed');

        FC.decks = FC.decks.filter(d => d.id !== deckID);
        if (FC.activeDeck?.id === deckID) {
            document.getElementById('deckArea').classList.remove('visible');
            FC.activeDeck = null;
        }
        renderDeckGrid();
        showStatus('Deck deleted.', 'success');
    } catch (err) {
        showStatus(err.message, 'error');
    }
}

async function saveSessionResult() {
    const deck = FC.activeDeck;
    if (!deck?.deckID) return;   // unsaved sub-deck (e.g. "missed only")

    try {
        await fetch('/api/flashcards/results', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                deckID:     deck.deckID,
                knew:       FC.sort.knew.length,
                unsure:     FC.sort.unsure.length,
                missed:     FC.sort.missed.length,
                totalCards: deck.flashcards.length,
            })
        });
    } catch (err) {
        console.warn('[Flashcards] Could not save result:', err.message);
    }
}

// ── DECK GRID ─────────────────────────────────────────────────────
function renderDeckGrid() {
    const grid = document.getElementById('deckGrid');
    if (!grid) return;

    if (!FC.decks.length) {
        grid.innerHTML = `<div class="empty-state"><div class="icon">🃏</div><p>No decks yet. Generate your first deck above or use the <strong>+ New Deck</strong> button.</p></div>`;
        return;
    }

    grid.innerHTML = FC.decks.map(deck => `
        <div class="deck-card" onclick='loadDeckById(${deck.id})'>
            <div class="deck-card-subject">${escHtml(deck.subject)}</div>
            <div class="deck-card-title">${escHtml(deck.title)}</div>
            <div class="deck-card-module">${escHtml(deck.module)}</div>
            <div class="deck-card-meta">
                <span class="deck-card-count">${deck.flashcards.length} cards</span>
                <div style="display:flex;gap:6px;align-items:center">
                    <span class="deck-card-play">▶</span>
                    <button
                        onclick="deleteDeckFromDB(${deck.id}, event)"
                        style="background:none;border:none;cursor:pointer;font-size:14px;color:#ccc;padding:0;line-height:1"
                        title="Delete deck">🗑</button>
                </div>
            </div>
        </div>
    `).join('');
}

function loadDeckById(id) {
    const deck = FC.decks.find(d => d.id === id);
    if (deck) loadDeck(deck);
}

// ── CARD STUDY ────────────────────────────────────────────────────
function loadDeck(deck) {
    FC.activeDeck = deck;
    FC.currentIndex = 0;
    FC.flipped = false;
    FC.sort = { knew: [], unsure: [], missed: [], unsorted: deck.flashcards.map((_, i) => i) };

    // Show deck area
    document.getElementById('deckArea').classList.add('visible');
    document.getElementById('restartBtn').style.display = '';
    document.getElementById('sessionComplete').classList.remove('show');
    document.getElementById('cardFlip').style.display = '';
    document.getElementById('trafficControls').style.display = 'none';
    document.getElementById('cardNav') && (document.getElementById('cardNav').style.display = '');
    document.getElementById('cardCounter') && (document.getElementById('cardCounter').style.display = '');
    document.getElementById('sortPiles') && (document.getElementById('sortPiles').style.display = '');

    document.getElementById('deckTitle').textContent = deck.title;
    document.getElementById('deckMeta').textContent = `${deck.subject} · ${deck.module}`;

    renderCard();
    updateSortBadges();

    // Scroll to deck area
    document.getElementById('deckArea').scrollIntoView({ behavior: 'smooth' });
}

function renderCard() {
    const deck = FC.activeDeck;
    if (!deck) return;
    const card = deck.flashcards[FC.currentIndex];
    if (!card) return;

    // Reset flip
    FC.flipped = false;
    const flip = document.getElementById('cardFlip');
    flip.classList.remove('flipped');
    document.getElementById('trafficControls').style.display = 'none';
    document.getElementById('flipHintBtn').textContent = 'Flip Card';

    document.getElementById('cardQuestion').textContent = card.question || card.prompt || '';
    document.getElementById('cardAnswer').textContent = card.answer || card.definition || '';

    const hint = card.hint || card.tip || '';
    const hintEl = document.getElementById('cardHint');
    if (hint) { hintEl.textContent = '💡 ' + hint; hintEl.style.display = ''; }
    else { hintEl.style.display = 'none'; }

    document.getElementById('cardCounter').textContent = `Card ${FC.currentIndex + 1} of ${deck.flashcards.length}`;
}

function flipCard() {
    FC.flipped = !FC.flipped;
    document.getElementById('cardFlip').classList.toggle('flipped', FC.flipped);
    document.getElementById('trafficControls').style.display = FC.flipped ? 'flex' : 'none';
    document.getElementById('flipHintBtn').textContent = FC.flipped ? 'Show Question' : 'Flip Card';
}

function nextCard() {
    if (!FC.activeDeck) return;
    if (FC.currentIndex < FC.activeDeck.flashcards.length - 1) {
        FC.currentIndex++;
        renderCard();
    }
}

function prevCard() {
    if (FC.currentIndex > 0) { FC.currentIndex--; renderCard(); }
}

function sortCard(result) {
    const idx = FC.currentIndex;
    // Remove from all piles
    ['knew','unsure','missed','unsorted'].forEach(k => {
        FC.sort[k] = FC.sort[k].filter(i => i !== idx);
    });
    FC.sort[result].push(idx);
    updateSortBadges();

    // Move to next unsorted, else next card
    const next = FC.sort.unsorted.find(i => i > idx);
    if (next !== undefined) {
        FC.currentIndex = next;
        renderCard();
    } else {
        checkSessionComplete();
    }
}

function updateSortBadges() {
    const { knew, unsure, missed } = FC.sort;
    const total = FC.activeDeck?.flashcards?.length || 1;

    ['knew','unsure','missed'].forEach(k => {
        const count = FC.sort[k].length;
        document.getElementById('count' + k.charAt(0).toUpperCase() + k.slice(1)).textContent = count;
        document.getElementById('pile' + k.charAt(0).toUpperCase() + k.slice(1)).textContent = count;
        document.getElementById('bar' + k.charAt(0).toUpperCase() + k.slice(1)).style.width = (count / total * 100) + '%';
    });
}

function checkSessionComplete() {
    if (FC.sort.unsorted.length > 0) return;

    // All cards sorted — show completion screen
    document.getElementById('cardFlip').style.display = 'none';
    document.getElementById('trafficControls').style.display = 'none';
    document.getElementById('cardCounter').textContent = 'Session complete!';

    document.getElementById('finalKnew').textContent   = FC.sort.knew.length;
    document.getElementById('finalUnsure').textContent = FC.sort.unsure.length;
    document.getElementById('finalMissed').textContent = FC.sort.missed.length;
    document.getElementById('sessionComplete').classList.add('show');
    
    document.getElementById('cardNav').style.display = 'none';
    document.getElementById('cardCounter').style.display = 'none';
    document.getElementById('sortPiles').style.display = 'none';

    // Save result to the database for Progress tracking
    saveSessionResult();
}

function restartDeck() {
    if (FC.activeDeck) loadDeck(FC.activeDeck);
}

function studyMissed() {
    if (!FC.activeDeck || !FC.sort.missed.length) {
        showStatus('No missed cards to study!', 'info');
        return;
    }
    const missedDeck = {
        ...FC.activeDeck,
        title: FC.activeDeck.title + ' (Missed)',
        flashcards: FC.sort.missed.map(i => FC.activeDeck.flashcards[i])
    };
    loadDeck(missedDeck);
}

// ── UTILS ─────────────────────────────────────────────────────────
function showStatus(msg, type = 'info') {
    const el = document.getElementById('fcStatus');
    if (!el) return;
    el.textContent = msg;
    el.className = `status show ${type}`;
    clearTimeout(el._t);
    el._t = setTimeout(() => { el.className = 'status'; }, 4200);
}

function escHtml(v) {
    return String(v || '').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
}