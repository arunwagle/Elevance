/**
 * Admin Jobs — infinite scroll job list with expandable run details.
 */
(function() {
    const PAGE_SIZE = 25;
    const WORKSPACE_HOST = window.DATABRICKS_HOST || '';

    function getWorkspaceJobUrl(jobId) {
        const host = WORKSPACE_HOST.startsWith('http') ? WORKSPACE_HOST : 'https://' + WORKSPACE_HOST;
        return host + '/#job/' + jobId;
    }

    let currentOffset = 0;
    let isLoading = false;
    let hasMore = true;
    let searchTerm = '';
    let searchTimeout = null;

    const listEl = document.getElementById('jobs-list');
    const loadingEl = document.getElementById('jobs-loading');
    const emptyEl = document.getElementById('jobs-empty');
    const containerEl = document.getElementById('jobs-list-container');
    const searchInput = document.getElementById('job-search-input');

    // ========== Search ==========
    searchInput?.addEventListener('input', function() {
        clearTimeout(searchTimeout);
        searchTimeout = setTimeout(() => {
            searchTerm = this.value.trim();
            resetAndLoad();
        }, 400);
    });

    // ========== Load Jobs ==========
    function resetAndLoad() {
        currentOffset = 0;
        hasMore = true;
        listEl.innerHTML = '';
        emptyEl.classList.add('hidden');
        loadJobs();
    }

    async function loadJobs() {
        if (isLoading || !hasMore) return;
        isLoading = true;
        loadingEl.classList.remove('hidden');

        try {
            const params = new URLSearchParams({
                offset: currentOffset,
                limit: PAGE_SIZE,
            });
            if (searchTerm) params.set('name', searchTerm);

            const resp = await fetch(`/admin/jobs/list?${params}`);
            const data = await resp.json();

            if (data.error) {
                showError(data.error);
                return;
            }

            const jobs = data.jobs || [];
            hasMore = data.has_more || false;
            currentOffset += jobs.length;

            if (jobs.length === 0 && currentOffset === 0) {
                emptyEl.classList.remove('hidden');
            } else {
                jobs.forEach(job => listEl.appendChild(createJobCard(job)));
            }
        } catch (err) {
            showError(err.message);
        } finally {
            isLoading = false;
            loadingEl.classList.add('hidden');
        }
    }

    function createJobCard(job) {
        const card = document.createElement('div');
        card.className = 'job-card';
        card.dataset.jobId = job.job_id;

        const createdDate = job.created_time
            ? new Date(job.created_time).toLocaleDateString('en-US', {
                year: 'numeric', month: 'short', day: 'numeric'
            })
            : '—';

        const tags = Object.entries(job.tags || {})
            .map(([k, v]) => `<span class="job-tag">${escapeHtml(k)}: ${escapeHtml(v)}</span>`)
            .join('');

        card.innerHTML = `
            <div class="job-card-header" data-job-id="${job.job_id}">
                <div class="job-card-left">
                    <span class="job-expand-icon">▶</span>
                    <div class="job-card-title">${escapeHtml(job.name)}</div>
                </div>
                <div class="job-card-actions">
                    <span class="job-card-id">Job Id: #${job.job_id}</span>
                    <a href="${getWorkspaceJobUrl(job.job_id)}" target="_blank" rel="noopener"
                       class="btn-view-job" title="View Job in Databricks">
                        🔗 View Job ↗
                    </a>
                </div>
            </div>
            <div class="job-card-meta">
                <span class="job-meta-item" title="Creator">👤 ${escapeHtml(job.creator_user_name || 'Unknown')}</span>
                <span class="job-meta-item" title="Created">📅 ${createdDate}</span>
                <span class="job-meta-item" title="Schedule">⏰ ${escapeHtml(job.schedule)}</span>
            </div>
            ${tags ? `<div class="job-card-tags">${tags}</div>` : ''}
            <div class="job-runs-container hidden" id="runs-${job.job_id}">
                <div class="runs-loading hidden"><div class="spinner-sm"></div> Loading runs...</div>
                <div class="runs-list"></div>
                <div class="runs-empty hidden">No runs found for this job</div>
            </div>
        `;

        // Click header to expand/collapse runs
        const header = card.querySelector('.job-card-header');
        header.addEventListener('click', () => toggleRuns(card, job.job_id));

        return card;
    }

    // ========== Expand/Collapse Runs ==========
    async function toggleRuns(card, jobId) {
        const container = card.querySelector('.job-runs-container');
        const icon = card.querySelector('.job-expand-icon');
        const isExpanded = !container.classList.contains('hidden');

        if (isExpanded) {
            container.classList.add('hidden');
            icon.textContent = '▶';
            card.classList.remove('expanded');
            return;
        }

        // Expand
        container.classList.remove('hidden');
        icon.textContent = '▼';
        card.classList.add('expanded');

        // Load runs if not already loaded
        const runsList = container.querySelector('.runs-list');
        if (runsList.children.length === 0) {
            await loadRuns(container, jobId);
        }
    }

    async function loadRuns(container, jobId) {
        const loadingEl = container.querySelector('.runs-loading');
        const runsList = container.querySelector('.runs-list');
        const emptyEl = container.querySelector('.runs-empty');

        loadingEl.classList.remove('hidden');
        emptyEl.classList.add('hidden');

        try {
            const resp = await fetch(`/admin/jobs/${jobId}/runs?limit=10`);
            const data = await resp.json();

            if (data.error) {
                runsList.innerHTML = `<div class="run-error">⚠️ ${escapeHtml(data.error)}</div>`;
                return;
            }

            const runs = data.runs || [];
            if (runs.length === 0) {
                emptyEl.classList.remove('hidden');
            } else {
                runs.forEach(run => runsList.appendChild(createRunRow(run)));
            }
        } catch (err) {
            runsList.innerHTML = `<div class="run-error">⚠️ ${err.message}</div>`;
        } finally {
            loadingEl.classList.add('hidden');
        }
    }

    function createRunRow(run) {
        const row = document.createElement('div');
        row.className = 'run-row';

        const startTime = run.start_time
            ? new Date(run.start_time).toLocaleString('en-US', {
                month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit'
            })
            : '—';

        const duration = run.run_duration
            ? formatDuration(run.run_duration)
            : '—';

        const stateClass = getStateClass(run.state);

        row.innerHTML = `
            <div class="run-row-left">
                <span class="run-state ${stateClass}">${escapeHtml(run.state)}</span>
                <span class="run-time">🕐 ${startTime}</span>
                <span class="run-duration">⏱ ${duration}</span>
            </div>
            <div class="run-row-right">
                <a href="${escapeHtml(run.run_page_url)}" target="_blank" rel="noopener"
                   class="run-details-link" title="View Run Details in Databricks">
                    🔗 View Details ↗
                </a>
            </div>
        `;

        return row;
    }

    // ========== Helpers ==========
    function formatDuration(ms) {
        if (ms < 1000) return `${ms}ms`;
        const seconds = Math.floor(ms / 1000);
        if (seconds < 60) return `${seconds}s`;
        const minutes = Math.floor(seconds / 60);
        const remainSec = seconds % 60;
        if (minutes < 60) return `${minutes}m ${remainSec}s`;
        const hours = Math.floor(minutes / 60);
        const remainMin = minutes % 60;
        return `${hours}h ${remainMin}m`;
    }

    function getStateClass(state) {
        switch (state) {
            case 'SUCCESS': return 'state-success';
            case 'FAILED': case 'TIMEDOUT': case 'CANCELED': return 'state-failed';
            case 'RUNNING': case 'PENDING': return 'state-running';
            default: return 'state-unknown';
        }
    }

    function showError(msg) {
        const errDiv = document.createElement('div');
        errDiv.className = 'job-error';
        errDiv.textContent = '⚠️ ' + msg;
        listEl.appendChild(errDiv);
    }

    function escapeHtml(str) {
        const div = document.createElement('div');
        div.textContent = str || '';
        return div.innerHTML;
    }

    // ========== Infinite Scroll ==========
    containerEl?.addEventListener('scroll', function() {
        const { scrollTop, scrollHeight, clientHeight } = this;
        if (scrollHeight - scrollTop - clientHeight < 200) {
            loadJobs();
        }
    });

    window.addEventListener('scroll', function() {
        if (!containerEl) return;
        const rect = containerEl.getBoundingClientRect();
        if (rect.bottom - window.innerHeight < 300) {
            loadJobs();
        }
    });


        // ========== Initial Load ==========
    loadJobs();
})();
