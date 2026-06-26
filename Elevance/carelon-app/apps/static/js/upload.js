/**
 * Upload Wizard — 5-step: Data File → Processing Template → Parsed Preview (PHI) → Protegrity → Target Folder
 */
(function() {
    // ======== State ========
    let currentStep = 1;
    const TOTAL_STEPS = 5;

    let selectedDataFile = null;
    let selectedProcTemplate = null;
    let selectedProtegrity = null;
    let selectedFolderPath = '';

    // Processing template state
    let procWorkbook = null;
    let procSheetNames = [];
    let procSelectedSheet = '';

    // Parsed data state (Step 3)
    let phiColumnIndices = [];   // indices of PHI columns in the data file
    let phiColumnNames = [];     // names of PHI columns
    let phiColumnTypes = [];     // PHI type per column (from template: 'SSN', 'DOB', 'Name', etc.)
    let parsedHeaders = [];      // column headers from parsing
    let parsedDataRows = [];     // all parsed rows (array of arrays)

    // ======== DOM Refs ========
    const form = document.getElementById('upload-form');
    const btnPrev = document.getElementById('btn-prev');
    const btnNext = document.getElementById('btn-next');
    const btnUpload = document.getElementById('btn-upload');
    const stepIndicators = document.querySelectorAll('.wizard-step');
    const panels = document.querySelectorAll('.wizard-panel');

    // Step 1
    const dataFileInput = document.getElementById('data-file-input');
    const dropZoneData = document.getElementById('drop-zone-data');
    const dataFileInfo = document.getElementById('data-file-info');
    const dataFileName = document.getElementById('data-file-name');
    const dataFileSize = document.getElementById('data-file-size');
    const btnClearData = document.getElementById('btn-clear-data');

    // Step 2
    const procInput = document.getElementById('proc-template-input');
    const dropZoneProc = document.getElementById('drop-zone-proc');
    const procFileInfo = document.getElementById('proc-file-info');
    const procFileName = document.getElementById('proc-file-name');
    const procFileSize = document.getElementById('proc-file-size');
    const btnClearProc = document.getElementById('btn-clear-proc');
    const procSheetSelector = document.getElementById('proc-sheet-selector');
    const procSheetCount = document.getElementById('proc-sheet-count');
    const procSheetTabs = document.getElementById('proc-sheet-tabs');
    const procSelectedSheetInput = document.getElementById('proc-selected-sheet');
    const previewTemplate = document.getElementById('preview-template');
    const templatePreviewMeta = document.getElementById('template-preview-meta');
    const templatePreviewThead = document.getElementById('template-preview-thead');
    const templatePreviewTbody = document.getElementById('template-preview-tbody');

    // Step 3
    const phiLegend = document.getElementById('phi-legend');
    const phiCountEl = document.getElementById('phi-count');
    const parsedDataMeta = document.getElementById('parsed-data-meta');
    const parsedDataThead = document.getElementById('parsed-data-thead');
    const parsedDataTbody = document.getElementById('parsed-data-tbody');
    const previewParsedData = document.getElementById('preview-parsed-data');

    // Step 4
    const protegrityInput = document.getElementById('protegrity-template-input');
    const dropZoneProtegrity = document.getElementById('drop-zone-protegrity');
    const protegrityFileInfo = document.getElementById('protegrity-file-info');
    const protegrityFileName = document.getElementById('protegrity-file-name');
    const protegrityFileSize = document.getElementById('protegrity-file-size');
    const btnClearProtegrity = document.getElementById('btn-clear-protegrity');
    const previewTokenized = document.getElementById('preview-tokenized');

    // Step 5 — Permitted Folders
    const volumePathInput = document.getElementById('volume-path-input');
    const permFoldersList = document.getElementById('permitted-folders-list');
    const permFoldersLoading = document.getElementById('permitted-folders-loading');
    const permFoldersEmpty = document.getElementById('permitted-folders-empty');

    // ======== Wizard Navigation ========
    function goToStep(step) {
        if (step < 1 || step > TOTAL_STEPS) return;

        // When entering Step 3, build the parsed preview
        if (step === 3 && currentStep === 2) {
            buildParsedPreview();
        }

        // When entering Step 5, load permitted folders
        if (step === 5) {
            loadPermittedFolders();
        }

        currentStep = step;

        panels.forEach(p => { p.classList.add('hidden'); p.classList.remove('active'); });
        const activePanel = document.getElementById(`step-${step}`);
        if (activePanel) { activePanel.classList.remove('hidden'); activePanel.classList.add('active'); }

        stepIndicators.forEach(s => {
            const sNum = parseInt(s.dataset.step);
            s.classList.remove('active', 'completed');
            if (sNum === step) s.classList.add('active');
            else if (sNum < step) s.classList.add('completed');
        });

        btnPrev.disabled = (step === 1);
        if (step === TOTAL_STEPS) {
            btnNext.classList.add('hidden');
            btnUpload.classList.remove('hidden');
            updateSummary();
        } else {
            btnNext.classList.remove('hidden');
            btnUpload.classList.add('hidden');
        }
    }

    function canAdvance(step) {
        switch (step) {
            case 1: return !!selectedDataFile;
            case 2: return !!selectedProcTemplate;
            case 3: return true; // preview is always ready once we get here
            case 4: return !!selectedProtegrity;
            case 5: return !!selectedFolderPath;
            default: return true;
        }
    }

    btnNext.addEventListener('click', () => {
        if (!canAdvance(currentStep)) {
            showToast('Please complete this step before continuing.', 'error');
            return;
        }
        goToStep(currentStep + 1);
    });

    btnPrev.addEventListener('click', () => goToStep(currentStep - 1));

    // ======== File Drop Zone Helpers ========

    // ======== Step 5: Load Permitted Folders (with client-side cache) ========
    let _permFoldersCache = null;
    let _permFoldersCacheTime = 0;
    const PERM_CACHE_TTL_MS = 90000;  // 90 seconds
    let _permFoldersLoading = false;

    async function loadPermittedFolders() {
        // Use cached data if fresh
        if (_permFoldersCache && (Date.now() - _permFoldersCacheTime) < PERM_CACHE_TTL_MS) {
            renderPermittedFolders(_permFoldersCache);
            return;
        }

        // Avoid duplicate fetches
        if (_permFoldersLoading) return;
        _permFoldersLoading = true;

        // Show loading state
        permFoldersLoading.classList.remove('hidden');
        permFoldersList.classList.add('hidden');
        permFoldersEmpty.classList.add('hidden');

        try {
            const resp = await fetch('/api/volumes/permitted-folders');
            const data = await resp.json();

            if (!resp.ok) {
                throw new Error(data.error || `HTTP ${resp.status}`);
            }

            const folders = data.folders || [];
            // Cache the result
            _permFoldersCache = folders;
            _permFoldersCacheTime = Date.now();

            renderPermittedFolders(folders);
        } catch (err) {
            permFoldersLoading.classList.add('hidden');
            permFoldersEmpty.classList.remove('hidden');
            permFoldersEmpty.innerHTML = `
                <span class="empty-icon">⚠️</span>
                <p>Error loading folders: ${err.message}</p>
                <button class="btn-retry-folders" onclick="loadPermittedFolders()">Retry</button>
            `;
        } finally {
            _permFoldersLoading = false;
        }
    }

    function renderPermittedFolders(folders) {
        permFoldersLoading.classList.add('hidden');

        if (folders.length === 0) {
            permFoldersEmpty.classList.remove('hidden');
            permFoldersList.classList.add('hidden');
            return;
        }

        permFoldersEmpty.classList.add('hidden');
        permFoldersList.classList.remove('hidden');

        let html = '';
        folders.forEach(f => {
            const isSelected = f.path === selectedFolderPath;
            html += `
                <div class="permitted-folder-card${isSelected ? ' selected' : ''}" data-path="${escHtml(f.path)}">
                    <div class="pf-icon">📁</div>
                    <div class="pf-info">
                        <div class="pf-name">${escHtml(f.display_name)}</div>
                        <div class="pf-path">${escHtml(f.path)}</div>
                    </div>
                    <div class="pf-check">${isSelected ? '✓' : ''}</div>
                </div>
            `;
        });
        permFoldersList.innerHTML = html;

        // Bind click handlers
        permFoldersList.querySelectorAll('.permitted-folder-card').forEach(card => {
            card.addEventListener('click', () => {
                // Deselect all
                permFoldersList.querySelectorAll('.permitted-folder-card').forEach(c => {
                    c.classList.remove('selected');
                    c.querySelector('.pf-check').textContent = '';
                });
                // Select this one
                card.classList.add('selected');
                card.querySelector('.pf-check').textContent = '✓';
                selectedFolderPath = card.dataset.path;
                volumePathInput.value = selectedFolderPath;
            });
        });
    }

    function escHtml(s) {
        const d = document.createElement('div');
        d.textContent = s || '';
        return d.innerHTML;
    }

    function setupDropZone(zone, input, onFile) {
        zone.addEventListener('click', (e) => {
            if (e.target.closest('.btn-clear-file')) return;
            input.click();
        });
        input.addEventListener('change', () => { if (input.files.length > 0) onFile(input.files[0]); });
        zone.addEventListener('dragover', (e) => { e.preventDefault(); zone.classList.add('drag-over'); });
        zone.addEventListener('dragleave', () => zone.classList.remove('drag-over'));
        zone.addEventListener('drop', (e) => {
            e.preventDefault(); zone.classList.remove('drag-over');
            if (e.dataTransfer.files.length > 0) { input.files = e.dataTransfer.files; onFile(e.dataTransfer.files[0]); }
        });
    }

    function showFileInfo(file, infoEl, nameEl, sizeEl, promptEl) {
        infoEl.classList.remove('hidden');
        nameEl.textContent = file.name;
        sizeEl.textContent = formatSize(file.size);
        if (promptEl) promptEl.classList.add('hidden');
    }

    function clearFileSelection(input, infoEl, promptEl) {
        input.value = '';
        infoEl.classList.add('hidden');
        if (promptEl) promptEl.classList.remove('hidden');
    }

    // ======== Step 1: Data File (no preview) ========
    setupDropZone(dropZoneData, dataFileInput, (file) => {
        selectedDataFile = file;
        showFileInfo(file, dataFileInfo, dataFileName, dataFileSize, dropZoneData.querySelector('.drop-zone-prompt'));
    });

    btnClearData.addEventListener('click', (e) => {
        e.stopPropagation();
        selectedDataFile = null;
        clearFileSelection(dataFileInput, dataFileInfo, dropZoneData.querySelector('.drop-zone-prompt'));
    });

    // ======== Step 2: Processing Template ========
    setupDropZone(dropZoneProc, procInput, (file) => {
        selectedProcTemplate = file;
        showFileInfo(file, procFileInfo, procFileName, procFileSize, dropZoneProc.querySelector('.drop-zone-prompt'));
        parseProcessingTemplate(file);
    });

    btnClearProc.addEventListener('click', (e) => {
        e.stopPropagation();
        selectedProcTemplate = null;
        procWorkbook = null;
        procSheetNames = [];
        procSelectedSheet = '';
        procSelectedSheetInput.value = '';
        clearFileSelection(procInput, procFileInfo, dropZoneProc.querySelector('.drop-zone-prompt'));
        procSheetSelector.classList.add('hidden');
        previewTemplate.classList.add('hidden');
    });

    function parseProcessingTemplate(file) {
        const ext = file.name.split('.').pop().toLowerCase();

        if (['xlsx', 'xls'].includes(ext)) {
            const reader = new FileReader();
            reader.onload = (e) => {
                try {
                    procWorkbook = XLSX.read(e.target.result, { type: 'array' });
                    procSheetNames = procWorkbook.SheetNames;

                    if (procSheetNames.length > 1) {
                        renderSheetSelector();
                    } else {
                        procSheetSelector.classList.add('hidden');
                        procSelectedSheet = procSheetNames[0];
                        procSelectedSheetInput.value = procSelectedSheet;
                    }
                    previewProcSheet(procSelectedSheet || procSheetNames[0]);
                } catch (err) {
                    showToast(`Error reading template: ${err.message}`, 'error');
                }
            };
            reader.readAsArrayBuffer(file);
        } else {
            // CSV/TSV/TXT
            procWorkbook = null;
            procSheetNames = [];
            procSelectedSheet = '';
            procSelectedSheetInput.value = '';
            procSheetSelector.classList.add('hidden');

            const reader = new FileReader();
            reader.onload = (e) => {
                const rows = parseCSV(e.target.result);
                renderTemplatePreview(rows, file.name);
            };
            reader.readAsText(file);
        }
    }

    function renderSheetSelector() {
        procSheetSelector.classList.remove('hidden');
        procSheetCount.textContent = `${procSheetNames.length} sheets found`;

        procSheetTabs.innerHTML = procSheetNames.map((name, idx) => `
            <button type="button" class="sheet-tab ${idx === 0 ? 'active' : ''}" data-sheet="${esc(name)}">
                <span class="sheet-tab-icon">&#128196;</span>
                <span class="sheet-tab-name">${esc(name)}</span>
            </button>
        `).join('');

        procSelectedSheet = procSheetNames[0];
        procSelectedSheetInput.value = procSelectedSheet;

        procSheetTabs.querySelectorAll('.sheet-tab').forEach(tab => {
            tab.addEventListener('click', () => {
                procSheetTabs.querySelectorAll('.sheet-tab').forEach(t => t.classList.remove('active'));
                tab.classList.add('active');
                procSelectedSheet = tab.dataset.sheet;
                procSelectedSheetInput.value = procSelectedSheet;
                previewProcSheet(procSelectedSheet);
            });
        });
    }

    function previewProcSheet(sheetName) {
        if (!procWorkbook) return;
        const sheet = procWorkbook.Sheets[sheetName];
        if (!sheet) return;
        const rows = XLSX.utils.sheet_to_json(sheet, { header: 1, defval: '' });
        renderTemplatePreview(rows, sheetName);
    }

    function renderTemplatePreview(rows, label) {
        if (rows.length === 0) {
            templatePreviewMeta.textContent = 'Empty sheet / no data';
            templatePreviewThead.innerHTML = '';
            templatePreviewTbody.innerHTML = '<tr><td>No data found</td></tr>';
            previewTemplate.classList.remove('hidden');
            return;
        }

        const headers = rows[0];
        const dataRows = rows.slice(1);

        templatePreviewMeta.textContent = `Sheet: ${label} | ${dataRows.length} records | ${headers.length} columns`;
        templatePreviewThead.innerHTML = '<tr><th class="row-num-col">#</th>' + headers.map(h => `<th>${esc(String(h))}</th>`).join('') + '</tr>';
        templatePreviewTbody.innerHTML = dataRows.map((row, idx) =>
            '<tr><td class="row-num-cell">' + (idx + 1) + '</td>' + headers.map((_, i) => `<td>${esc(String(row[i] ?? ''))}</td>`).join('') + '</tr>'
        ).join('');
        previewTemplate.classList.remove('hidden');
    }

    // ==============================================================
    // ======== Step 3: Parsed Data Preview with PHI Highlight ======
    // ==============================================================

    /**
     * Builds the parsed data preview by:
     * 1. Reading the template sheet to get column definitions (Field Name, Start, End, PHI Type)
     * 2. Reading the data file as raw text
     * 3. Parsing each line using fixed-width Start/End positions from the template
     * 4. Highlighting columns where PHI Type is non-empty
     */
    function buildParsedPreview() {
        const templateRows = getTemplateSheetRows();
        const colDefs = parseTemplateDefs(templateRows);

        if (colDefs.length === 0) {
            parsedDataMeta.textContent = 'Could not find column definitions (Field Name / Start / End) in template';
            parsedDataThead.innerHTML = '';
            parsedDataTbody.innerHTML = '<tr><td>Template must have columns: Field Name, Start, End</td></tr>';
            previewParsedData.classList.remove('hidden');
            phiLegend.classList.add('hidden');
            return;
        }

        // Identify PHI columns
        phiColumnIndices = [];
        phiColumnNames = [];
        phiColumnIndices = [];
        phiColumnNames = [];
        phiColumnTypes = [];
        colDefs.forEach((col, idx) => {
            if (col.phiType) {
                phiColumnIndices.push(idx);
                phiColumnNames.push(col.fieldName);
                phiColumnTypes.push(col.phiType);
            }
        });

        // Read data file as raw text and parse with fixed-width positions
        readDataFileRaw((rawText) => {
            if (!rawText) {
                parsedDataMeta.textContent = 'No data to display';
                parsedDataThead.innerHTML = '';
                parsedDataTbody.innerHTML = '<tr><td>Data file is empty or could not be read</td></tr>';
                previewParsedData.classList.remove('hidden');
                return;
            }

            const lines = rawText.split('\n').filter(l => l.length > 0);
            const headers = colDefs.map(c => c.fieldName);
            parsedHeaders = headers;  // Store for submit

            // Parse each line using Start/End positions (1-based)
            const parsedRows = lines.map(line => {
                return colDefs.map(col => {
                    const start = col.start - 1; // convert to 0-based
                    const end = col.end;         // substring end is exclusive
                    return line.substring(start, end).trim();
                });
            });

            // Update PHI legend
            phiCountEl.textContent = `${phiColumnNames.length} PHI column${phiColumnNames.length !== 1 ? 's' : ''} detected`;
            phiLegend.classList.remove('hidden');

            // Render table
            parsedDataMeta.textContent = `${parsedRows.length} records | ${headers.length} columns | ${phiColumnNames.length} PHI`;

            parsedDataThead.innerHTML = '<tr><th class="row-num-col">#</th>' +
                headers.map((h, i) => {
                    const isPhi = phiColumnIndices.includes(i);
                    const phiType = isPhi ? colDefs[i].phiType : '';
                    return `<th class="${isPhi ? 'phi-col-header' : ''}">${esc(h)}${isPhi ? ' <span class="phi-badge" title="' + esc(phiType) + '">PHI</span>' : ''}</th>`;
                }).join('') + '</tr>';

            parsedDataTbody.innerHTML = parsedRows.map((row, rIdx) =>
                '<tr><td class="row-num-cell">' + (rIdx + 1) + '</td>' +
                row.map((cell, i) => {
                    const isPhi = phiColumnIndices.includes(i);
                    return `<td class="${isPhi ? 'phi-col-cell' : ''}">${esc(cell)}</td>`;
                }).join('') + '</tr>'
            ).join('');

            previewParsedData.classList.remove('hidden');

            // Store parsed data for upload submission
            parsedDataRows = parsedRows;
        });
    }

    /**
     * Get the template sheet data as array of arrays.
     */
    function getTemplateSheetRows() {
        if (procWorkbook && procSelectedSheet) {
            const sheet = procWorkbook.Sheets[procSelectedSheet];
            return sheet ? XLSX.utils.sheet_to_json(sheet, { header: 1, defval: '' }) : [];
        }
        return [];
    }

    /**
     * Parse template rows into column definitions.
     * Expects columns: "Field Name", "Start", "End", "PHI Type"
     * Returns array of { fieldName, start, end, phiType }
     */
    function parseTemplateDefs(templateRows) {
        if (templateRows.length < 2) return [];

        const headers = templateRows[0].map(h => String(h).trim().toLowerCase());

        // Find column indices (flexible matching)
        const fieldNameIdx = headers.findIndex(h =>
            h === 'field name' || h === 'field_name' || h === 'fieldname' ||
            h === 'column_name' || h === 'column name' || h === 'name' || h === 'field'
        );
        const startIdx = headers.findIndex(h =>
            h === 'start' || h === 'start_position' || h === 'startposition' || h === 'begin'
        );
        const endIdx = headers.findIndex(h =>
            h === 'end' || h === 'end_position' || h === 'endposition' || h === 'stop'
        );
        const phiIdx = headers.findIndex(h =>
            h === 'phi type' || h === 'phi_type' || h === 'phitype' || h === 'phi'
        );

        if (fieldNameIdx === -1 || startIdx === -1 || endIdx === -1) return [];

        const defs = [];
        for (let i = 1; i < templateRows.length; i++) {
            const row = templateRows[i];
            const fieldName = String(row[fieldNameIdx] ?? '').trim();
            const start = parseInt(row[startIdx], 10);
            const end = parseInt(row[endIdx], 10);
            const phiType = phiIdx !== -1 ? String(row[phiIdx] ?? '').trim() : '';

            if (fieldName && !isNaN(start) && !isNaN(end)) {
                defs.push({ fieldName, start, end, phiType });
            }
        }
        return defs;
    }

    /**
     * Read the data file as raw text (for fixed-width parsing).
     */
    function readDataFileRaw(callback) {
        if (!selectedDataFile) { callback(null); return; }

        const reader = new FileReader();
        reader.onload = (e) => callback(e.target.result);
        reader.onerror = () => { showToast('Error reading data file', 'error'); callback(null); };
        reader.readAsText(selectedDataFile);
    }

    // ==============================================================
    // ======== Step 4: Protegrity Template (JSON Viewer) ===========
    // ==============================================================

    setupDropZone(dropZoneProtegrity, protegrityInput, (file) => {
        selectedProtegrity = file;
        showFileInfo(file, protegrityFileInfo, protegrityFileName, protegrityFileSize, dropZoneProtegrity.querySelector('.drop-zone-prompt'));
        renderJsonPreview(file, previewTokenized, 'Protegrity');
    });

    btnClearProtegrity.addEventListener('click', (e) => {
        e.stopPropagation();
        selectedProtegrity = null;
        clearFileSelection(protegrityInput, protegrityFileInfo, dropZoneProtegrity.querySelector('.drop-zone-prompt'));
        previewTokenized.classList.add('hidden');
    });

    function renderJsonPreview(file, container, label) {
        const reader = new FileReader();
        reader.onload = (e) => {
            const rawText = e.target.result;
            let json = null;
            try { json = JSON.parse(rawText); } catch (_) {}

            if (!json) {
                container.innerHTML = `
                    <div class="json-viewer-header">
                        <span class="json-viewer-title">${esc(label)} Template</span>
                        <span class="json-badge badge-disabled">Non-JSON</span>
                    </div>
                    <div class="json-raw-view"><pre class="json-raw-code">${esc(rawText.slice(0, 5000))}</pre></div>`;
                container.classList.remove('hidden');
                return;
            }

            const summaryHtml = buildVisualSummary(json, label);
            const rawHtml = buildRawJsonView(json);
            const uid = 'jv-' + Math.random().toString(36).slice(2, 8);

            container.innerHTML = `
                <div class="json-viewer-header">
                    <span class="json-viewer-title">${esc(label)} Template</span>
                    <div class="json-tab-toggle" data-uid="${uid}">
                        <button class="json-tab active" data-view="summary">Visual Summary</button>
                        <button class="json-tab" data-view="raw">Raw JSON</button>
                    </div>
                </div>
                <div class="json-view-panel json-summary-panel" id="${uid}-summary">${summaryHtml}</div>
                <div class="json-view-panel json-raw-panel hidden" id="${uid}-raw">${rawHtml}</div>`;
            container.classList.remove('hidden');

            container.querySelectorAll(`.json-tab-toggle[data-uid="${uid}"] .json-tab`).forEach(tab => {
                tab.addEventListener('click', () => {
                    container.querySelectorAll('.json-tab').forEach(t => t.classList.remove('active'));
                    tab.classList.add('active');
                    const view = tab.dataset.view;
                    document.getElementById(`${uid}-summary`).classList.toggle('hidden', view !== 'summary');
                    document.getElementById(`${uid}-raw`).classList.toggle('hidden', view !== 'raw');
                });
            });

            container.querySelectorAll('.json-collapsible').forEach(arrow => {
                arrow.addEventListener('click', () => {
                    const target = arrow.nextElementSibling;
                    const isCollapsed = target.classList.toggle('collapsed');
                    arrow.classList.toggle('collapsed', isCollapsed);
                });
            });
        };
        reader.readAsText(file);
    }

    // ======== JSON Visual Summary ========
    function buildVisualSummary(json, label) {
        let html = '';
        const enabled = findKey(json, 'enabled');
        if (enabled !== undefined) {
            html += `<div class="json-summary-badges"><span class="json-badge ${enabled ? 'badge-enabled' : 'badge-disabled'}">${enabled ? 'Enabled' : 'Disabled'}</span></div>`;
        }
        const metaFields = extractMetadata(json);
        if (metaFields.length > 0) {
            html += '<div class="json-meta-cards">';
            metaFields.forEach(([key, val]) => {
                html += `<div class="json-meta-card"><span class="meta-label">${esc(formatKey(key))}</span><span class="meta-value">${esc(String(val))}</span></div>`;
            });
            html += '</div>';
        }
        const columns = extractColumns(json);
        if (columns.length > 0) {
            const colHeaders = Object.keys(columns[0]);
            html += `<div class="json-columns-section"><h4 class="json-columns-title">Column Configuration <span class="json-col-count">(${columns.length})</span></h4>
                <div class="json-columns-table-wrap"><table class="json-columns-table">
                <thead><tr>${colHeaders.map(h => `<th>${esc(formatKey(h))}</th>`).join('')}</tr></thead>
                <tbody>${columns.map(row => '<tr>' + colHeaders.map(h => `<td>${esc(String(row[h] ?? ''))}</td>`).join('') + '</tr>').join('')}</tbody>
                </table></div></div>`;
        }
        if (!html) {
            const entries = flattenJSON(json).slice(0, 40);
            html += `<div class="json-columns-section"><h4 class="json-columns-title">${esc(label)} Fields</h4>
                <div class="json-columns-table-wrap"><table class="json-columns-table">
                <thead><tr><th>Field</th><th>Value</th></tr></thead>
                <tbody>${entries.map(([k, v]) => `<tr><td><code>${esc(k)}</code></td><td>${esc(String(v))}</td></tr>`).join('')}</tbody>
                </table></div></div>`;
        }
        return html;
    }

    function buildRawJsonView(json) {
        return `<div class="json-raw-view"><pre class="json-raw-code">${syntaxHighlight(json, 0)}</pre></div>`;
    }

    function syntaxHighlight(obj, indent, isLast) {
        const pad = '  '.repeat(indent);
        const padInner = '  '.repeat(indent + 1);
        if (isLast === undefined) isLast = true;
        const comma = isLast ? '' : ',';
        if (obj === null) return `<span class="json-null">null</span>${comma}`;
        if (typeof obj === 'boolean') return `<span class="json-bool">${obj}</span>${comma}`;
        if (typeof obj === 'number') return `<span class="json-num">${obj}</span>${comma}`;
        if (typeof obj === 'string') return `<span class="json-str">"${escJson(obj)}"</span>${comma}`;
        if (Array.isArray(obj)) {
            if (obj.length === 0) return `<span class="json-bracket">[]</span>${comma}`;
            let lines = `<span class="json-collapsible">&#9660;</span><span class="json-collapsible-content"><span class="json-bracket">[</span>\n`;
            obj.forEach((item, i) => { lines += padInner + syntaxHighlight(item, indent + 1, i === obj.length - 1) + '\n'; });
            return lines + pad + `<span class="json-bracket">]</span>${comma}</span>`;
        }
        if (typeof obj === 'object') {
            const keys = Object.keys(obj);
            if (keys.length === 0) return `<span class="json-bracket">{}</span>${comma}`;
            let lines = `<span class="json-collapsible">&#9660;</span><span class="json-collapsible-content"><span class="json-bracket">{</span>\n`;
            keys.forEach((key, i) => { lines += padInner + `<span class="json-key">"${escJson(key)}"</span>: ${syntaxHighlight(obj[key], indent + 1, i === keys.length - 1)}\n`; });
            return lines + pad + `<span class="json-bracket">}</span>${comma}</span>`;
        }
        return esc(String(obj)) + comma;
    }

    function findKey(obj, key) {
        if (!obj || typeof obj !== 'object') return undefined;
        if (key in obj) return obj[key];
        for (const v of Object.values(obj)) { const f = findKey(v, key); if (f !== undefined) return f; }
        return undefined;
    }
    function extractMetadata(json) {
        return Object.entries(json).filter(([k, v]) => v !== null && typeof v !== 'object' && k.toLowerCase() !== 'enabled');
    }
    function extractColumns(json) {
        const keys = ['fixedWidthColumns','columns','fields','protectionRules','tokenizationRules','mappings','columnMappings'];
        for (const k of keys) { const a = findKey(json, k); if (Array.isArray(a) && a.length > 0 && typeof a[0] === 'object') return normalizeColumns(a, k); }
        for (const v of Object.values(json)) { if (Array.isArray(v) && v.length > 0 && typeof v[0] === 'object') return normalizeColumns(v, ''); }
        return [];
    }
    function normalizeColumns(arr, sourceKey) {
        if (sourceKey === 'fixedWidthColumns') {
            return arr.map((c, i) => ({ Position: c.startPosition||c.start||c.position||(i+1), Width: c.width||c.length||c.size||'', 'Target Field': c.comments||c.comment||c.targetField||c.name||c.fieldName||'', 'Protection Profile': c.protectionProfile||c.profile||c.tokenProfile||c.rule||'' }));
        }
        const allKeys = new Set(); arr.slice(0,5).forEach(item => Object.keys(item).forEach(k => allKeys.add(k)));
        const priority = ['name','fieldName','column','field','position','startPosition','width','length','type','dataType','comments','description','protectionProfile','profile','rule','action'];
        const sel = priority.filter(k => allKeys.has(k)); allKeys.forEach(k => { if (!sel.includes(k) && sel.length < 6) sel.push(k); });
        return arr.map(item => { const r = {}; sel.forEach(k => { r[k] = item[k] ?? ''; }); return r; });
    }



    // ======== Summary ========
    function updateSummary() {
        document.getElementById('summary-data-file').textContent = selectedDataFile ? selectedDataFile.name : '--';
        document.getElementById('summary-proc-template').textContent = selectedProcTemplate ? selectedProcTemplate.name : '--';
        document.getElementById('summary-proc-sheet').textContent = procSelectedSheet || '(single sheet / CSV)';
        document.getElementById('summary-phi-cols').textContent = phiColumnNames.length > 0 ? phiColumnNames.join(', ') : 'None detected';
        document.getElementById('summary-protegrity-template').textContent = selectedProtegrity ? selectedProtegrity.name : '--';
        document.getElementById('summary-target-folder').textContent = selectedFolderPath || '--';
    }

    // ======== Form Submission ========
    btnUpload.addEventListener('click', async (e) => {
        if (!selectedDataFile || !selectedProcTemplate || !selectedProtegrity || !selectedFolderPath) { showToast('Please complete all steps before uploading.', 'error'); return; }
        if (!parsedDataRows || parsedDataRows.length === 0) { showToast('No parsed data available. Go back to Step 3 to verify preview.', 'error'); return; }

        btnUpload.disabled = true; btnUpload.textContent = 'Tokenizing & Uploading...';
        const progressDiv = document.getElementById('upload-progress');
        progressDiv.classList.remove('hidden');
        document.getElementById('progress-message').textContent = 'Calling Protegrity API and uploading tokenized file...';

        // Build JSON payload with parsed data from Step 3
        const payload = {
            headers: parsedHeaders,
            rows: parsedDataRows,
            phi_columns: phiColumnNames,
            phi_indices: phiColumnIndices,
            phi_types: phiColumnTypes,
            volume_path: selectedFolderPath,
            original_filename: selectedDataFile.name,
        };

        try {
            const resp = await fetch('/upload/tokenize', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload),
            });
            const result = await resp.json();
            progressDiv.classList.add('hidden');
            const resultsDiv = document.getElementById('upload-results');
            resultsDiv.classList.remove('hidden');
            if (resp.ok) {
                resultsDiv.innerHTML = `<div class="result-success">
                    <h4>✅ Upload & Tokenization Complete</h4>
                    <p>${esc(result.message || 'File tokenized and uploaded successfully.')}</p>
                    ${result.output_path ? '<p><strong>Output File:</strong> ' + esc(result.output_path) + '</p>' : ''}
                    ${result.rows_processed ? '<p><strong>Rows Processed:</strong> ' + result.rows_processed + '</p>' : ''}
                    ${result.columns_tokenized ? '<p><strong>PHI Columns Masked:</strong> ' + esc(result.columns_tokenized.join(', ')) + '</p>' : ''}
                </div>`;
                showToast('Upload and tokenization complete!');
            } else {
                resultsDiv.innerHTML = `<div class="result-error"><h4>Upload Failed</h4><p>${esc(result.error || 'An error occurred.')}</p></div>`;
                showToast(result.error || 'Upload failed', 'error');
            }
        } catch (err) { document.getElementById('upload-progress').classList.add('hidden'); showToast(`Network error: ${err.message}`, 'error'); }
        finally { btnUpload.disabled = false; btnUpload.textContent = 'Upload and Tokenize'; }
    });

    // ======== Utilities ========
    function parseCSV(text) {
        const lines = text.split('\n').filter(l => l.trim());
        const delimiter = text.includes('\t') ? '\t' : ',';
        return lines.map(line => parseCSVLine(line, delimiter));
    }
    function parseCSVLine(line, delimiter) {
        const cells = []; let current = ''; let inQuotes = false;
        for (let i = 0; i < line.length; i++) {
            const ch = line[i];
            if (ch === '"') { if (inQuotes && line[i+1] === '"') { current += '"'; i++; } else { inQuotes = !inQuotes; } }
            else if (ch === delimiter && !inQuotes) { cells.push(current.trim()); current = ''; }
            else { current += ch; }
        }
        cells.push(current.trim()); return cells;
    }
    function flattenJSON(obj, prefix) {
        prefix = prefix || ''; const entries = [];
        for (const [k, v] of Object.entries(obj)) { const fk = prefix ? `${prefix}.${k}` : k; if (v && typeof v === 'object' && !Array.isArray(v)) entries.push(...flattenJSON(v, fk)); else entries.push([fk, Array.isArray(v) ? JSON.stringify(v) : v]); }
        return entries;
    }
    function formatKey(k) { return k.replace(/([a-z])([A-Z])/g,'$1 $2').replace(/_/g,' ').replace(/\b\w/g,c=>c.toUpperCase()); }
    function formatSize(b) { if (b < 1024) return b + ' B'; if (b < 1048576) return (b/1024).toFixed(1) + ' KB'; return (b/1048576).toFixed(1) + ' MB'; }
    function esc(s) { const d = document.createElement('div'); d.textContent = s || ''; return d.innerHTML; }
    function escJson(s) { return s.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;'); }
    function showToast(msg, type) {
        let n = document.getElementById('upload-toast');
        if (!n) { n = document.createElement('div'); n.id = 'upload-toast'; n.className = 'perm-notification'; document.body.appendChild(n); }
        n.textContent = (type === 'error' ? '! ' : '') + msg;
        n.className = `perm-notification ${type || 'success'} show`;
        setTimeout(() => n.classList.remove('show'), 4000);
    }

    // ======== Init ========
    goToStep(1);
})();
