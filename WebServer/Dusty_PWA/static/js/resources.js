/* ================================================================
   resources.js  –  Dusty Resource Library
   Fix: search results and tree file links use proper <a> tags
        so files open directly without popup-blocker issues.
   Adds: user file upload support (My Uploads library tab).
   ================================================================ */

const RS = {
    libraries:    [],
    activeLibIdx: 0,
    currentPath:  [],
    currentNode:  null,
    searchQuery:  '',
    allFiles:     [],
};

let SUBJECT_NAME_COLOURS = {};

// ── ICON / EXT HELPERS ──────────────────────────────────────────
const EXT_ICONS = {
    pdf:'📄', docx:'📝', doc:'📝', pptx:'📊', ppt:'📊',
    xlsx:'📈', xls:'📈', csv:'📈', txt:'📃', md:'📃',
    png:'🖼', jpg:'🖼', jpeg:'🖼', gif:'🖼',
    mp4:'🎬', mp3:'🎵',
};
function getIcon(ext) { return EXT_ICONS[ext] || '📎'; }
function extClass(ext) {
    const m = { pdf:'ext-pdf', docx:'ext-docx', doc:'ext-doc', pptx:'ext-pptx', ppt:'ext-ppt', xlsx:'ext-xlsx', csv:'ext-csv', txt:'ext-txt', md:'ext-md' };
    return m[ext] || 'ext-default';
}

function normaliseSubjectName(name) {
    return String(name||'').toLowerCase().replace(/&/g,'and').replace(/[^a-z0-9]+/g,' ').trim();
}

function resolveSubjectColour(subjectName) {
    const fallback = window.getSubjectColour?.('orange') || '#f5761c';
    if (!subjectName) return fallback;
    if (SUBJECT_NAME_COLOURS[subjectName]) return SUBJECT_NAME_COLOURS[subjectName];
    const target = normaliseSubjectName(subjectName);
    for (const [name, colour] of Object.entries(SUBJECT_NAME_COLOURS)) {
        const key = normaliseSubjectName(name);
        if (target === key || target.includes(key) || key.includes(target)) return colour;
    }
    return fallback;
}

// ── INIT ────────────────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', async() => {
    const loadingScreen = document.getElementById('resources-loading');
    if (loadingScreen) {
        loadingScreen.classList.remove('is-hidden');
    }
    
    loadResources();

    setTimeout(() => {
        const loadingScreen = document.getElementById('resources-loading');
        if (loadingScreen) {
            loadingScreen.classList.add('is-hidden');
        }
    }, 2000);
});

async function loadResources() {
    try {
        const [res, subjRes] = await Promise.all([
            fetch('/api/resources'),
            fetch('/api/subjects'),
        ]);
        const data     = await res.json();
        const subjData = await subjRes.json().catch(() => ({}));
        if (!res.ok) throw new Error(data.error || 'Could not load resources');

        if (subjRes.ok && Array.isArray(subjData.subjects)) {
            SUBJECT_NAME_COLOURS = {};
            subjData.subjects.forEach(s => {
                const c = window.getSubjectColour
                    ? window.getSubjectColour(s.colourScheme || 'orange')
                    : window.SUBJECT_COLOURS?.[s.colourScheme] || '#f5761c';
                SUBJECT_NAME_COLOURS[s.subjectName] = c;
                SUBJECT_NAME_COLOURS[normaliseSubjectName(s.subjectName)] = c;
            });
        }

        RS.libraries = data.libraries || [];
        RS.allFiles  = buildFlatFileList(RS.libraries);

        renderLibraryTabs();
        renderTree();
        renderMainContent();
        showStatus(`${RS.allFiles.length} file${RS.allFiles.length !== 1 ? 's' : ''} loaded.`, 'success');
    } catch (e) {
        showStatus(e.message, 'error');
        document.getElementById('resourcesContent').innerHTML = `
            <div class="empty-state">
                <div class="icon">⚠️</div>
                <h3>Could not load resources</h3>
                <p>${escHtml(e.message)}</p>
            </div>`;
    }
}

