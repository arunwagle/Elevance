/**
 * Admin module — permissions matrix, jobs, ABAC policies, clusters.
 */
(function() {
    // ========== Permissions Matrix ==========
    document.getElementById('save-permissions')?.addEventListener('click', function() {
        const groups = {};
        document.querySelectorAll('.perm-matrix input[type="checkbox"]').forEach(cb => {
            const group = cb.dataset.group;
            const perm = cb.dataset.perm;
            if (!groups[group]) groups[group] = [];
            if (cb.checked) groups[group].push(perm);
        });

        const promises = Object.entries(groups).map(([groupId, perms]) =>
            fetch('/admin/permissions', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ group_id: groupId, permissions: perms }),
            })
        );

        Promise.all(promises)
            .then(() => alert('Permissions saved successfully.'))
            .catch(err => alert('Error saving permissions: ' + err.message));
    });

    // ========== Create Job Form ==========
    document.getElementById('create-job-form')?.addEventListener('submit', async function(e) {
        e.preventDefault();
        const form = e.target;
        const data = {
            job_name: form.job_name.value,
            notebook_path: form.notebook_path.value,
            schedule_cron: form.schedule_cron.value,
            timezone: form.timezone.value,
            max_retries: form.max_retries.value,
            timeout_seconds: form.timeout_seconds.value,
            cluster_id: form.cluster_id.value,
            tags: form.tags.value,
        };

        try {
            const resp = await fetch('/admin/jobs', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(data),
            });
            const result = await resp.json();
            const panel = document.getElementById('job-result');
            const content = document.getElementById('job-result-content');
            panel.classList.remove('hidden');
            content.textContent = JSON.stringify(result, null, 2);
        } catch (err) {
            alert('Error: ' + err.message);
        }
    });

    // ========== ABAC Policy Form ==========
    // Toggle row filter vs column mask fields
    document.getElementById('policy-type')?.addEventListener('change', function() {
        const isRow = this.value === 'row_filter';
        const rowSection = document.getElementById('row-filter-section');
        const colSection = document.getElementById('column-mask-section');
        const maskSection = document.getElementById('mask-function-section');
        if (rowSection) rowSection.classList.toggle('hidden', !isRow);
        if (colSection) colSection.classList.toggle('hidden', isRow);
        if (maskSection) maskSection.classList.toggle('hidden', isRow);
    });

    // Toggle custom mask expression
    document.getElementById('mask-function')?.addEventListener('change', function() {
        const customSection = document.getElementById('custom-mask-section');
        if (customSection) customSection.classList.toggle('hidden', this.value !== 'custom');
    });

    // Preview SQL button
    document.getElementById('preview-sql')?.addEventListener('click', function() {
        const form = document.getElementById('create-abac-form');
        const catalog = form.catalog.value;
        const schema = form.schema.value;
        const table = form.table_name.value;
        const policyName = form.policy_name.value;
        const policyType = form.policy_type.value;
        const fullTable = `${catalog}.${schema}.${table}`;

        let sql = '';
        if (policyType === 'row_filter') {
            const filterExpr = form.filter_expression.value;
            sql = `CREATE OR REPLACE FUNCTION ${catalog}.${schema}.${policyName}()\nRETURNS BOOLEAN\nRETURN (${filterExpr});\n\nALTER TABLE ${fullTable} SET ROW FILTER ${catalog}.${schema}.${policyName} ON ();`;
        } else {
            const col = form.column_name.value;
            let maskExpr = form.mask_function.value;
            if (maskExpr === 'custom') maskExpr = form.custom_mask_expression.value;
            maskExpr = maskExpr.replace(/\{col\}/g, col + '_val');
            sql = `CREATE OR REPLACE FUNCTION ${catalog}.${schema}.${policyName}(${col}_val STRING)\nRETURNS STRING\nRETURN ${maskExpr};\n\nALTER TABLE ${fullTable} ALTER COLUMN ${col} SET MASK ${catalog}.${schema}.${policyName};`;
        }

        const panel = document.getElementById('sql-preview');
        const content = document.getElementById('sql-preview-content');
        panel.classList.remove('hidden');
        content.textContent = sql;
    });

    // Submit ABAC policy
    document.getElementById('create-abac-form')?.addEventListener('submit', async function(e) {
        e.preventDefault();
        const form = e.target;
        const data = {
            policy_name: form.policy_name.value,
            catalog: form.catalog.value,
            schema: form.schema.value,
            table_name: form.table_name.value,
            policy_type: form.policy_type.value,
            filter_expression: form.filter_expression?.value || '',
            column_name: form.column_name?.value || '',
            mask_function: form.mask_function?.value || '',
            custom_mask_expression: form.custom_mask_expression?.value || '',
            groups: form.groups?.value || '',
        };

        try {
            const resp = await fetch('/admin/abac-policies', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(data),
            });
            const result = await resp.json();
            const panel = document.getElementById('abac-result');
            const content = document.getElementById('abac-result-content');
            panel.classList.remove('hidden');
            content.textContent = JSON.stringify(result, null, 2);
        } catch (err) {
            alert('Error: ' + err.message);
        }
    });

    // ========== Create Cluster Form ==========
    // Toggle autoscale section
    document.getElementById('enable-autoscale')?.addEventListener('change', function() {
        document.getElementById('autoscale-section')?.classList.toggle('hidden', !this.checked);
    });

    // Preview JSON button
    document.getElementById('preview-cluster-json')?.addEventListener('click', function() {
        const form = document.getElementById('create-cluster-form');
        const payload = {
            cluster_name: form.cluster_name.value,
            spark_version: form.spark_version.value,
            node_type_id: form.node_type_id.value,
            autotermination_minutes: parseInt(form.autotermination_minutes.value),
        };
        if (form.driver_node_type_id.value) payload.driver_node_type_id = form.driver_node_type_id.value;
        if (form.enable_autoscale.checked) {
            payload.autoscale = { min_workers: parseInt(form.min_workers.value), max_workers: parseInt(form.max_workers.value) };
        } else {
            payload.num_workers = parseInt(form.num_workers.value);
        }
        payload.aws_attributes = { availability: form.spot_policy.value, first_on_demand: 1 };
        if (form.spark_conf.value.trim()) {
            payload.spark_conf = {};
            form.spark_conf.value.trim().split('\n').forEach(line => {
                const [k, v] = line.split('=');
                if (k && v) payload.spark_conf[k.trim()] = v.trim();
            });
        }
        if (form.tags.value.trim()) {
            try { payload.custom_tags = JSON.parse(form.tags.value); } catch(e) {}
        }
        const panel = document.getElementById('cluster-json-preview');
        const content = document.getElementById('cluster-json-content');
        panel.classList.remove('hidden');
        content.textContent = JSON.stringify(payload, null, 2);
    });

    // Submit cluster form
    document.getElementById('create-cluster-form')?.addEventListener('submit', async function(e) {
        e.preventDefault();
        const form = e.target;
        const data = {
            cluster_name: form.cluster_name.value,
            spark_version: form.spark_version.value,
            node_type_id: form.node_type_id.value,
            num_workers: form.num_workers.value,
            driver_node_type_id: form.driver_node_type_id.value,
            enable_autoscale: form.enable_autoscale.checked,
            min_workers: form.min_workers.value,
            max_workers: form.max_workers.value,
            autotermination_minutes: form.autotermination_minutes.value,
            spot_policy: form.spot_policy.value,
            spark_conf: form.spark_conf.value,
            tags: form.tags.value,
        };

        try {
            const resp = await fetch('/admin/clusters', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(data),
            });
            const result = await resp.json();
            const panel = document.getElementById('cluster-result');
            const content = document.getElementById('cluster-result-content');
            panel.classList.remove('hidden');
            content.textContent = JSON.stringify(result, null, 2);
        } catch (err) {
            alert('Error: ' + err.message);
        }
    });
})();
