/**
 * Browse page — action menus and delete confirmation.
 */
(function() {
    // Toggle action dropdown menus
    document.querySelectorAll('.action-dots').forEach(btn => {
        btn.addEventListener('click', function(e) {
            e.stopPropagation();
            const dropdown = this.nextElementSibling;
            document.querySelectorAll('.action-dropdown').forEach(d => d.classList.add('hidden'));
            dropdown.classList.toggle('hidden');
        });
    });

    // Close dropdowns on outside click
    document.addEventListener('click', () => {
        document.querySelectorAll('.action-dropdown').forEach(d => d.classList.add('hidden'));
    });

    // Delete actions
    document.querySelectorAll('.delete-action').forEach(link => {
        link.addEventListener('click', function(e) {
            e.preventDefault();
            const path = this.dataset.path;
            if (confirm(`Are you sure you want to delete:\n${path}?`)) {
                fetch(`/files/delete/${encodeURIComponent(path)}`, { method: 'DELETE' })
                    .then(r => r.json())
                    .then(() => location.reload())
                    .catch(err => alert('Delete failed: ' + err.message));
            }
        });
    });

    // Search filter
    document.getElementById('search-files')?.addEventListener('input', function() {
        const query = this.value.toLowerCase();
        document.querySelectorAll('.data-table tbody tr').forEach(row => {
            const name = row.querySelector('td')?.textContent.toLowerCase() || '';
            row.style.display = name.includes(query) ? '' : 'none';
        });
    });
})();