// ── FLAT FILE LIST (for search) ─────────────────────────────────
function buildFlatFileList(libraries) {
    const files = [];
    libraries.forEach(lib => {
        lib.subjects.forEach(subj => {
            walkNodes(subj.tree, [], lib, subj.name, files);
        });
    });
    return files;
}

function walkNodes(nodes, pathStack, lib, subjectName, out) {
    (nodes || []).forEach(node => {
        if (node.type === 'file') {
            out.push({
                name:         node.name,
                path:         node.path,
                ext:          (node.extension || '').replace('.', ''),
                sourceKey:    lib.source_key,
                libraryTitle: lib.title,
                subjectName,
                breadcrumb:   pathStack.join(' / '),
            });
        } else if (node.type === 'directory') {
            walkNodes(node.children || [], [...pathStack, node.name], lib, subjectName, out);
        }
    });
}

// ── LIBRARY TABS ────────────────────────────────────────────────
function renderLibraryTabs() {
    const el = document.getElementById('libraryTabs');
    if (!el) return;
    el.innerHTML = RS.libraries.map((lib, i) => `
        <button class="lib-tab ${i === RS.activeLibIdx ? 'active' : ''}"
                onclick="switchLibrary(${i})" type="button">${escHtml(lib.title)}</button>
    `).join('');
}

function switchLibrary(idx) {
    RS.activeLibIdx = idx;
    RS.currentPath  = [];
    RS.currentNode  = null;
    renderLibraryTabs();
    renderTree();
    renderMainContent();
}

// ── TREE SIDEBAR ────────────────────────────────────────────────
function renderTree() {
    const el  = document.getElementById('treeScroll');
    if (!el)  return;
    const lib = RS.libraries[RS.activeLibIdx];
    if (!lib) { el.innerHTML = '<div style="padding:20px;color:#bbb;text-align:center;font-size:13px">No libraries found.</div>'; return; }

    el.innerHTML = lib.subjects.map(subj => renderTreeSubject(subj, lib)).join('');
}

function renderTreeSubject(subj, lib) {
    const colour      = resolveSubjectColour(subj.name);
    const childrenHtml = renderTreeNodes(subj.tree || [], lib.source_key, 1, colour);
    return `
        <div class="tree-node">
            <div class="tree-folder-row open tree-folder-depth-0"
                 onclick="toggleFolder(this)">
                <span class="tree-folder-icon" style="color:${colour}">▶</span>
                <span class="tree-folder-label" style="color:#22140b;font-size:13px;font-weight:700">${escHtml(subj.name)}</span>
            </div>
            <div class="tree-children visible">${childrenHtml}</div>
        </div>`;
}

function renderTreeNodes(nodes, sourceKey, depth, subjectColour) {
    return (nodes || []).map(node => {
        if (node.type === 'directory') {
            const children = renderTreeNodes(node.children || [], sourceKey, depth + 1, subjectColour);
            const count    = countFiles(node);
            return `
                <div class="tree-node tree-folder-depth-${Math.min(depth,3)}">
                    <div class="tree-folder-row"
                         onclick="treeOpenFolder(this, event)"
                         style="--tree-subject-colour:${subjectColour}"
                         data-name="${escHtml(node.name)}"
                         data-path="${escHtml(node.path)}"
                         data-source="${escHtml(sourceKey)}">
                        <span class="tree-folder-icon">▶</span>
                        <span class="tree-folder-label">${escHtml(node.name)}</span>
                        <span class="tree-folder-count">${count}</span>
                    </div>
                    <div class="tree-children">${children}</div>
                </div>`;
        } else {
            /* ── Use proper <a> tag so the browser navigates directly.
               This avoids popup blockers that would block window.open(). ── */
            const ext  = (node.extension || '').replace('.', '');
            const href = buildResourceHref(sourceKey, node.path);
            return `
                <a class="tree-file-link depth-${Math.min(depth + 1, 4)}"
                   href="${escHtml(href)}" target="_blank" rel="noopener noreferrer">
                    <span class="tree-file-icon">${getIcon(ext)}</span>
                    <span class="tree-file-name">${escHtml(node.name)}</span>
                    <span class="tree-file-ext ${extClass(ext)}">${ext || 'file'}</span>
                </a>`;
        }
    }).join('');
}

