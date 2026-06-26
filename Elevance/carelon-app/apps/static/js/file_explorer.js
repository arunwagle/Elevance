/**
 * File Explorer — Two-panel layout: Folder Tree (left) + File List (right).
 *
 * Left panel: Lazy-loading folder tree with expand/collapse.
 * Right panel: Files for selected folder + inherited permission badges + action buttons.
 */
(function() {
    const VOLUME_ROOT = window.FILE_EXPLORER_CONFIG.volumeRoot;
    const IS_ADMIN = window.FILE_EXPLORER_CONFIG.isAdmin;

    // State
    let folderPermissions = {};   // { path: [actions] }  from /files/api/my-access
    let currentFolder = null;     // { path, actions }
    let currentFiles = [];
    let pendingDeletePath = '';
    let expandedNodes = new Set();

    // Retry config
    const MAX_RETRIES = 5;
    const BASE_DELAY_MS = 2000;

    // Client-side cache (shared for files + tree + my-access)
    const CACHE_TTL_MS = 90000;  // 90 seconds
    const _cache = {};

    function getCached(key) {
        const e = _cache[key];
        if (e && (Date.now() - e.ts) < CACHE_TTL_MS) return e.data;
        if (e) delete _cache[key];
        return null;
    }
    function setCache(key, data) { _cache[key] = { data, ts: Date.now() }; }
    function invalidateCache(key) {
        if (key) { delete _cache[key]; }
        else { Object.keys(_cache).forEach(k => delete _cache[k]); }
    }

    // DOM refs — Tree
    const treeContainer = document.getElementById('fe-tree-container');
    const treeRoot = document.getElementById('fe-tree-root');
    const treeLoading = document.getElementById('fe-tree-loading');
    const treeEmpty = document.getElementById('fe-tree-empty');
    const treeRefreshBtn = document.getElementById('fe-tree-refresh');

    // DOM refs — Files
    const breadcrumb = document.getElementById('fe-breadcrumb');
    const folderPerms = document.getElementById('fe-folder-perms');
    const placeholder = document.getElementById('fe-placeholder');
    const fileLoading = document.getElementById('fe-file-loading');
    const fileEmpty = document.getElementById('fe-file-empty');
    const fileTableWrap = document.getElementById('fe-file-table-wrap');
    const fileCount = document.getElementById('fe-file-count');
    const fileTbody = document.getElementById('fe-file-tbody');

    // DOM refs — Delete modal
    const deleteModal = document.getElementById('fe-delete-modal');
    const deleteFilename = document.getElementById('fe-delete-filename');
    const confirmDeleteBtn = document.getElementById('fe-confirm-delete');
    const cancelDeleteBtn = document.getElementById('fe-cancel-delete');

    // ======== Init ========
    async function init() {
        await loadUserAccess();
        treeRefreshBtn.addEventListener('click', () => {
            expandedNodes.clear();
            invalidateCache();  // Clear all caches on manual refresh
            loadUserAccess();
        });
        cancelDeleteBtn.addEventListener('click', () => deleteModal.classList.add('hidden'));
        confirmDeleteBtn.addEventListener('click', executeDelete);
    }

    // ======== Load User Access (permissions + build tree) ========
    async function loadUserAccess() {
        treeLoading.classList.remove('hidden');
        treeEmpty.classList.add('hidden');
        treeRoot.innerHTML = '';

        try {
            let data;
            const accessCacheKey = 'my-access';
            const cachedAccess = getCached(accessCacheKey);
            if (cachedAccess) {
                data = cachedAccess;
            } else {
                const resp = await fetch('/files/api/my-access');
                data = await resp.json();
                setCache(accessCacheKey, data);
            }
            const folders = data.folders || [];

            if (folders.length === 0) {
                treeLoading.classList.add('hidden');
                treeEmpty.classList.remove('hidden');
                return;
            }

            // Store permissions map
            folderPermissions = {};
            folders.forEach(f => { folderPermissions[f.path] = f.actions; });

            // Build tree
            if (IS_ADMIN) {
                // Admin: show root node with lazy-loaded children
                buildAdminTree(folders);
            } else {
                // Non-admin: flat list of permitted folders
                buildPermittedTree(folders);
            }

            treeLoading.classList.add('hidden');
        } catch (err) {
            treeLoading.innerHTML = `<span class="fe-tree-error">Failed to load: ${esc(err.message)}</span>`;
        }
    }

    // ======== Build Tree (Admin — hierarchical) ========
    function buildAdminTree(folders) {
        treeRoot.innerHTML = '';
        // Create root node
        const rootNode = createTreeNode({
            name: 'dxutility',
            path: VOLUME_ROOT,
            isRoot: true,
            has_children: true,
        });
        treeRoot.appendChild(rootNode);
        // Auto-expand root
        expandNode(rootNode, VOLUME_ROOT);
    }

    // ======== Build Tree (Non-admin — flat permitted) ========
    function buildPermittedTree(folders) {
        treeRoot.innerHTML = '';
        folders.forEach(f => {
            const node = createTreeNode({
                name: f.display_name,
                path: f.path,
                isRoot: false,
                has_children: true,
            });
            treeRoot.appendChild(node);
        });
    }

    // ======== Create a Tree Node DOM Element ========
    function createTreeNode({ name, path, isRoot, has_children }) {
        const li = document.createElement('li');
        li.className = 'fe-tree-node';
        li.dataset.path = path;

        const row = document.createElement('div');
        row.className = 'fe-tree-row';

        // Expand toggle
        const toggle = document.createElement('span');
        toggle.className = 'fe-tree-toggle';
        toggle.textContent = has_children ? '▶' : ' ';
        toggle.addEventListener('click', (e) => {
            e.stopPropagation();
            if (has_children) toggleNode(li, path);
        });

        // Folder icon + name
        const label = document.createElement('span');
        label.className = 'fe-tree-label';
        label.innerHTML = `<span class="fe-tree-icon">📁</span> ${esc(name)}`;

        // Permission dot indicator
        if (folderPermissions[path]) {
            const dot = document.createElement('span');
            dot.className = 'fe-tree-perm-dot';
            dot.title = folderPermissions[path].join(', ');
            label.appendChild(dot);
        }

        row.appendChild(toggle);
        row.appendChild(label);

        // Click row to select folder
        row.addEventListener('click', () => selectFolder(path));

        li.appendChild(row);

        // Children container (hidden until expanded)
        const childList = document.createElement('ul');
        childList.className = 'fe-tree-children hidden';
        li.appendChild(childList);

        return li;
    }

    // ======== Toggle (expand/collapse) ========
    function toggleNode(li, path) {
        const childList = li.querySelector(':scope > .fe-tree-children');
        const toggle = li.querySelector(':scope > .fe-tree-row > .fe-tree-toggle');

        if (expandedNodes.has(path)) {
            // Collapse
            childList.classList.add('hidden');
            toggle.textContent = '▶';
            expandedNodes.delete(path);
        } else {
            // Expand
            expandNode(li, path);
        }
    }

    async function expandNode(li, path) {
        const childList = li.querySelector(':scope > .fe-tree-children');
        const toggle = li.querySelector(':scope > .fe-tree-row > .fe-tree-toggle');

        toggle.textContent = '⏳';
        childList.innerHTML = '<li class="fe-tree-loading-child">Loading...</li>';
        childList.classList.remove('hidden');

        // Check tree cache first
        const cacheKey = 'tree:' + path;
        const cachedChildren = getCached(cacheKey);

        try {
            let children;
            if (cachedChildren) {
                children = cachedChildren;
            } else {
                const resp = await fetch(`/files/api/tree?path=${encodeURIComponent(path)}`);
                const data = await resp.json();
                children = data.children || [];
                setCache(cacheKey, children);
            }

            childList.innerHTML = '';
            if (children.length === 0) {
                toggle.textContent = '▶';
                childList.innerHTML = '<li class="fe-tree-no-children">No subfolders</li>';
            } else {
                toggle.textContent = '▼';
                children.forEach(child => {
                    const childNode = createTreeNode({
                        name: child.name,
                        path: child.path,
                        isRoot: false,
                        has_children: child.has_children,
                    });
                    childList.appendChild(childNode);
                });
            }
            expandedNodes.add(path);
        } catch (err) {
            toggle.textContent = '▶';
            childList.innerHTML = `<li class="fe-tree-error">${esc(err.message)}</li>`;
        }
    }

    // ======== Select Folder (load files in right panel) ========
    function selectFolder(path) {
        // Highlight selected node
        document.querySelectorAll('.fe-tree-row.selected').forEach(el => el.classList.remove('selected'));
        const node = document.querySelector(`.fe-tree-node[data-path="${CSS.escape(path)}"] > .fe-tree-row`);
        if (node) node.classList.add('selected');

        // Determine actions for this folder
        let actions;
        if (IS_ADMIN) {
            actions = ['browse', 'upload', 'download', 'delete', 'preview', 'detokenize', 'share'];
        } else {
            // Check exact match or parent folder permissions
            actions = folderPermissions[path] || findParentPermissions(path) || ['browse'];
        }

        currentFolder = { path, actions };

        // Update breadcrumb
        const relative = path.replace(VOLUME_ROOT + '/', '').replace(VOLUME_ROOT, '');
        const parts = relative ? relative.split('/') : ['Root'];
        breadcrumb.innerHTML = parts.map((p, i) => {
            const isLast = i === parts.length - 1;
            return `<span class="fe-bc-item${isLast ? ' active' : ''}">${esc(p || 'Root')}</span>`;
        }).join('<span class="fe-bc-sep">›</span>');

        // Show permission badges
        folderPerms.innerHTML = actions.map(a =>
            `<span class="fe-perm-badge">${esc(formatAction(a))}</span>`
        ).join('');

        // Load files
        loadFiles(path);
    }

    function findParentPermissions(path) {
        // Walk up to find the closest parent with permissions
        const parts = path.replace(VOLUME_ROOT + '/', '').split('/');
        while (parts.length > 0) {
            parts.pop();
            const parentPath = parts.length > 0 ? `${VOLUME_ROOT}/${parts.join('/')}` : VOLUME_ROOT;
            if (folderPermissions[parentPath]) return folderPermissions[parentPath];
        }
        return null;
    }

    // ======== Load Files (with retry on rate limit) ========
    async function loadFiles(folderPath, forceRefresh) {
        // Check cache
        if (!forceRefresh) {
            const cached = getCached(folderPath);
            if (cached) {
                renderFiles(cached.files, cached.subfolders);
                return;
            }
        }

        showFileState('loading');

        for (let attempt = 1; attempt <= MAX_RETRIES; attempt++) {
            try {
                const resp = await fetch(`/files/api/list?folder_path=${encodeURIComponent(folderPath)}`);
                const data = await resp.json();

                const isRateLimited = resp.status === 429 ||
                    (data.error && (data.error.includes('429') || data.error.includes('RATE') ||
                     data.error.includes('RESOURCE_EXHAUSTED') || data.error.includes('REQUEST_LIMIT')));

                if (isRateLimited) {
                    if (attempt < MAX_RETRIES) {
                        const waitSec = (BASE_DELAY_MS * attempt) / 1000;
                        fileLoading.innerHTML = `<span class="perm-spinner-inline"></span> Rate limit. Retrying in ${waitSec}s... (${attempt}/${MAX_RETRIES})`;
                        await sleep(BASE_DELAY_MS * attempt);
                        continue;
                    }
                    showFileState('empty', 'File service is busy. Please wait and try again.');
                    return;
                }

                if (data.error) {
                    showFileState('empty', data.error);
                    return;
                }

                const files = data.files || [];
                const subfolders = data.subfolders || [];
                setCache(folderPath, { files, subfolders });
                renderFiles(files, subfolders);
                return;

            } catch (err) {
                if (attempt < MAX_RETRIES) {
                    const waitSec = (BASE_DELAY_MS * attempt) / 1000;
                    fileLoading.innerHTML = `<span class="perm-spinner-inline"></span> Retrying in ${waitSec}s... (${attempt}/${MAX_RETRIES})`;
                    await sleep(BASE_DELAY_MS * attempt);
                    continue;
                }
            }
        }
        showFileState('empty', 'Unable to load files. Try again later.');
    }

    // ======== Render Files ========
    function renderFiles(files, subfolders) {
        if (files.length === 0 && subfolders.length === 0) {
            showFileState('empty', 'This folder is empty.');
            return;
        }

        showFileState('table');
        const actions = currentFolder ? currentFolder.actions : [];
        const totalItems = files.length + subfolders.length;
        fileCount.innerHTML = `${totalItems} item${totalItems !== 1 ? 's' : ''} <button class="fe-btn fe-btn-refresh" id="fe-refresh-files" title="Refresh">&#8635;</button>`;

        let rows = '';

        // Subfolders first
        subfolders.forEach(sf => {
            rows += `
                <tr class="fe-row-folder" data-path="${esc(sf.path)}">
                    <td class="fe-cell-icon">📁</td>
                    <td class="fe-cell-name"><a class="fe-folder-link" data-path="${esc(sf.path)}">${esc(sf.name)}</a></td>
                    <td class="fe-cell-size">—</td>
                    <td class="fe-cell-mod">${esc(sf.last_modified || '')}</td>
                    <td class="fe-cell-perms">${renderPermBadges(actions)}</td>
                    <td class="fe-cell-actions">—</td>
                </tr>`;
        });

        // Files
        files.forEach(f => {
            rows += `
                <tr class="fe-row-file">
                    <td class="fe-cell-icon">${getFileIcon(f.extension)}</td>
                    <td class="fe-cell-name">${esc(f.name)}</td>
                    <td class="fe-cell-size">${formatSize(f.size)}</td>
                    <td class="fe-cell-mod">${esc(f.last_modified || '')}</td>
                    <td class="fe-cell-perms">${renderPermBadges(actions)}</td>
                    <td class="fe-cell-actions">${buildActionBtns(f, actions)}</td>
                </tr>`;
        });

        fileTbody.innerHTML = rows;
        bindFileEvents();
    }

    function renderPermBadges(actions) {
        return actions.map(a => `<span class="fe-perm-badge fe-perm-${a}">${formatAction(a)}</span>`).join('');
    }

    function buildActionBtns(file, actions) {
        let html = '';
        if (actions.includes('download'))
            html += `<button class="fe-btn fe-btn-download" data-path="${esc(file.path)}" data-name="${esc(file.name)}">⬇</button>`;
        if (actions.includes('preview'))
            html += `<button class="fe-btn fe-btn-preview" data-path="${esc(file.path)}">👁</button>`;
        if (actions.includes('delete'))
            html += `<button class="fe-btn fe-btn-delete" data-path="${esc(file.path)}" data-name="${esc(file.name)}">🗑</button>`;
        return html || '—';
    }

    function bindFileEvents() {
        // Folder click → navigate into
        document.querySelectorAll('.fe-folder-link').forEach(el => {
            el.addEventListener('click', (e) => {
                e.preventDefault();
                const path = el.dataset.path;
                selectFolder(path);
                // Also expand in tree if visible
                const treeNode = document.querySelector(`.fe-tree-node[data-path="${CSS.escape(path)}"]`);
                if (treeNode && !expandedNodes.has(path)) toggleNode(treeNode, path);
            });
        });

        // Download
        document.querySelectorAll('.fe-btn-download').forEach(btn => {
            btn.addEventListener('click', () => {
                const a = document.createElement('a');
                a.href = `/files/api/download?file_path=${encodeURIComponent(btn.dataset.path)}`;
                a.download = btn.dataset.name;
                a.click();
            });
        });

        // Preview (placeholder)
        document.querySelectorAll('.fe-btn-preview').forEach(btn => {
            btn.addEventListener('click', () => {
                showToast('Preview coming soon');
            });
        });

        // Delete
        document.querySelectorAll('.fe-btn-delete').forEach(btn => {
            btn.addEventListener('click', () => {
                pendingDeletePath = btn.dataset.path;
                deleteFilename.textContent = btn.dataset.name;
                deleteModal.classList.remove('hidden');
            });
        });

        // Refresh button
        const refreshBtn = document.getElementById('fe-refresh-files');
        if (refreshBtn) {
            refreshBtn.addEventListener('click', () => {
                if (currentFolder) {
                    invalidateCache(currentFolder.path);
                    loadFiles(currentFolder.path, true);
                }
            });
        }
    }

    async function executeDelete() {
        deleteModal.classList.add('hidden');
        if (!pendingDeletePath) return;

        try {
            const resp = await fetch(`/files/api/delete?file_path=${encodeURIComponent(pendingDeletePath)}`, {
                method: 'DELETE',
            });
            if (resp.ok) {
                showToast('File deleted');
                if (currentFolder) {
                    invalidateCache(currentFolder.path);
                    loadFiles(currentFolder.path, true);
                }
            } else {
                const data = await resp.json();
                showToast(data.error || 'Delete failed', 'error');
            }
        } catch (err) {
            showToast(err.message, 'error');
        }
        pendingDeletePath = '';
    }

    // ======== UI State Helpers ========
    function showFileState(state, msg) {
        placeholder.classList.add('hidden');
        fileLoading.classList.add('hidden');
        fileEmpty.classList.add('hidden');
        fileTableWrap.classList.add('hidden');

        if (state === 'loading') {
            fileLoading.innerHTML = '<span class="perm-spinner-inline"></span> Loading files...';
            fileLoading.classList.remove('hidden');
        } else if (state === 'empty') {
            fileEmpty.textContent = msg || 'This folder is empty.';
            fileEmpty.classList.remove('hidden');
        } else if (state === 'table') {
            fileTableWrap.classList.remove('hidden');
        } else {
            placeholder.classList.remove('hidden');
        }
    }

    // ======== Utilities ========
    function sleep(ms) { return new Promise(r => setTimeout(r, ms)); }
    function esc(s) { const d = document.createElement('div'); d.textContent = s || ''; return d.innerHTML; }

    function formatAction(a) {
        return a.charAt(0).toUpperCase() + a.slice(1);
    }

    function formatSize(bytes) {
        if (!bytes || bytes === 0) return '—';
        if (bytes < 1024) return bytes + ' B';
        if (bytes < 1048576) return (bytes / 1024).toFixed(1) + ' KB';
        if (bytes < 1073741824) return (bytes / 1048576).toFixed(1) + ' MB';
        return (bytes / 1073741824).toFixed(2) + ' GB';
    }

    function getFileIcon(ext) {
        const icons = { csv: '📊', xlsx: '📊', xls: '📊', json: '📋', txt: '📝', dat: '📄', pdf: '📕', parquet: '🗃️' };
        return icons[ext] || '📄';
    }

    function showToast(msg, type) {
        let t = document.getElementById('fe-toast');
        if (!t) { t = document.createElement('div'); t.id = 'fe-toast'; t.className = 'fe-toast'; document.body.appendChild(t); }
        t.textContent = msg;
        t.className = `fe-toast ${type || 'success'} show`;
        setTimeout(() => t.classList.remove('show'), 3000);
    }

    // ======== Resizable Divider ========
    (function initResizer() {
        const divider = document.getElementById('fe-divider');
        const treePanel = document.getElementById('fe-tree-panel');
        if (!divider || !treePanel) return;

        let isResizing = false;
        let startX = 0;
        let startWidth = 0;

        divider.addEventListener('mousedown', (e) => {
            isResizing = true;
            startX = e.clientX;
            startWidth = treePanel.offsetWidth;
            document.body.style.cursor = 'col-resize';
            document.body.style.userSelect = 'none';
            e.preventDefault();
        });

        document.addEventListener('mousemove', (e) => {
            if (!isResizing) return;
            const delta = e.clientX - startX;
            const newWidth = Math.max(180, Math.min(500, startWidth + delta));
            treePanel.style.width = newWidth + 'px';
        });

        document.addEventListener('mouseup', () => {
            if (isResizing) {
                isResizing = false;
                document.body.style.cursor = '';
                document.body.style.userSelect = '';
            }
        });
    })();

    init();
})();
