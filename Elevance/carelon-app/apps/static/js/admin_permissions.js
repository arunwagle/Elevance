/**
 * Admin Permissions — File Permissions with folder browser + assignments table.
 * Includes loading spinner overlay for all async operations.
 */
(function() {
    // State
    let selectedFolder = null;       // {name, path}
    let selectedUsers = [];          // [{id, name, type}]
    let accessLevels = [];           // from permission_types API
    let allAssignments = [];         // loaded from API
    let searchTimeout = null;
    let currentBrowsePath = '';      // current subfolder in browser
    const VOLUME_ROOT = '/Volumes/aw_serverless_stable_catalog/carelon/dxutility';

    // DOM refs
    const folderDisplay = document.getElementById('folder-browser-display');
    const browseBtn = document.getElementById('btn-browse-folder');
    const modal = document.getElementById('folder-browser-modal');
    const closeBtn = document.getElementById('btn-close-browser');
    const cancelBtn = document.getElementById('btn-cancel-browse');
    const selectBtn = document.getElementById('btn-select-folder');
    const breadcrumb = document.getElementById('browser-breadcrumb');
    const browserList = document.getElementById('browser-list');
    const userInput = document.getElementById('user-search');
    const userDropdown = document.getElementById('user-dropdown');
    const selectedUsersEl = document.getElementById('selected-users');
    const accessGrid = document.getElementById('access-levels-grid');
    const selectAllCb = document.getElementById('select-all-access');
    const submitBtn = document.getElementById('btn-submit-perm');
    const clearBtn = document.getElementById('btn-clear-perm');
    const filterInput = document.getElementById('assignments-filter');
    const tbody = document.getElementById('assignments-tbody');

    // New Folder DOM refs
    const newFolderToggle = document.getElementById('btn-new-folder-toggle');
    const newFolderForm = document.getElementById('new-folder-form');
    const newFolderInput = document.getElementById('new-folder-name');
    const createFolderBtn = document.getElementById('btn-create-folder');
    const cancelNewFolderBtn = document.getElementById('btn-cancel-new-folder');
    const newFolderError = document.getElementById('new-folder-error');

    // ======== Loading Spinner ========
    let spinnerEl = null;

    function createSpinner() {
        if (spinnerEl) return;
        spinnerEl = document.createElement('div');
        spinnerEl.id = 'perm-loading-overlay';
        spinnerEl.className = 'perm-loading-overlay';
        spinnerEl.innerHTML = `
            <div class="perm-spinner-box">
                <div class="perm-spinner"></div>
                <p class="perm-spinner-msg" id="spinner-msg">Loading...</p>
            </div>
        `;
        document.body.appendChild(spinnerEl);
    }

    function showSpinner(msg) {
        createSpinner();
        const msgEl = document.getElementById('spinner-msg');
        if (msgEl) msgEl.textContent = msg || 'Loading...';
        spinnerEl.classList.add('visible');
    }

    function hideSpinner() {
        if (spinnerEl) spinnerEl.classList.remove('visible');
    }

    // ======== Init ========
    async function init() {
        showSpinner('Loading permissions...');
        try {
            await Promise.all([loadAccessLevels(), loadAssignments()]);
        } finally {
            hideSpinner();
        }
        setupEventListeners();
    }

    // ======== Folder Browser ========
    function openBrowser() {
        modal.classList.remove('hidden');
        currentBrowsePath = '';
        loadBrowserFolder('');
    }

    function closeBrowser() {
        modal.classList.add('hidden');
        hideNewFolderForm();
    }

    // ======== Create Folder ========
    function showNewFolderForm() {
        newFolderForm.classList.remove('hidden');
        newFolderToggle.classList.add('hidden');
        newFolderError.classList.add('hidden');
        newFolderInput.value = '';
        newFolderInput.focus();
    }

    function hideNewFolderForm() {
        newFolderForm.classList.add('hidden');
        newFolderToggle.classList.remove('hidden');
        newFolderError.classList.add('hidden');
        newFolderInput.value = '';
    }

    async function createFolder() {
        const folderName = newFolderInput.value.trim();
        if (!folderName) {
            showFolderError('Please enter a folder name');
            return;
        }

        // Validate name
        if (/[/\\:*?"<>|]/.test(folderName) || folderName === '..' || folderName === '.') {
            showFolderError('Invalid folder name. Avoid special characters.');
            return;
        }

        createFolderBtn.disabled = true;
        createFolderBtn.textContent = 'Creating...';
        newFolderError.classList.add('hidden');

        try {
            const resp = await fetch('/api/volumes/create-folder', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    volume_path: VOLUME_ROOT,
                    folder_name: folderName,
                    subfolder: currentBrowsePath,
                }),
            });
            const data = await resp.json();

            if (resp.ok && data.success) {
                hideNewFolderForm();
                showNotification(`Folder "${folderName}" created successfully`);
                // Refresh the current directory listing
                await loadBrowserFolder(currentBrowsePath);
            } else {
                showFolderError(data.error || 'Failed to create folder');
            }
        } catch (err) {
            showFolderError(`Error: ${err.message}`);
        } finally {
            createFolderBtn.disabled = false;
            createFolderBtn.textContent = 'Create';
        }
    }

    function showFolderError(msg) {
        newFolderError.textContent = msg;
        newFolderError.classList.remove('hidden');
    }

    async function loadBrowserFolder(subfolder) {
        currentBrowsePath = subfolder;
        browserList.innerHTML = '<div class="browser-loading">Loading...</div>';
        updateBreadcrumb(subfolder);
        selectBtn.disabled = false;  // Can always select current folder

        try {
            const params = new URLSearchParams({ volume_path: VOLUME_ROOT });
            if (subfolder) params.set('subfolder', subfolder);

            const resp = await fetch(`/api/volumes/browse?${params}`);
            const data = await resp.json();

            if (data.error) {
                browserList.innerHTML = `<div class="browser-empty">${esc(data.error)}</div>`;
                return;
            }

            const folders = (data.items || []).filter(i => i.is_directory);
            if (folders.length === 0) {
                browserList.innerHTML = '<div class="browser-empty">No subfolders — you can select this folder</div>';
                return;
            }

            browserList.innerHTML = folders.map(f => `
                <div class="browser-folder-item" data-name="${esc(f.name)}" data-path="${esc(f.path)}">
                    <span class="folder-icon">&#128194;</span>
                    <span class="folder-name">${esc(f.name)}</span>
                    <span class="folder-arrow">&rsaquo;</span>
                </div>
            `).join('');

            browserList.querySelectorAll('.browser-folder-item').forEach(item => {
                item.addEventListener('click', () => {
                    const name = item.dataset.name;
                    const newPath = currentBrowsePath ? `${currentBrowsePath}/${name}` : name;
                    loadBrowserFolder(newPath);
                });
            });
        } catch (err) {
            browserList.innerHTML = `<div class="browser-empty">${esc(err.message)}</div>`;
        }
    }

    function updateBreadcrumb(subfolder) {
        let html = '<span class="breadcrumb-item breadcrumb-root" data-path="">Root</span>';
        if (subfolder) {
            const parts = subfolder.split('/');
            let accumulated = '';
            parts.forEach((part, i) => {
                accumulated = accumulated ? `${accumulated}/${part}` : part;
                html += ` <span class="breadcrumb-sep">&rsaquo;</span> <span class="breadcrumb-item" data-path="${esc(accumulated)}">${esc(part)}</span>`;
            });
        }
        breadcrumb.innerHTML = html;

        breadcrumb.querySelectorAll('.breadcrumb-item').forEach(item => {
            item.addEventListener('click', () => {
                loadBrowserFolder(item.dataset.path);
            });
        });
    }

    function selectCurrentFolder() {
        const fullPath = currentBrowsePath
            ? `${VOLUME_ROOT}/${currentBrowsePath}`
            : VOLUME_ROOT;
        const displayName = currentBrowsePath || 'Root (all folders)';

        selectedFolder = { name: displayName, path: fullPath };
        folderDisplay.innerHTML = `
            <span class="folder-selected-path">${esc(displayName)}</span>
            <button class="chip-remove" id="clear-folder-btn">&times;</button>
        `;
        document.getElementById('clear-folder-btn').addEventListener('click', (e) => {
            e.stopPropagation();
            selectedFolder = null;
            folderDisplay.innerHTML = '<span class="folder-placeholder">No folder selected</span>';
            updateSubmitState();
        });
        closeBrowser();
        updateSubmitState();
    }

    // ======== Load Access Levels ========
    async function loadAccessLevels() {
        try {
            const resp = await fetch('/admin/permissions/types');
            const data = await resp.json();
            const fileTypes = (data.types || {}).files || [];
            accessLevels = fileTypes;
            renderAccessCheckboxes(fileTypes);
        } catch (err) {
            console.error('Failed to load access levels:', err);
        }
    }

    function renderAccessCheckboxes(types) {
        accessGrid.querySelectorAll('.access-cb:not(.select-all-cb)').forEach(el => el.remove());
        types.forEach(t => {
            const label = document.createElement('label');
            label.className = 'access-cb';
            label.innerHTML = `<input type="checkbox" value="${esc(t.action)}" class="access-checkbox"> ${esc(t.display_name)}`;
            label.title = t.description || '';
            accessGrid.appendChild(label);
        });
    }

    // ======== User Search ========
    async function searchUsers(query) {
        try {
            const resp = await fetch(`/admin/users/search?q=${encodeURIComponent(query)}&type=all`);
            const data = await resp.json();
            renderUserDropdown(data.results || []);
        } catch (err) {
            userDropdown.innerHTML = '<div class="typeahead-item typeahead-error">Search failed</div>';
            userDropdown.classList.remove('hidden');
        }
    }

    function renderUserDropdown(results) {
        if (results.length === 0) {
            userDropdown.innerHTML = '<div class="typeahead-item typeahead-empty">No results</div>';
        } else {
            userDropdown.innerHTML = results.map(r => `
                <div class="typeahead-item" data-id="${esc(r.id)}" data-name="${esc(r.name)}" data-type="${r.type}" data-email="${esc(r.email || '')}">
                    <span class="entity-type-badge ${r.type}">${getIcon(r.type)}</span>
                    <span class="entity-name">${esc(r.name)}</span>
                    ${r.email ? '<span class="entity-email">' + esc(r.email) + '</span>' : ''}
                </div>
            `).join('');
        }
        userDropdown.classList.remove('hidden');

        userDropdown.querySelectorAll('.typeahead-item[data-id]').forEach(item => {
            item.addEventListener('click', () => {
                const user = { id: item.dataset.id, name: item.dataset.name, type: item.dataset.type, email: item.dataset.email || '' };
                if (!selectedUsers.find(u => u.id === user.id)) {
                    selectedUsers.push(user);
                    renderSelectedUsers();
                }
                userDropdown.classList.add('hidden');
                userInput.value = '';
                updateSubmitState();
            });
        });
    }

    function renderSelectedUsers() {
        selectedUsersEl.innerHTML = selectedUsers.map((u, i) => `
            <span class="entity-chip ${u.type}">
                ${getIcon(u.type)} ${esc(u.name)}
                <button class="chip-remove" data-idx="${i}">&times;</button>
            </span>
        `).join('');
        selectedUsersEl.querySelectorAll('.chip-remove').forEach(btn => {
            btn.addEventListener('click', () => {
                selectedUsers.splice(parseInt(btn.dataset.idx), 1);
                renderSelectedUsers();
                updateSubmitState();
            });
        });
    }

    // ======== Submit ========
    async function handleSubmit() {
        const requestType = document.querySelector('input[name="request_type"]:checked').value;
        const checkedActions = [...document.querySelectorAll('.access-checkbox:checked')].map(cb => cb.value);

        if (!selectedFolder || selectedUsers.length === 0 || checkedActions.length === 0) return;

        submitBtn.disabled = true;
        const actionLabel = requestType === 'add' ? 'Assigning permissions...' : 'Revoking permissions...';
        showSpinner(actionLabel);

        try {
            if (requestType === 'add') {
                const resp = await fetch('/admin/permissions/assign', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        entities: selectedUsers,
                        permission_category: 'files',
                        actions: checkedActions,
                        resource_path: selectedFolder.path,
                    }),
                });
                const result = await resp.json();
                if (resp.ok) {
                    showNotification(`Assigned ${result.count} permissions`);
                } else {
                    showNotification(result.error || 'Failed', 'error');
                }
            } else {
                let revoked = 0;
                for (const user of selectedUsers) {
                    for (const action of checkedActions) {
                        const resp = await fetch('/admin/permissions/revoke', {
                            method: 'POST',
                            headers: { 'Content-Type': 'application/json' },
                            body: JSON.stringify({
                                entity_id: user.id,
                                permission_category: 'files',
                                action: action,
                                resource_path: selectedFolder.path,
                            }),
                        });
                        if (resp.ok) revoked++;
                    }
                }
                showNotification(`Revoked ${revoked} permissions`);
            }
            showSpinner('Refreshing assignments...');
            await loadAssignments();
            clearForm();
        } catch (err) {
            showNotification(err.message, 'error');
        } finally {
            hideSpinner();
            submitBtn.disabled = false;
            submitBtn.textContent = 'Submit';
        }
    }

    // ======== Load Assignments ========
    async function loadAssignments() {
        try {
            const resp = await fetch('/admin/permissions/assignments?category=files');
            const data = await resp.json();
            const assignments = data.assignments || {};

            allAssignments = [];
            Object.entries(assignments).forEach(([action, entities]) => {
                entities.forEach(e => {
                    let existing = allAssignments.find(
                        r => r.entity_id === e.id && r.resource_path === (e.resource_path || '')
                    );
                    if (existing) {
                        existing.actions.push(action);
                    } else {
                        allAssignments.push({
                            entity_id: e.id,
                            entity_name: e.name,
                            entity_type: e.type,
                            resource_path: e.resource_path || '',
                            actions: [action],
                        });
                    }
                });
            });

            renderAssignmentsTable(allAssignments);
        } catch (err) {
            tbody.innerHTML = `<tr><td colspan="6" class="loading-row">Failed: ${esc(err.message)}</td></tr>`;
        }
    }

    function renderAssignmentsTable(rows, filter) {
        let filtered = rows;
        if (filter) {
            const q = filter.toLowerCase();
            filtered = rows.filter(r =>
                r.entity_name.toLowerCase().includes(q) ||
                r.resource_path.toLowerCase().includes(q)
            );
        }

        if (filtered.length === 0) {
            tbody.innerHTML = '<tr><td colspan="6" class="loading-row">No assignments found</td></tr>';
            return;
        }

        tbody.innerHTML = filtered.map(r => {
            const folderDisplay = r.resource_path
                ? r.resource_path.replace(VOLUME_ROOT + '/', '').replace(VOLUME_ROOT, 'Root')
                : '<em>All folders</em>';
            const actionBadges = r.actions.map(a => {
                const level = accessLevels.find(l => l.action === a);
                return `<span class="action-badge">${level ? level.display_name : a}</span>`;
            }).join(' ');

            return `
                <tr>
                    <td><span class="entity-type-badge ${r.entity_type}">${getIcon(r.entity_type)}</span> ${esc(r.entity_name)}</td>
                    <td><span class="type-label ${r.entity_type}">${r.entity_type}</span></td>
                    <td>${folderDisplay}</td>
                    <td>${actionBadges}</td>
                    <td>&mdash;</td>
                    <td><button class="btn-revoke-table" data-entity="${esc(r.entity_id)}" data-name="${esc(r.entity_name)}" data-folder="${esc(r.resource_path)}" data-actions='${JSON.stringify(r.actions)}'>Revoke All</button></td>
                </tr>
            `;
        }).join('');

        tbody.querySelectorAll('.btn-revoke-table').forEach(btn => {
            btn.addEventListener('click', async () => {
                const entityId = btn.dataset.entity;
                const entityName = btn.dataset.name;
                const folder = btn.dataset.folder;
                const actions = JSON.parse(btn.dataset.actions);
                btn.disabled = true;
                btn.textContent = 'Revoking...';
                showSpinner(`Revoking access for ${entityName}...`);
                try {
                    for (const action of actions) {
                        await fetch('/admin/permissions/revoke', {
                            method: 'POST',
                            headers: { 'Content-Type': 'application/json' },
                            body: JSON.stringify({ entity_id: entityId, permission_category: 'files', action, resource_path: folder }),
                        });
                    }
                    showNotification('Revoked successfully');
                    await loadAssignments();
                } finally {
                    hideSpinner();
                }
            });
        });
    }

    // ======== Event Listeners ========
    function setupEventListeners() {
        // Folder browser
        browseBtn.addEventListener('click', openBrowser);
        folderDisplay.addEventListener('click', openBrowser);
        closeBtn.addEventListener('click', closeBrowser);
        cancelBtn.addEventListener('click', closeBrowser);
        selectBtn.addEventListener('click', selectCurrentFolder);

        // New Folder
        newFolderToggle.addEventListener('click', showNewFolderForm);
        cancelNewFolderBtn.addEventListener('click', hideNewFolderForm);
        createFolderBtn.addEventListener('click', createFolder);
        newFolderInput.addEventListener('keydown', (e) => {
            if (e.key === 'Enter') createFolder();
            if (e.key === 'Escape') hideNewFolderForm();
        });

        // User search
        userInput.addEventListener('input', () => {
            clearTimeout(searchTimeout);
            const q = userInput.value.trim();
            if (q.length < 2) { userDropdown.classList.add('hidden'); return; }
            searchTimeout = setTimeout(() => searchUsers(q), 350);
        });

        // Close dropdowns on outside click
        document.addEventListener('click', (e) => {
            if (!userInput.contains(e.target) && !userDropdown.contains(e.target)) userDropdown.classList.add('hidden');
        });

        // Select All checkbox
        selectAllCb.addEventListener('change', () => {
            document.querySelectorAll('.access-checkbox').forEach(cb => { cb.checked = selectAllCb.checked; });
            updateSubmitState();
        });

        accessGrid.addEventListener('change', (e) => {
            if (e.target.classList.contains('access-checkbox')) {
                const allCbs = document.querySelectorAll('.access-checkbox');
                selectAllCb.checked = [...allCbs].every(cb => cb.checked);
                updateSubmitState();
            }
        });

        submitBtn.addEventListener('click', handleSubmit);
        clearBtn.addEventListener('click', clearForm);

        filterInput.addEventListener('input', () => {
            renderAssignmentsTable(allAssignments, filterInput.value.trim());
        });
    }

    // ======== Helpers ========
    function updateSubmitState() {
        const hasFolder = !!selectedFolder;
        const hasUsers = selectedUsers.length > 0;
        const hasActions = document.querySelectorAll('.access-checkbox:checked').length > 0;
        submitBtn.disabled = !(hasFolder && hasUsers && hasActions);
    }

    function clearForm() {
        selectedFolder = null;
        selectedUsers = [];
        folderDisplay.innerHTML = '<span class="folder-placeholder">No folder selected</span>';
        selectedUsersEl.innerHTML = '';
        userInput.value = '';
        document.querySelectorAll('.access-checkbox').forEach(cb => { cb.checked = false; });
        selectAllCb.checked = false;
        updateSubmitState();
    }

    function getIcon(type) {
        if (type === 'user') return '&#128100;';
        if (type === 'service_principal') return '&#129302;';
        return '&#128101;';
    }

    function showNotification(msg, type) {
        let n = document.getElementById('perm-notification');
        if (!n) { n = document.createElement('div'); n.id = 'perm-notification'; n.className = 'perm-notification'; document.body.appendChild(n); }
        n.textContent = (type === 'error' ? 'Error: ' : '') + msg;
        n.className = `perm-notification ${type || 'success'} show`;
        setTimeout(() => n.classList.remove('show'), 3000);
    }

    function esc(str) { const d = document.createElement('div'); d.textContent = str || ''; return d.innerHTML; }

    init();
})();