function buildResourceHref(sourceKey, path) {
    if (sourceKey === 'user_uploads') {
        return `/resource/upload/${encodeURIComponent(path)}`;
    }
    return `/resource?source=${encodeURIComponent(sourceKey)}&path=${encodeURIComponent(path)}`;
}

function countFiles(node) {
    if (node.type === 'file') return 1;
    return (node.children || []).reduce((a, c) => a + countFiles(c), 0);
}

function toggleFolder(row) {
    const children = row.nextElementSibling;
    if (!children) return;
    const open = children.classList.toggle('visible');
    row.classList.toggle('open', open);
}

function treeOpenFolder(row, e) {
    e.stopPropagation();
    const children = row.nextElementSibling;
    if (children) {
        const open = children.classList.toggle('visible');
        row.classList.toggle('open', open);
    }
    const lib  = RS.libraries[RS.activeLibIdx];
    if (!lib) return;
    const path = row.dataset.path;
    let found  = null;
    lib.subjects.forEach(s => { if (!found) found = findNodeByPath(s.tree, path); });
    if (found) {
        RS.currentNode = found;
        RS.currentPath = buildBreadcrumbForPath(lib, path);
        renderBreadcrumb();
        renderFolderGrid(found.children || [], row.dataset.source);
    }
}

function findNodeByPath(nodes, targetPath) {
    for (const n of (nodes || [])) {
        if (n.path === targetPath) return n;
        if (n.type === 'directory') {
            const found = findNodeByPath(n.children || [], targetPath);
            if (found) return found;
        }
    }
    return null;
}

function buildBreadcrumbForPath(lib, targetPath) {
    const parts  = targetPath.split('/');
    const crumbs = [];
    let nodes    = [];
    lib.subjects.forEach(s => { nodes.push(...(s.tree || [])); });
    let pathSoFar = '';
    for (const part of parts) {
        pathSoFar = pathSoFar ? pathSoFar + '/' + part : part;
        const node = nodes.find(n => n.name === part);
        if (node) { crumbs.push({ label: part, node, source: lib.source_key }); nodes = node.children || []; }
    }
    return crumbs;
}

function collapseAll() {
    document.querySelectorAll('.tree-children.visible').forEach(el => el.classList.remove('visible'));
    document.querySelectorAll('.tree-folder-row.open').forEach(el => el.classList.remove('open'));
}

// ── MAIN CONTENT ────────────────────────────────────────────────
function renderMainContent() {
    const lib = RS.libraries[RS.activeLibIdx];
    if (!lib) {
        document.getElementById('resourcesContent').innerHTML = `
            <div class="empty-state"><div class="icon">📂</div><h3>No libraries found</h3><p>Run the ingestion agent or upload your own files.</p></div>`;
        return;
    }
    RS.currentPath = [];
    RS.currentNode = null;
    renderBreadcrumb();

    const content = document.getElementById('resourcesContent');

    // My Uploads library renders differently
    if (lib.source_key === 'user_uploads') {
        renderUploadsContent(lib);
        return;
    }

    content.innerHTML = lib.subjects.map(subj => {
        const gridHtml = buildGridHtml(subj.tree || [], lib.source_key);
        return `
            <div class="subject-section">
                <div class="library-heading">
                    <h2>${escHtml(subj.name)}</h2>
                    <span class="lib-badge">${escHtml(lib.title)}</span>
                </div>
                ${gridHtml || '<p style="color:#bbb;font-size:13.5px;padding:6px 0">No files in this subject yet.</p>'}
            </div>`;
    }).join('');
}

