/* ================================================================
   resources.js  –  Dusty Resource Library
   File explorer: tree sidebar, breadcrumb, grid view, search
   Pulls from /api/resources, opens files via /resource endpoint
   ================================================================ */

const RS = {
    libraries: [],          // raw API data
    activeLibIdx: 0,        // which library tab is selected
    currentPath: [],        // breadcrumb stack: [{label, node}]
    currentNode: null,      // current folder node being displayed
    searchQuery: '',
    allFiles: [],           // flat list for search
};

let SUBJECT_NAME_COLOURS = {};

function normaliseSubjectName(name) {
    return String(name || '')
        .toLowerCase()
        .replace(/&/g, 'and')
        .replace(/[^a-z0-9]+/g, ' ')
        .trim();
}

function resolveSubjectColour(subjectName) {
    const fallback = window.getSubjectColour?.('orange') || '#f5761c';
    if (!subjectName) return fallback;
    if (SUBJECT_NAME_COLOURS[subjectName]) return SUBJECT_NAME_COLOURS[subjectName];

    const target = normaliseSubjectName(subjectName);
    if (SUBJECT_NAME_COLOURS[target]) return SUBJECT_NAME_COLOURS[target];

    const aliases = {
        maths: 'mathematics',
        math: 'mathematics',
        physics: 'science',
        chemistry: 'science',
        biology: 'science',
        english: 'english',
        humanities: 'humanities',
        software: 'software engineering',
    };

    for (const [name, colour] of Object.entries(SUBJECT_NAME_COLOURS)) {
        const key = normaliseSubjectName(name);
        if (target === key || target.includes(key) || key.includes(target)) return colour;
        for (const [needle, alias] of Object.entries(aliases)) {
            if (target.includes(needle) && key.includes(alias)) return colour;
        }
    }

    return fallback;
}

const EXT_ICONS = {
    pdf: '📄', docx: '📝', doc: '📝', pptx: '📊', ppt: '📊',
    xlsx: '📈', xls: '📈', csv: '📈', txt: '📃', md: '📃',
    png: '🖼', jpg: '🖼', jpeg: '🖼', gif: '🖼',
    mp4: '🎬', mp3: '🎵',
};

function getIcon(ext) { return EXT_ICONS[ext] || '📎'; }

function extClass(ext) {
    const map = { pdf:'ext-pdf', docx:'ext-docx', doc:'ext-doc', pptx:'ext-pptx', ppt:'ext-ppt', xlsx:'ext-xlsx', csv:'ext-csv', txt:'ext-txt', md:'ext-md' };
    return map[ext] || 'ext-default';
}

// ── INIT ──────────────────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', loadResources);

async function loadResources() {
    try {
        const [res, subjRes] = await Promise.all([
            fetch('/api/resources'),
            fetch('/api/subjects'),
        ]);
        const data = await res.json();
        const subjData = await subjRes.json().catch(() => ({}));
        if (!res.ok) throw new Error(data.error || 'Could not load resources');

        if (subjRes.ok && Array.isArray(subjData.subjects)) {
            SUBJECT_NAME_COLOURS = {};
            subjData.subjects.forEach(subject => {
                const colour = window.getSubjectColour
                    ? window.getSubjectColour(subject.colourScheme || 'orange')
                    : window.SUBJECT_COLOURS?.[subject.colourScheme] || '#f5761c';
                SUBJECT_NAME_COLOURS[subject.subjectName] = colour;
                SUBJECT_NAME_COLOURS[normaliseSubjectName(subject.subjectName)] = colour;
            });
        }

        RS.libraries = data.libraries || [];
        RS.allFiles = buildFlatFileList(RS.libraries);

        renderLibraryTabs();
        renderTree();
        renderMainContent();
        showStatus(`${RS.allFiles.length} files loaded.`, 'success');
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

// ── FLAT FILE LIST (for search) ───────────────────────────────────
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
                name: node.name,
                path: node.path,
                ext: (node.extension || '').replace('.', ''),
                sourceKey: lib.source_key,
                libraryTitle: lib.title,
                subjectName,
                breadcrumb: pathStack.join(' / '),
            });
        } else if (node.type === 'directory') {
            walkNodes(node.children || [], [...pathStack, node.name], lib, subjectName, out);
        }
    });
}

// ── LIBRARY TABS ──────────────────────────────────────────────────
function renderLibraryTabs() {
    const el = document.getElementById('libraryTabs');
    if (!el) return;
    if (!RS.libraries.length) { el.innerHTML = ''; return; }
    el.innerHTML = RS.libraries.map((lib, i) => `
        <button class="lib-tab ${i === RS.activeLibIdx ? 'active' : ''}"
                onclick="switchLibrary(${i})">${escHtml(lib.title)}</button>
    `).join('');
}