function renderUploadsContent(lib) {
    const content = document.getElementById('resourcesContent');
    const files   = lib.subjects?.[0]?.tree || [];

    if (!files.length) {
        content.innerHTML = `
            <div class="uploads-section">
                <div class="uploads-heading">
                    <h2>My Uploads</h2>
                    <span class="uploads-badge">Personal</span>
                </div>
                <div class="empty-state">
                    <div class="icon">📤</div>
                    <h3>No uploads yet</h3>
                    <p>Click <strong>Upload</strong> in the header to add your own notes, PDFs, and study materials.</p>
                </div>
            </div>`;
        return;
    }

    const grid = files.map(f => {
        const ext  = (f.extension || '').replace('.', '');
        const href = buildResourceHref('user_uploads', f.path);
        return `
            <div class="upload-file-card">
                <div style="font-size:26px">${getIcon(ext)}</div>
                <div class="upload-file-name">${escHtml(f.name)}</div>
                <div class="upload-file-meta"><span class="tree-file-ext ${extClass(ext)}" style="display:inline-block">${ext || 'file'}</span></div>
                <div class="upload-file-actions">
                    <a class="upload-open-btn" href="${escHtml(href)}" target="_blank" rel="noopener noreferrer"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true" width="15" height="15" style="flex-shrink:0;"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="17 8 12 3 7 8"/><line x1="12" y1="3" x2="12" y2="15"/></svg>Open</a>
                    <button class="upload-del-btn" onclick="deleteUpload('${escHtml(f.name)}')" type="button">Delete</button>
                </div>
            </div>`;
    }).join('');

    content.innerHTML = `
        <div class="uploads-section">
            <div class="uploads-heading">
                <h2>My Uploads</h2>
                <span class="uploads-badge">${files.length} file${files.length !== 1 ? 's' : ''}</span>
            </div>
            <div class="file-grid">${grid}</div>
        </div>`;
}

function buildGridHtml(nodes, sourceKey) {
    if (!nodes.length) return '';
    return `<div class="file-grid">
        ${nodes.map(node => {
            if (node.type === 'directory') {
                const count = countFiles(node);
                return `<div class="folder-card" onclick='navigateInto(${JSON.stringify(node)}, "${escHtml(sourceKey)}")'>
                    <div class="folder-card-icon">📁</div>
                    <div class="folder-card-name">${escHtml(node.name)}</div>
                    <div class="folder-card-count">${count} file${count !== 1 ? 's' : ''}</div>
                </div>`;
            } else {
                const ext  = (node.extension || '').replace('.', '');
                const href = buildResourceHref(sourceKey, node.path);
                return `<a class="file-card" href="${escHtml(href)}" target="_blank" rel="noopener noreferrer">
                    <div class="file-card-icon">${getIcon(ext)}</div>
                    <div class="file-card-name">${escHtml(node.name)}</div>
                    <span class="file-card-ext ${extClass(ext)}">${ext || 'file'}</span>
                    <div class="file-card-actions">
                        <span class="file-action-btn btn-view"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true" width="15" height="15" style="flex-shrink:0;"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="17 8 12 3 7 8"/><line x1="12" y1="3" x2="12" y2="15"/></svg>Open</span>
                    </div>
                </a>`;
            }
        }).join('')}
    </div>`;
}

function renderFolderGrid(nodes, sourceKey) {
    const content = document.getElementById('resourcesContent');
    content.innerHTML = buildGridHtml(nodes, sourceKey) ||
        '<div class="empty-state"><div class="icon">📂</div><h3>Empty folder</h3><p>No files found here.</p></div>';
}

function navigateInto(node, sourceKey) {
    RS.currentPath.push({ label: node.name, node, source: sourceKey });
    RS.currentNode = node;
    renderBreadcrumb();
    renderFolderGrid(node.children || [], sourceKey);
}

// ── BREADCRUMB ──────────────────────────────────────────────────
function renderBreadcrumb() {
    const el  = document.getElementById('breadcrumb');
    if (!el)  return;
    const lib = RS.libraries[RS.activeLibIdx];
    let html  = `<a onclick="goHome()" style="cursor:pointer"><img src="/static/images/folder-icon.svg" alt="Library" style="width:20px;height:20px;display:inline;vertical-align:middle;margin-right:4px">${escHtml(lib?.title || 'Library')}</a>`;
    RS.currentPath.forEach((crumb, i) => {
        html += `<span class="breadcrumb-sep">/</span>`;
        if (i === RS.currentPath.length - 1) {
            html += `<span>${escHtml(crumb.label)}</span>`;
        } else {
            html += `<a onclick="goToCrumb(${i})" style="cursor:pointer">${escHtml(crumb.label)}</a>`;
        }
    });
    el.innerHTML = html;
}

function goHome() {
    RS.currentPath = [];
    RS.currentNode = null;
    renderBreadcrumb();
    renderMainContent();
}

function goToCrumb(idx) {
    const crumb    = RS.currentPath[idx];
    RS.currentPath = RS.currentPath.slice(0, idx + 1);
    RS.currentNode = crumb.node;
    renderBreadcrumb();
    renderFolderGrid(crumb.node.children || [], crumb.source);
}

// ── SEARCH ──────────────────────────────────────────────────────
let _searchTimer;
function handleSearch(query) {
    RS.searchQuery = query.trim().toLowerCase();
    clearTimeout(_searchTimer);
    _searchTimer = setTimeout(() => {
        RS.searchQuery.length < 2 ? goHome() : renderSearchResults();
    }, 280);
}

function renderSearchResults() {
    const q       = RS.searchQuery;
    const matches = RS.allFiles.filter(f =>
        f.name.toLowerCase().includes(q) ||
        f.subjectName.toLowerCase().includes(q) ||
        f.breadcrumb.toLowerCase().includes(q)
    );

    document.getElementById('breadcrumb').innerHTML =
        `<span>🔍 Results for <strong>"${escHtml(q)}"</strong></span>`;

    const content = document.getElementById('resourcesContent');

    if (!matches.length) {
        content.innerHTML = `<div class="empty-state"><div class="icon">🔍</div><h3>No results found</h3><p>Try a different search term.</p></div>`;
        return;
    }

    /* Each result is a proper <a> tag — opens directly in new tab */
    const rows = matches.slice(0, 60).map(f => {
        const href = buildResourceHref(f.sourceKey, f.path);
        return `<a class="result-row" href="${escHtml(href)}" target="_blank" rel="noopener noreferrer">
            <span class="result-row-icon">${getIcon(f.ext)}</span>
            <div class="result-row-info">
                <strong>${escHtml(f.name)}</strong>
                <span>${escHtml(f.subjectName)}${f.breadcrumb ? ' / ' + escHtml(f.breadcrumb) : ''} · ${escHtml(f.libraryTitle)}</span>
            </div>
            <span class="result-row-badge ${extClass(f.ext)}">${f.ext || 'file'}</span>
        </a>`;
    }).join('');

    content.innerHTML = `
        <div class="search-results-banner">
            Found <strong>${matches.length}</strong> file${matches.length !== 1 ? 's' : ''} matching "${escHtml(q)}"
        </div>
        ${rows}
        ${matches.length > 60 ? `<p style="text-align:center;color:#bbb;font-size:12.5px;padding:12px">Showing first 60 of ${matches.length} results.</p>` : ''}`;
}

// ── UPLOAD MODAL ────────────────────────────────────────────────
let uploadQueue = []; // [{file, status: 'pending'|'uploading'|'done'|'error', error}]

function openUploadModal() {
    uploadQueue = [];
    renderUploadQueue();
    document.getElementById('uploadQueue').style.display = 'none';
    document.getElementById('uploadModal').classList.remove('hidden');
}

function closeUploadModal() {
    document.getElementById('uploadModal').classList.add('hidden');
    uploadQueue = [];
}

function handleDragOver(e) {
    e.preventDefault();
    document.getElementById('uploadDropzone').classList.add('drag-over');
}
function handleDragLeave(e) {
    document.getElementById('uploadDropzone').classList.remove('drag-over');
}
function handleDrop(e) {
    e.preventDefault();
    document.getElementById('uploadDropzone').classList.remove('drag-over');
    handleUploadFiles(e.dataTransfer.files);
}

function handleUploadFiles(fileList) {
    if (!fileList?.length) return;
    const allowed = ['pdf','docx','doc','pptx','ppt','txt','md','png','jpg','jpeg'];

    Array.from(fileList).forEach(file => {
        const ext = file.name.split('.').pop().toLowerCase();
        if (!allowed.includes(ext)) {
            showStatus(`Skipped ${file.name}: unsupported type.`, 'error'); return;
        }
        if (file.size > 10 * 1024 * 1024) {
            showStatus(`Skipped ${file.name}: exceeds 10 MB.`, 'error'); return;
        }
        uploadQueue.push({ file, status: 'pending', error: null });
    });

    renderUploadQueue();
    document.getElementById('uploadQueue').style.display = uploadQueue.length ? '' : 'none';
}