function switchLibrary(idx) {
    RS.activeLibIdx = idx;
    RS.currentPath = [];
    RS.currentNode = null;
    renderLibraryTabs();
    renderTree();
    renderMainContent();
}

// ── TREE SIDEBAR ──────────────────────────────────────────────────
function renderTree() {
    const el = document.getElementById('treeScroll');
    if (!el) return;
    const lib = RS.libraries[RS.activeLibIdx];
    if (!lib) { el.innerHTML = '<div style="padding:20px;color:#bbb;text-align:center;font-size:13px">No libraries found.</div>'; return; }

    el.innerHTML = lib.subjects.map(subj => renderTreeSubject(subj, lib)).join('');
}

function renderTreeSubject(subj, lib) {
    const dot = resolveSubjectColour(subj.name);
    const childrenHtml = renderTreeNodes(subj.tree || [], lib.source_key, 1, dot);
    return `
        <div class="tree-node">
            <div class="tree-folder-row open tree-folder-depth-0"
                 onclick="toggleFolder(this)"
                 data-subject="${escHtml(subj.name)}" data-source="${lib.source_key}">
                <span class="tree-folder-icon" style="color:${dot}">▶</span>
                <span class="tree-folder-label" style="color:#22140b;font-size:13.5px">${escHtml(subj.name)}</span>
            </div>
            <div class="tree-children visible">
                ${childrenHtml}
            </div>
        </div>`;
}

function renderTreeNodes(nodes, sourceKey, depth, subjectColour) {
    return (nodes || []).map(node => {
        if (node.type === 'directory') {
            const children = renderTreeNodes(node.children || [], sourceKey, depth + 1, subjectColour);
            const count = countFiles(node);
            return `
                <div class="tree-node tree-folder-depth-${Math.min(depth,3)}">
                    <div class="tree-folder-row"
                         onclick="treeOpenFolder(this, event)"
                         style="--tree-subject-colour:${subjectColour || resolveSubjectColour(node.name)}"
                         data-name="${escHtml(node.name)}"
                         data-path="${escHtml(node.path)}"
                         data-source="${sourceKey}">
                        <span class="tree-folder-icon">▶</span>
                        <span class="tree-folder-label">${escHtml(node.name)}</span>
                        <span class="tree-folder-count">${count}</span>
                    </div>
                    <div class="tree-children">${children}</div>
                </div>`;
        } else {
            const ext = (node.extension || '').replace('.', '');
            const href = `/resource?source=${encodeURIComponent(sourceKey)}&path=${encodeURIComponent(node.path)}`;
            return `
                <div class="tree-file-row depth-${Math.min(depth+1,4)}"
                     onclick="treeOpenFile(this, '${escHtml(href)}', '${escHtml(node.name)}')"
                     data-href="${escHtml(href)}">
                    <span class="tree-file-icon">${getIcon(ext)}</span>
                    <span class="tree-file-name">${escHtml(node.name)}</span>
                    <span class="tree-file-ext ${extClass(ext)}">${ext || 'file'}</span>
                </div>`;
        }
    }).join('');
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
    // toggle tree children
    const children = row.nextElementSibling;
    if (children) {
        const open = children.classList.toggle('visible');
        row.classList.toggle('open', open);
    }
    // navigate main content to this folder
    const lib = RS.libraries[RS.activeLibIdx];
    if (!lib) return;
    const path = row.dataset.path;
    const name = row.dataset.name;
    const source = row.dataset.source;
    // find node
    let found = null;
    lib.subjects.forEach(s => { if (!found) found = findNodeByPath(s.tree, path); });
    if (found) {
        RS.currentNode = found;
        RS.currentPath = buildBreadcrumbForPath(lib, path);
        renderBreadcrumb();
        renderFolderGrid(found.children || [], source);
    }
}