function renderUploadQueue() {
    const list = document.getElementById('uploadQueueList');
    if (!list) return;
    list.innerHTML = uploadQueue.map((item, idx) => {
        const ext = item.file.name.split('.').pop().toLowerCase();
        const statusLabel = { pending:'Ready', uploading:'Uploading…', done:'✓ Uploaded', error:'✗ Failed' }[item.status] || '';
        return `<div class="upload-queue-item ${item.status}">
            <span class="upload-qi-icon">${getIcon(ext)}</span>
            <div class="upload-qi-info">
                <div class="upload-qi-name">${escHtml(item.file.name)}</div>
                <div class="upload-qi-size">${fmtBytes(item.file.size)}</div>
            </div>
            <span class="upload-qi-status ${item.status}">${statusLabel}${item.error ? ': ' + escHtml(item.error) : ''}</span>
            ${item.status === 'pending'
                ? `<button class="upload-qi-remove" onclick="removeFromQueue(${idx})" type="button" aria-label="Remove from queue"><img src="/static/images/cross-brown-icon.svg" alt="Remove" class="btn-icon-xs"></button>`
                : ''}
        </div>`;
    }).join('');
}

function removeFromQueue(idx) {
    uploadQueue.splice(idx, 1);
    renderUploadQueue();
    if (!uploadQueue.length) document.getElementById('uploadQueue').style.display = 'none';
}

function clearUploadQueue() {
    uploadQueue = [];
    renderUploadQueue();
    document.getElementById('uploadQueue').style.display = 'none';
    document.getElementById('uploadFileInput').value = '';
}

async function submitUploads() {
    const pending = uploadQueue.filter(i => i.status === 'pending');
    if (!pending.length) { showStatus('No files to upload.', 'info'); return; }

    const btn = document.getElementById('uploadSubmitBtn');
    if (btn) btn.disabled = true;

    let successCount = 0;

    for (const item of uploadQueue) {
        if (item.status !== 'pending') continue;
        item.status = 'uploading';
        renderUploadQueue();

        try {
            const fd = new FormData();
            fd.append('file', item.file);

            const res  = await fetch('/api/resources/upload', { method: 'POST', body: fd });
            const data = await res.json().catch(() => ({}));
            if (!res.ok) throw new Error(data.error || 'Upload failed');

            item.status = 'done';
            successCount++;
        } catch (err) {
            item.status = 'error';
            item.error  = err.message;
        }
        renderUploadQueue();
    }

    if (btn) btn.disabled = false;

    if (successCount > 0) {
        showStatus(`${successCount} file${successCount !== 1 ? 's' : ''} uploaded successfully!`, 'success');
        setTimeout(() => { closeUploadModal(); loadResources(); }, 1200);
    } else {
        showStatus('Upload failed. Please try again.', 'error');
    }
}

async function deleteUpload(filename) {
    if (!confirm(`Delete "${filename}"? This cannot be undone.`)) return;
    try {
        const res  = await fetch(`/api/resources/user-uploads/${encodeURIComponent(filename)}`, { method: 'DELETE' });
        const data = await res.json().catch(() => ({}));
        if (!res.ok) throw new Error(data.error || 'Delete failed');
        showStatus('File deleted.', 'success');
        loadResources();
    } catch (err) {
        showStatus(err.message, 'error');
    }
}

// ── UTILITIES ────────────────────────────────────────────────────
function showStatus(msg, type = 'info') {
    const el = document.getElementById('rsStatus');
    if (!el) return;
    el.textContent = msg; el.className = `status show ${type}`;
    clearTimeout(el._t);
    el._t = setTimeout(() => { el.className = 'status'; }, 4000);
}

function escHtml(v) {
    return String(v || '').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
}

function fmtBytes(b) {
    if (b < 1024) return b + ' B';
    if (b < 1048576) return (b / 1024).toFixed(1) + ' KB';
    return (b / 1048576).toFixed(1) + ' MB';
}