function treeOpenFile(row, href, name) {
    document.querySelectorAll('.tree-file-row.active').forEach(r => r.classList.remove('active'));
    row.classList.add('active');
    window.open(href, '_blank', 'noopener noreferrer');
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
    const parts = targetPath.split('/');
    const crumbs = [];
    let nodes = [];
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

// ── MAIN CONTENT ──────────────────────────────────────────────────
function renderMainContent() {
    const lib = RS.libraries[RS.activeLibIdx];
    if (!lib) {
        document.getElementById('resourcesContent').innerHTML = `
            <div class="empty-state"><div class="icon">📂</div><h3>No libraries found</h3><p>Run the ingestion agent to populate your resource library.</p></div>`;
        return;
    }
    RS.currentPath = [];
    RS.currentNode = null;
    renderBreadcrumb();

    const content = document.getElementById('resourcesContent');
    content.innerHTML = lib.subjects.map((subj, si) => {
        const dot = SUBJECT_NAME_COLOURS[subj.name] || window.getSubjectColour?.('orange') || '#f5761c';
        const topNodes = subj.tree || [];
        const gridHtml = buildGridHtml(topNodes, lib.source_key);
        return `
            <div class="subject-section">
                <div class="library-heading">
                    <h2>${escHtml(subj.name)}</h2>
                    <span class="lib-badge">${lib.title}</span>
                </div>
                ${gridHtml || '<p style="color:#bbb;font-size:14px;padding:8px 0">No files in this subject yet.</p>'}
            </div>`;
    }).join('');
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
                const ext = (node.extension || '').replace('.', '');
                const href = `/resource?source=${encodeURIComponent(sourceKey)}&path=${encodeURIComponent(node.path)}`;
                return `<div class="file-card">
                    <div class="file-card-icon">${getIcon(ext)}</div>
                    <div class="file-card-name">${escHtml(node.name)}</div>
                    <span class="file-card-ext ${extClass(ext)}">${ext || 'file'}</span>
                    <div class="file-card-actions">
                        <button class="file-action-btn btn-view" onclick="openFile('${escHtml(href)}')">Open</button>
                    </div>
                </div>`;
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

function openFile(href) {
    window.open(href, '_blank', 'noopener noreferrer');
}

// ── BREADCRUMB ────────────────────────────────────────────────────
function renderBreadcrumb() {
    const el = document.getElementById('breadcrumb');
    if (!el) return;
    const lib = RS.libraries[RS.activeLibIdx];
    let html = `<a onclick="goHome()">📁 ${escHtml(lib?.title || 'Library')}</a>`;
    RS.currentPath.forEach((crumb, i) => {
        html += `<span class="breadcrumb-sep">/</span>`;
        if (i === RS.currentPath.length - 1) {
            html += `<span>${escHtml(crumb.label)}</span>`;
        } else {
            html += `<a onclick="goToCrumb(${i})">${escHtml(crumb.label)}</a>`;
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
    const crumb = RS.currentPath[idx];
    RS.currentPath = RS.currentPath.slice(0, idx + 1);
    RS.currentNode = crumb.node;
    renderBreadcrumb();
    renderFolderGrid(crumb.node.children || [], crumb.source);
}

// ── SEARCH ────────────────────────────────────────────────────────
let _searchTimer;
function handleSearch(query) {
    RS.searchQuery = query.trim().toLowerCase();
    clearTimeout(_searchTimer);
    _searchTimer = setTimeout(() => {
        if (RS.searchQuery.length < 2) {
            goHome();
        } else {
            renderSearchResults();
        }
    }, 280);
}

function renderSearchResults() {
    const q = RS.searchQuery;
    const matches = RS.allFiles.filter(f =>
        f.name.toLowerCase().includes(q) ||
        f.subjectName.toLowerCase().includes(q) ||
        f.breadcrumb.toLowerCase().includes(q)
    );

    const content = document.getElementById('resourcesContent');
    document.getElementById('breadcrumb').innerHTML = `<span>🔍 Search results for "<strong>${escHtml(q)}</strong>"</span>`;

    if (!matches.length) {
        content.innerHTML = `<div class="empty-state"><div class="icon">🔍</div><h3>No results found</h3><p>Try a different search term.</p></div>`;
        return;
    }

    content.innerHTML = `
        <div class="search-results-banner">
            🔍 Found <strong>${matches.length}</strong> file${matches.length !== 1 ? 's' : ''} matching "${escHtml(q)}"
        </div>
        ${matches.slice(0, 60).map(f => {
            const href = `/resource?source=${encodeURIComponent(f.sourceKey)}&path=${encodeURIComponent(f.path)}`;
            return `<a class="result-row" href="${escHtml(href)}" target="_blank" rel="noopener noreferrer">
                <span class="result-row-icon">${getIcon(f.ext)}</span>
                <div class="result-row-info">
                    <strong>${escHtml(f.name)}</strong>
                    <span>${escHtml(f.subjectName)}${f.breadcrumb ? ' / ' + escHtml(f.breadcrumb) : ''} · ${escHtml(f.libraryTitle)}</span>
                </div>
                <span class="result-row-badge ${extClass(f.ext)}">${f.ext || 'file'}</span>
            </a>`;
        }).join('')}
        ${matches.length > 60 ? `<p style="text-align:center;color:#bbb;font-size:13px;padding:12px">Showing first 60 of ${matches.length} results. Refine your search to narrow down.</p>` : ''}
    `;
}

// ── UTILS ─────────────────────────────────────────────────────────
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
