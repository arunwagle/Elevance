"""Admin routes — dashboard tiles, permissions, jobs, ABAC policies, clusters."""

import json
import logging
import os
import requests as http_requests
from flask import Blueprint, render_template, request, jsonify, session
from middleware.auth_middleware import require_permission, require_admin
from services.permissions_service import PermissionsService
from services.audit_service import audit_service
from services.auth_service import AuthService

logger = logging.getLogger(__name__)
admin_bp = Blueprint('admin', __name__, url_prefix='/admin')
permissions_service = PermissionsService()
auth_service = AuthService()


def _get_user_api_headers():
    """Get headers using the user's X-Forwarded-Access-Token (for Files API)."""
    token = auth_service.get_access_token()
    if not token:
        return None
    return {
        'Authorization': f'Bearer {token}',
        'Content-Type': 'application/json',
    }


def _get_sp_api_headers():
    """Get headers using the app service principal token (for Jobs/Clusters API).

    The Jobs and Clusters APIs don't have user-authorization scopes available
    in the Databricks Apps Public Preview. Admin operations use the SP token
    obtained via OAuth2 client_credentials flow.
    """
    host = _get_host()
    sp_client_id = os.environ.get('DATABRICKS_CLIENT_ID', '')
    sp_client_secret = os.environ.get('DATABRICKS_CLIENT_SECRET', '')

    if not sp_client_id or not sp_client_secret:
        logger.error("SP credentials not found in environment")
        return None

    try:
        token_resp = http_requests.post(
            f'{host}/oidc/v1/token',
            data={
                'grant_type': 'client_credentials',
                'client_id': sp_client_id,
                'client_secret': sp_client_secret,
                'scope': 'all-apis',
            },
            timeout=10,
        )
        if token_resp.status_code != 200:
            logger.error(f"SP token request failed: {token_resp.status_code} {token_resp.text[:200]}")
            return None

        sp_token = token_resp.json().get('access_token')
        if not sp_token:
            logger.error("SP token response missing access_token")
            return None

        return {
            'Authorization': f'Bearer {sp_token}',
            'Content-Type': 'application/json',
        }
    except Exception as e:
        logger.error(f"Failed to get SP token: {e}")
        return None


def _get_host():
    """Get the Databricks workspace host with https:// scheme."""
    host = os.environ.get('DATABRICKS_HOST', '').rstrip('/')
    if host and not host.startswith('http'):
        host = f'https://{host}'
    return host


# --- Admin Dashboard ---

@admin_bp.route('/', methods=['GET'])
@admin_bp.route('/dashboard', methods=['GET'])
@require_admin
def admin_dashboard():
    """Render the admin dashboard with tiles."""
    return render_template(
        'admin/dashboard.html',
        permissions=session.get('permissions', []),
    )


# --- Permissions Management ---


@admin_bp.route('/users/search', methods=['GET'])
@require_admin
def search_users_groups():
    """Search workspace users and groups via SCIM API (uses SP token for broader visibility)."""
    headers = _get_sp_api_headers()
    if not headers:
        return jsonify({'error': 'SP token unavailable.'}), 401

    host = _get_host()
    query = request.args.get('q', '').strip()
    entity_type = request.args.get('type', 'all')  # 'users', 'groups', or 'all'

    if not query or len(query) < 2:
        return jsonify({'results': []}), 200

    results = []

    # Search users
    if entity_type in ('users', 'all'):
        try:
            params = {
                'filter': f'displayName co "{query}" or userName co "{query}"',
                'count': 10,
                'attributes': 'id,displayName,userName',
            }
            resp = http_requests.get(
                f'{host}/api/2.0/preview/scim/v2/Users',
                headers=headers,
                params=params,
                timeout=15,
            )
            if resp.status_code == 200:
                data = resp.json()
                for user in data.get('Resources', []):
                    results.append({
                        'id': user.get('id', ''),
                        'name': user.get('displayName', user.get('userName', '')),
                        'email': user.get('userName', ''),
                        'type': 'user',
                    })
        except Exception as e:
            logger.warning(f"User search failed: {e}")

    # Search groups
    if entity_type in ('groups', 'all'):
        try:
            params = {
                'filter': f'displayName co "{query}"',
                'count': 10,
                'attributes': 'id,displayName',
            }
            resp = http_requests.get(
                f'{host}/api/2.0/preview/scim/v2/Groups',
                headers=headers,
                params=params,
                timeout=15,
            )
            if resp.status_code == 200:
                data = resp.json()
                for group in data.get('Resources', []):
                    results.append({
                        'id': group.get('id', ''),
                        'name': group.get('displayName', ''),
                        'email': '',
                        'type': 'group',
                    })
        except Exception as e:
            logger.warning(f"Group search failed: {e}")

    # Search service principals
    if entity_type in ('service_principals', 'all'):
        try:
            params = {
                'filter': f'displayName co "{query}"',
                'count': 10,
                'attributes': 'id,displayName,applicationId',
            }
            resp = http_requests.get(
                f'{host}/api/2.0/preview/scim/v2/ServicePrincipals',
                headers=headers,
                params=params,
                timeout=15,
            )
            if resp.status_code == 200:
                data = resp.json()
                for sp in data.get('Resources', []):
                    results.append({
                        'id': sp.get('id', ''),
                        'name': sp.get('displayName', ''),
                        'email': sp.get('applicationId', ''),
                        'type': 'service_principal',
                    })
        except Exception as e:
            logger.warning(f"Service principal search failed: {e}")

    return jsonify({'results': results}), 200


@admin_bp.route('/permissions', methods=['GET'])
@require_admin
def permissions_page():
    """Render the permissions management page (tiles loaded dynamically via JS)."""
    return render_template(
        'admin/permissions.html',
        permissions=session.get('permissions', []),
    )


@admin_bp.route('/permissions', methods=['POST'])
@require_admin
def update_permissions():
    """Update group permissions from the matrix editor."""
    data = request.get_json()
    group_id = data.get('group_id')
    new_permissions = data.get('permissions', [])

    if not group_id:
        return jsonify({'error': 'group_id is required.'}), 400

    success = permissions_service.update_group_permissions(group_id, new_permissions)
    if success:
        audit_service.log_event(
            user=session.get('username', 'unknown'),
            action='update_permissions',
            resource=group_id,
            status='success',
            details=f"permissions={new_permissions}",
        )
        return jsonify({'status': 'updated', 'group_id': group_id}), 200
    return jsonify({'error': 'Failed to update permissions.'}), 400

# --- Permission Assignments (Delta table-backed) ---
# Tables: aw_serverless_stable_catalog.carelon.permission_types (reference)
#         aw_serverless_stable_catalog.carelon.permission_assignments (fact)

_CATALOG = 'aw_serverless_stable_catalog'
_SCHEMA = 'carelon'
_VOLUME = 'dxutility'
_VOLUME_FQN = f'{_CATALOG}.{_SCHEMA}.{_VOLUME}'
_PERM_TYPES_TABLE = f'{_CATALOG}.{_SCHEMA}.permission_types'
_PERM_ASSIGNMENTS_TABLE = f'{_CATALOG}.{_SCHEMA}.permission_assignments'
_VOLUME_GRANTS_TABLE = f'{_CATALOG}.{_SCHEMA}.volume_grants'

# Maps UI actions to the minimum UC volume privilege required
_ACTION_TO_UC_PRIVILEGE = {
    'browse': 'READ_VOLUME',
    'preview': 'READ_VOLUME',
    'download': 'READ_VOLUME',
    'detokenize': 'READ_VOLUME',
    'share': 'READ_VOLUME',
    'upload': 'WRITE_VOLUME',
    'delete': 'WRITE_VOLUME',
    'manage_permissions': 'MANAGE',
}


def _determine_uc_privileges(actions):
    """Given a list of app actions, return the set of UC privileges needed."""
    privileges = set()
    for action in actions:
        priv = _ACTION_TO_UC_PRIVILEGE.get(action)
        if priv:
            privileges.add(priv)
    return privileges


def _resolve_uc_principal_name(entity, headers, host):
    """Resolve the correct principal name for UC GRANT/REVOKE statements.

    UC requires:
      - Users: email address (e.g. user@domain.com)
      - Groups: group display name
      - Service Principals: application_id (UUID)
    """
    etype = entity.get('type', 'user')
    ename = entity.get('name', '')

    # If email was explicitly provided, use it
    if etype == 'user' and entity.get('email'):
        return entity['email']

    # For groups, display name is correct
    if etype == 'group':
        return ename

    # For service principals, look up applicationId
    if etype == 'service_principal':
        sp_id = entity.get('id', '')
        try:
            resp = http_requests.get(
                f"{host}/api/2.0/preview/scim/v2/ServicePrincipals/{sp_id}",
                headers=headers, timeout=15,
            )
            if resp.status_code == 200:
                return resp.json().get('applicationId', ename)
        except Exception:
            pass
        return ename

    # For users without email: look up via SCIM to get userName (email)
    user_id = entity.get('id', '')
    if user_id:
        try:
            resp = http_requests.get(
                f"{host}/api/2.0/preview/scim/v2/Users/{user_id}",
                headers=headers, timeout=15,
            )
            if resp.status_code == 200:
                return resp.json().get('userName', ename)
        except Exception:
            pass

    # Last resort: if name looks like an email, use it
    if '@' in ename:
        return ename

    logger.warning(f"Could not resolve UC principal for entity: {entity}")
    return ename


def _grant_uc_privilege(headers, host, entity_id, entity_name, entity_type, privilege, granted_by):
    """Execute GRANT <privilege> ON VOLUME and track in volume_grants table.

    Non-fatal: if GRANT fails (user may already have implicit access via
    ownership/admin), we still return True and track the intent.
    """
    # Check if already tracked as granted
    check_sql = f"""
        SELECT grant_id FROM {_VOLUME_GRANTS_TABLE}
        WHERE entity_name = '{entity_name.replace("'", "''")}'
          AND volume_fqn = '{_VOLUME_FQN}'
          AND uc_privilege = '{privilege}'
          AND is_active = TRUE
    """
    result = _execute_sql(headers, host, check_sql)
    if result:
        rows = result.get('result', {}).get('data_array', [])
        if rows:
            logger.info(f"UC privilege {privilege} already granted to {entity_name} on {_VOLUME_FQN}")
            return True

    # Execute the GRANT with full error capture
    quoted_entity = f"`{entity_name}`"
    grant_sql = f"GRANT {privilege.replace('_', ' ')} ON VOLUME {_VOLUME_FQN} TO {quoted_entity}"
    logger.info(f"Executing UC GRANT: {grant_sql}")

    grant_succeeded = False
    try:
        grant_resp = http_requests.post(
            f'{host}/api/2.0/sql/statements',
            headers=headers,
            json={
                'statement': grant_sql,
                'warehouse_id': os.environ.get('DATABRICKS_SQL_WAREHOUSE_ID', ''),
                'wait_timeout': '50s',
                'disposition': 'INLINE',
                'format': 'JSON_ARRAY',
            },
            timeout=120,
        )
        if grant_resp.status_code != 200:
            logger.error(f"UC GRANT HTTP error ({grant_resp.status_code}): {grant_resp.text[:800]}")
        else:
            grant_data = grant_resp.json()
            grant_status = grant_data.get('status', {}).get('state', '')
            if grant_status == 'SUCCEEDED':
                grant_succeeded = True
                logger.info(f"UC GRANT SUCCEEDED: {privilege} on {_VOLUME_FQN} to {entity_name}")
            else:
                err = grant_data.get('status', {}).get('error', {})
                logger.error(
                    f"UC GRANT SQL failed: privilege={privilege}, entity={entity_name}, "
                    f"status={grant_status}, error_code={err.get('error_code', '?')}, "
                    f"message={err.get('message', '?')}"
                )
    except Exception as exc:
        logger.error(f"UC GRANT exception for {entity_name}: {type(exc).__name__}: {exc}")

    if not grant_succeeded:
        # Non-fatal: user may already have implicit access via ownership/admin role
        logger.info(f"UC GRANT non-fatal skip for {entity_name} - user likely has implicit access")

    # Always track in volume_grants (records intent regardless of UC GRANT outcome)
    safe_name = entity_name.replace("'", "''")
    safe_id = entity_id.replace("'", "''") if entity_id else safe_name
    safe_by = granted_by.replace("'", "''")
    track_sql = f"""
        INSERT INTO {_VOLUME_GRANTS_TABLE}
        (entity_id, entity_type, entity_name, volume_fqn, uc_privilege, granted_by)
        VALUES ('{safe_id}', '{entity_type}', '{safe_name}', '{_VOLUME_FQN}', '{privilege}', '{safe_by}')
    """
    _execute_sql(headers, host, track_sql)
    return True


def _maybe_revoke_uc_privilege(headers, host, entity_id, entity_name, entity_type, privilege):
    """Check if any active permission_assignments still need this privilege.

    If none remain, REVOKE and mark volume_grants inactive.
    """
    actions_needing = [a for a, p in _ACTION_TO_UC_PRIVILEGE.items() if p == privilege]
    actions_list = ', '.join(f"'{a}'" for a in actions_needing)

    check_sql = f"""
        SELECT COUNT(*) AS cnt FROM {_PERM_ASSIGNMENTS_TABLE}
        WHERE entity_id = '{entity_id.replace("'", "''")}'
          AND permission_type = 'files'
          AND action IN ({actions_list})
          AND is_active = TRUE
    """
    result = _execute_sql(headers, host, check_sql)
    if result:
        rows = result.get('result', {}).get('data_array', [])
        if rows and int(rows[0][0]) > 0:
            logger.info(f"Still {rows[0][0]} active assignments needing {privilege} for {entity_id}")
            return

    # No remaining assignments need this privilege - REVOKE
    quoted_entity = f"`{entity_name}`"
    revoke_sql = f"REVOKE {privilege.replace('_', ' ')} ON VOLUME {_VOLUME_FQN} FROM {quoted_entity}"
    logger.info(f"Executing UC REVOKE: {revoke_sql}")
    _execute_sql(headers, host, revoke_sql)

    safe_name = entity_name.replace("'", "''")
    update_sql = f"""
        UPDATE {_VOLUME_GRANTS_TABLE}
        SET is_active = FALSE, revoked_at = current_timestamp()
        WHERE entity_name = '{safe_name}'
          AND volume_fqn = '{_VOLUME_FQN}'
          AND uc_privilege = '{privilege}'
          AND is_active = TRUE
    """
    _execute_sql(headers, host, update_sql)


def _execute_sql(headers, host, sql_text):
    """Execute a SQL statement via the Databricks SQL Statement API."""
    resp = http_requests.post(
        f'{host}/api/2.0/sql/statements',
        headers=headers,
        json={
            'statement': sql_text,
            'warehouse_id': os.environ.get('DATABRICKS_SQL_WAREHOUSE_ID', ''),
            'wait_timeout': '50s',
            'disposition': 'INLINE',
            'format': 'JSON_ARRAY',
        },
        timeout=120,
    )
    if resp.status_code != 200:
        logger.error(f"SQL exec failed ({resp.status_code}): {resp.text[:500]}")
        return None
    data = resp.json()
    status = data.get('status', {}).get('state', '')
    if status not in ('SUCCEEDED',):
        logger.error(f"SQL status: {status}, error: {data.get('status', {}).get('error', {})}")
        return None
    return data


@admin_bp.route('/permissions/types', methods=['GET'])
@require_admin
def get_permission_types():
    """Get all active permission types from the reference table."""
    headers = _get_sp_api_headers()
    if not headers:
        return jsonify({'error': 'No SP token available.'}), 401

    host = _get_host()
    sql = f"""
        SELECT permission_type, action, display_name, description, sort_order
        FROM {_PERM_TYPES_TABLE}
        WHERE is_active = TRUE
        ORDER BY permission_type, sort_order
    """
    result = _execute_sql(headers, host, sql)
    if result is None:
        return jsonify({'error': 'Failed to query permission types.'}), 500

    # Parse result
    columns = [col['name'] for col in result.get('manifest', {}).get('schema', {}).get('columns', [])]
    rows = result.get('result', {}).get('data_array', [])

    types_by_category = {}
    for row in rows:
        row_dict = dict(zip(columns, row))
        cat = row_dict['permission_type']
        if cat not in types_by_category:
            types_by_category[cat] = []
        types_by_category[cat].append({
            'action': row_dict['action'],
            'display_name': row_dict['display_name'],
            'description': row_dict['description'],
            'sort_order': row_dict['sort_order'],
        })

    return jsonify({'types': types_by_category}), 200


@admin_bp.route('/permissions/assign', methods=['POST'])
@require_admin
def assign_permissions():
    """Assign permissions: supports multiple actions + resource_path (folder-level)."""
    data = request.get_json()
    entities = data.get('entities', [])  # [{id, name, type}]
    category = data.get('permission_category', 'files')
    actions = data.get('actions', [])  # list of action strings
    resource_path = data.get('resource_path', '').strip()
    assigned_by = session.get('email', session.get('username', 'unknown'))

    # Backward compat: single action field
    if not actions and data.get('action'):
        actions = [data['action']]

    if not entities or not actions:
        return jsonify({'error': 'entities and actions are required.'}), 400

    headers = _get_sp_api_headers()
    if not headers:
        return jsonify({'error': 'No SP token available.'}), 401
    host = _get_host()

    # Build MERGE: one row per entity x action x resource_path
    values_rows = []
    for e in entities:
        eid = e.get('id', '').replace("'", "''")
        ename = e.get('name', '').replace("'", "''")
        etype = e.get('type', 'user').replace("'", "''")
        res_path = resource_path.replace("'", "''") if resource_path else ''
        for action in actions:
            act = action.replace("'", "''")
            values_rows.append(
                f"('{category}', '{act}', '{eid}', '{etype}', '{ename}', '{assigned_by}', '{res_path}')"
            )

    values_sql = ', '.join(values_rows)
    sql = f"""
        MERGE INTO {_PERM_ASSIGNMENTS_TABLE} AS target
        USING (
            SELECT * FROM VALUES {values_sql}
            AS src(permission_type, action, entity_id, entity_type, entity_name, assigned_by, resource_path)
        ) AS source
        ON target.permission_type = source.permission_type
           AND target.action = source.action
           AND target.entity_id = source.entity_id
           AND COALESCE(target.resource_path, '') = source.resource_path
        WHEN MATCHED AND target.is_active = FALSE THEN
            UPDATE SET is_active = TRUE, assigned_by = source.assigned_by, assigned_at = current_timestamp()
        WHEN NOT MATCHED THEN
            INSERT (permission_type, action, entity_id, entity_type, entity_name, assigned_by, is_active, resource_path)
            VALUES (source.permission_type, source.action, source.entity_id, source.entity_type, source.entity_name, source.assigned_by, TRUE,
                    CASE WHEN source.resource_path = '' THEN NULL ELSE source.resource_path END)
    """

    result = _execute_sql(headers, host, sql)
    if result is None:
        return jsonify({'error': 'Failed to save assignments.'}), 500

    # --- UC Privilege Grants ---
    uc_privileges = _determine_uc_privileges(actions)
    uc_grant_results = []
    if uc_privileges and category == 'files':
        for e in entities:
            etype = e.get('type', 'user')
            grant_name = _resolve_uc_principal_name(e, headers, host)
            for priv in uc_privileges:
                granted = _grant_uc_privilege(headers, host, e.get('id', ''), grant_name, etype, priv, assigned_by)
                uc_grant_results.append({'entity': grant_name, 'privilege': priv, 'granted': granted})

    audit_service.log_event(
        user=assigned_by,
        action='assign_permissions',
        resource=f'{category}/{actions}/{resource_path}',
        status='success',
        details=f"entities={[e.get('name') for e in entities]}, uc_grants={uc_grant_results}",
    )

    return jsonify({
        'status': 'assigned',
        'count': len(entities) * len(actions),
        'actions': actions,
        'uc_grants': uc_grant_results,
    }), 200


@admin_bp.route('/permissions/revoke', methods=['POST'])
@require_admin
def revoke_permissions():
    """Soft-revoke: set is_active=FALSE for entity+action+resource_path."""
    data = request.get_json()
    entity_id = data.get('entity_id', '').replace("'", "''")
    category = data.get('permission_category', 'files')
    action = data.get('action', '')
    resource_path = data.get('resource_path', '').strip().replace("'", "''")

    if not entity_id or not action:
        return jsonify({'error': 'entity_id and action are required.'}), 400

    headers = _get_sp_api_headers()
    if not headers:
        return jsonify({'error': 'No SP token available.'}), 401
    host = _get_host()

    resource_filter = f"AND resource_path = '{resource_path}'" if resource_path else "AND resource_path IS NULL"
    sql = f"""
        UPDATE {_PERM_ASSIGNMENTS_TABLE}
        SET is_active = FALSE
        WHERE permission_type = '{category}'
          AND action = '{action}'
          AND entity_id = '{entity_id}'
          {resource_filter}
          AND is_active = TRUE
    """

    result = _execute_sql(headers, host, sql)
    if result is None:
        return jsonify({'error': 'Failed to revoke.'}), 500

    # --- UC Privilege Revoke Check ---
    uc_priv = _ACTION_TO_UC_PRIVILEGE.get(action)
    if uc_priv and category == 'files':
        entity_type = data.get('entity_type', 'user')
        entity_for_lookup = {
            'id': entity_id,
            'name': data.get('entity_name', ''),
            'type': entity_type,
            'email': data.get('email', ''),
        }
        principal_name = _resolve_uc_principal_name(entity_for_lookup, headers, host)
        if principal_name:
            _maybe_revoke_uc_privilege(headers, host, entity_id, principal_name, entity_type, uc_priv)

    audit_service.log_event(
        user=session.get('username', 'unknown'),
        action='revoke_permission',
        resource=f'{category}/{action}/{entity_id}',
        status='success',
    )

    return jsonify({'status': 'revoked'}), 200


@admin_bp.route('/permissions/assignments', methods=['GET'])
@require_admin
def list_assignments():
    """List active assignments for a category (optionally filtered by action)."""
    category = request.args.get('category', 'files')
    action_filter = request.args.get('action', '').strip()

    headers = _get_sp_api_headers()
    if not headers:
        return jsonify({'error': 'No SP token available.'}), 401
    host = _get_host()

    where_clause = f"permission_type = '{category}' AND is_active = TRUE"
    if action_filter:
        where_clause += f" AND action = '{action_filter}'"

    sql = f"""
        SELECT action, entity_id, entity_type, entity_name, resource_path
        FROM {_PERM_ASSIGNMENTS_TABLE}
        WHERE {where_clause}
        ORDER BY action, resource_path, entity_name
    """

    result = _execute_sql(headers, host, sql)
    if result is None:
        return jsonify({'assignments': {}, 'category': category}), 200

    columns = [col['name'] for col in result.get('manifest', {}).get('schema', {}).get('columns', [])]
    rows = result.get('result', {}).get('data_array', [])

    assignments = {}
    for row in rows:
        row_dict = dict(zip(columns, row))
        act = row_dict['action']
        if act not in assignments:
            assignments[act] = []
        assignments[act].append({
            'id': row_dict['entity_id'],
            'name': row_dict['entity_name'],
            'type': row_dict['entity_type'],
            'resource_path': row_dict.get('resource_path', ''),
        })

    return jsonify({'assignments': assignments, 'category': category}), 200



@admin_bp.route('/volumes/folders', methods=['GET'])
@require_admin
def list_volume_folders():
    """List top-level folders under the root volume path (uses user token for Files API)."""
    from services.auth_service import AuthService
    auth_svc = AuthService()
    user_token = auth_svc.get_access_token()

    if not user_token:
        return jsonify({'error': 'No user token available.', 'folders': []}), 401

    host = _get_host()
    volume_root = os.environ.get('VOLUME_PATH', '/Volumes/aw_serverless_stable_catalog/carelon/dxutility')
    api_path = volume_root.lstrip('/')
    url = f"{host}/api/2.0/fs/directories/{api_path}"

    try:
        resp = http_requests.get(
            url,
            headers={'Authorization': f'Bearer {user_token}'},
            timeout=30,
        )
        if resp.status_code != 200:
            logger.error(f"List volume folders failed ({resp.status_code}): {resp.text[:300]}")
            return jsonify({'error': f'Failed to list folders (HTTP {resp.status_code})', 'folders': []}), resp.status_code

        data = resp.json()
        folders = []
        for entry in data.get('contents', []):
            if entry.get('is_directory', False):
                name = entry.get('name', entry.get('path', '').rstrip('/').split('/')[-1])
                folders.append({
                    'name': name,
                    'path': entry.get('path', ''),
                })
        return jsonify({'folders': folders, 'volume_root': volume_root}), 200
    except Exception as e:
        logger.error(f"Failed to list volume folders: {e}")
        return jsonify({'error': str(e), 'folders': []}), 500




# --- Create Databricks Jobs ---

@admin_bp.route('/jobs', methods=['GET'])
@require_admin
def jobs_page():
    """Render the Manage Databricks Jobs page — list + create."""
    return render_template(
        'admin/jobs.html',
        permissions=session.get('permissions', []),
    )




@admin_bp.route('/jobs/list', methods=['GET'])
@require_admin
def list_jobs():
    """List Databricks Jobs with pagination via REST API (uses SP token)."""
    headers = _get_sp_api_headers()
    if not headers:
        return jsonify({'error': 'No access token available.'}), 401

    host = _get_host()
    offset = int(request.args.get('offset', 0))
    limit = int(request.args.get('limit', 25))
    name_filter = request.args.get('name', '').strip()

    params = {
        'offset': offset,
        'limit': limit,
        'expand_tasks': 'false',
    }
    if name_filter:
        params['name'] = name_filter

    try:
        resp = http_requests.get(
            f'{host}/api/2.1/jobs/list',
            headers=headers,
            params=params,
            timeout=30,
        )

        # Safely parse response — may be empty or non-JSON
        try:
            data = resp.json()
        except (ValueError, Exception) as parse_err:
            logger.error(f"Jobs list parse error: {parse_err}, status={resp.status_code}, body={resp.text[:500]}")
            return jsonify({
                'error': f'Invalid response from Jobs API (HTTP {resp.status_code}). Ensure the app has proper token scopes.',
                'details': resp.text[:200],
            }), 502

        if resp.status_code != 200:
            return jsonify({'error': data.get('message', f'Jobs API returned {resp.status_code}'), 'details': data}), resp.status_code

        # Success — extract job items
        jobs = data.get('jobs', [])
        has_more = data.get('has_more', False)

        job_items = []
        for job in jobs:
            settings = job.get('settings', {})
            schedule = settings.get('schedule', {})
            job_items.append({
                'job_id': job.get('job_id'),
                'name': settings.get('name', 'Untitled'),
                'creator_user_name': job.get('creator_user_name', ''),
                'created_time': job.get('created_time', 0),
                'schedule': schedule.get('quartz_cron_expression', '\u2014'),
                'schedule_tz': schedule.get('timezone_id', ''),
                'tags': settings.get('tags', {}),
                'format': settings.get('format', ''),
            })

        return jsonify({
            'jobs': job_items,
            'has_more': has_more,
            'offset': offset,
            'limit': limit,
            'total_count': offset + len(job_items),
        }), 200

    except Exception as e:
        logger.error(f"Failed to list jobs: {e}")
        return jsonify({'error': str(e)}), 500


@admin_bp.route('/jobs/<int:job_id>/runs', methods=['GET'])
@require_admin
def list_job_runs(job_id):
    """List runs for a specific job via REST API (uses SP token)."""
    headers = _get_sp_api_headers()
    if not headers:
        return jsonify({'error': 'No access token available (SP credentials missing).'}), 401

    host = _get_host()
    limit = int(request.args.get('limit', 10))
    offset = int(request.args.get('offset', 0))

    params = {
        'job_id': job_id,
        'limit': limit,
        'offset': offset,
    }

    try:
        resp = http_requests.get(
            f'{host}/api/2.1/jobs/runs/list',
            headers=headers,
            params=params,
            timeout=30,
        )

        try:
            data = resp.json()
        except (ValueError, Exception) as parse_err:
            logger.error(f"Job runs parse error: {parse_err}, status={resp.status_code}")
            return jsonify({'error': f'Invalid response (HTTP {resp.status_code})'}), 502

        if resp.status_code != 200:
            return jsonify({'error': data.get('message', f'Runs API returned {resp.status_code}')}), resp.status_code

        runs = data.get('runs', [])
        has_more = data.get('has_more', False)

        run_items = []
        for run in runs:
            state = run.get('state', {})
            run_items.append({
                'run_id': run.get('run_id'),
                'run_name': run.get('run_name', ''),
                'start_time': run.get('start_time', 0),
                'end_time': run.get('end_time', 0),
                'state': state.get('result_state', state.get('life_cycle_state', 'UNKNOWN')),
                'life_cycle_state': state.get('life_cycle_state', ''),
                'run_page_url': run.get('run_page_url', ''),
                'run_duration': run.get('run_duration', 0),
                'trigger': run.get('trigger', 'UNKNOWN'),
            })

        return jsonify({
            'runs': run_items,
            'has_more': has_more,
            'job_id': job_id,
        }), 200

    except Exception as e:
        logger.error(f"Failed to list job runs: {e}")
        return jsonify({'error': str(e)}), 500


@admin_bp.route('/jobs', methods=['POST'])
@require_admin
def create_job():
    """Create a Databricks Job via REST API (uses SP token)."""
    headers = _get_sp_api_headers()
    if not headers:
        return jsonify({'error': 'No access token available.'}), 401

    data = request.get_json()
    host = _get_host()

    # Build job payload
    task = {
        'task_key': 'main_task',
        'notebook_task': {
            'notebook_path': data.get('notebook_path', ''),
        },
    }

    # Attach to existing cluster or let it use default new job cluster
    cluster_id = data.get('cluster_id', '').strip()
    if cluster_id:
        task['existing_cluster_id'] = cluster_id

    job_payload = {
        'name': data.get('job_name', 'Untitled Job'),
        'tasks': [task],
        'max_retries': int(data.get('max_retries', 1)),
        'timeout_seconds': int(data.get('timeout_seconds', 3600)),
    }

    # Schedule (optional)
    cron = data.get('schedule_cron', '').strip()
    if cron:
        job_payload['schedule'] = {
            'quartz_cron_expression': cron,
            'timezone_id': data.get('timezone', 'UTC'),
        }

    # Tags (optional)
    tags_str = data.get('tags', '').strip()
    if tags_str:
        try:
            job_payload['tags'] = json.loads(tags_str)
        except json.JSONDecodeError:
            return jsonify({'error': 'Invalid JSON in tags field.'}), 400

    try:
        resp = http_requests.post(
            f'{host}/api/2.1/jobs/create',
            headers=headers,
            json=job_payload,
            timeout=30,
        )
        try:
            result = resp.json()
        except (ValueError, Exception):
            return jsonify({'error': f'Invalid response (HTTP {resp.status_code})', 'details': resp.text[:200]}), 502
        if resp.status_code == 200:
            audit_service.log_event(
                user=session.get('username', 'unknown'),
                action='create_job',
                resource=result.get('job_id', ''),
                status='success',
                details=f"name={data.get('job_name')}",
            )
            return jsonify({'status': 'created', 'job_id': result.get('job_id'), 'response': result}), 200
        return jsonify({'error': result.get('message', 'Unknown error'), 'response': result}), resp.status_code
    except Exception as e:
        logger.error(f"Failed to create job: {e}")
        return jsonify({'error': str(e)}), 500


# --- ABAC Policies ---

@admin_bp.route('/abac-policies', methods=['GET'])
@require_admin
def abac_policies_page():
    """Render the ABAC Policies setup page."""
    return render_template(
        'admin/abac_policies.html',
        permissions=session.get('permissions', []),
    )


@admin_bp.route('/abac-policies', methods=['POST'])
@require_admin
def create_abac_policy():
    """Create an ABAC policy (row filter or column mask) via SQL statement API."""
    headers = _get_user_api_headers()
    if not headers:
        return jsonify({'error': 'No access token available.'}), 401

    data = request.get_json()
    host = _get_host()

    policy_type = data.get('policy_type', 'column_mask')
    catalog = data.get('catalog', 'aw_serverless_stable_catalog')
    schema = data.get('schema', 'carelon')
    table_name = data.get('table_name', '')
    policy_name = data.get('policy_name', '')

    if not table_name or not policy_name:
        return jsonify({'error': 'Policy name and table name are required.'}), 400

    full_table = f"{catalog}.{schema}.{table_name}"

    if policy_type == 'row_filter':
        filter_expr = data.get('filter_expression', '')
        if not filter_expr:
            return jsonify({'error': 'Filter expression is required for row filters.'}), 400
        sql = f"ALTER TABLE {full_table} SET ROW FILTER {catalog}.{schema}.{policy_name} ON ();"
        # First create the function
        create_fn_sql = (
            f"CREATE OR REPLACE FUNCTION {catalog}.{schema}.{policy_name}()\n"
            f"RETURNS BOOLEAN\n"
            f"RETURN ({filter_expr});"
        )
    else:  # column_mask
        column_name = data.get('column_name', '')
        mask_function = data.get('mask_function', '')
        custom_expr = data.get('custom_mask_expression', '')

        if not column_name:
            return jsonify({'error': 'Column name is required for column masks.'}), 400

        if mask_function == 'custom':
            mask_expr = custom_expr.replace('{col}', column_name)
        else:
            mask_expr = mask_function.replace('{col}', column_name)

        if not mask_expr:
            return jsonify({'error': 'Mask expression is required.'}), 400

        # Create the masking function
        create_fn_sql = (
            f"CREATE OR REPLACE FUNCTION {catalog}.{schema}.{policy_name}({column_name}_val STRING)\n"
            f"RETURNS STRING\n"
            f"RETURN {mask_expr.replace(column_name, column_name + '_val')};"
        )
        sql = f"ALTER TABLE {full_table} ALTER COLUMN {column_name} SET MASK {catalog}.{schema}.{policy_name};"

    # Return the SQL preview and execute
    try:
        # Execute the function creation
        sql_payload = {
            'statement': create_fn_sql,
            'warehouse_id': os.environ.get('SQL_WAREHOUSE_ID', ''),
        }

        # If no warehouse configured, return SQL for manual execution
        if not sql_payload.get('warehouse_id'):
            return jsonify({
                'status': 'preview',
                'message': 'No SQL warehouse configured. Execute these statements manually:',
                'sql_statements': [create_fn_sql, sql],
            }), 200

        resp = http_requests.post(
            f'{host}/api/2.0/sql/statements',
            headers=headers,
            json=sql_payload,
            timeout=30,
        )

        if resp.status_code == 200:
            # Now apply the policy
            apply_payload = {
                'statement': sql,
                'warehouse_id': sql_payload['warehouse_id'],
            }
            resp2 = http_requests.post(
                f'{host}/api/2.0/sql/statements',
                headers=headers,
                json=apply_payload,
                timeout=30,
            )
            audit_service.log_event(
                user=session.get('username', 'unknown'),
                action='create_abac_policy',
                resource=f"{full_table}/{policy_name}",
                status='success',
                details=f"type={policy_type}",
            )
            return jsonify({
                'status': 'created',
                'sql_statements': [create_fn_sql, sql],
                'response': resp2.json() if resp2.status_code == 200 else resp.json(),
            }), 200

        return jsonify({'error': resp.json().get('message', 'SQL execution failed'), 'sql': create_fn_sql}), resp.status_code
    except Exception as e:
        logger.error(f"Failed to create ABAC policy: {e}")
        return jsonify({'error': str(e), 'sql_statements': [create_fn_sql, sql]}), 500


# --- Create Job Clusters ---

@admin_bp.route('/clusters', methods=['GET'])
@require_admin
def clusters_page():
    """Render the Create Job Clusters page."""
    return render_template(
        'admin/clusters.html',
        permissions=session.get('permissions', []),
    )


@admin_bp.route('/clusters', methods=['POST'])
@require_admin
def create_cluster():
    """Create a Job Cluster via REST API (uses SP token)."""
    headers = _get_sp_api_headers()
    if not headers:
        return jsonify({'error': 'No access token available.'}), 401

    data = request.get_json()
    host = _get_host()

    cluster_payload = {
        'cluster_name': data.get('cluster_name', 'job-cluster'),
        'spark_version': data.get('spark_version', '15.4.x-scala2.12'),
        'node_type_id': data.get('node_type_id', 'i3.xlarge'),
        'autotermination_minutes': int(data.get('autotermination_minutes', 30)),
    }

    # Driver node type
    driver_type = data.get('driver_node_type_id', '').strip()
    if driver_type:
        cluster_payload['driver_node_type_id'] = driver_type

    # Workers / autoscaling
    if data.get('enable_autoscale'):
        cluster_payload['autoscale'] = {
            'min_workers': int(data.get('min_workers', 1)),
            'max_workers': int(data.get('max_workers', 8)),
        }
    else:
        cluster_payload['num_workers'] = int(data.get('num_workers', 2))

    # Spot policy
    spot_policy = data.get('spot_policy', 'COST_OPTIMIZED')
    cluster_payload['aws_attributes'] = {
        'availability': spot_policy,
        'first_on_demand': 1,
    }

    # Spark config
    spark_conf_str = data.get('spark_conf', '').strip()
    if spark_conf_str:
        spark_conf = {}
        for line in spark_conf_str.split('\n'):
            if '=' in line:
                key, val = line.split('=', 1)
                spark_conf[key.strip()] = val.strip()
        if spark_conf:
            cluster_payload['spark_conf'] = spark_conf

    # Tags
    tags_str = data.get('tags', '').strip()
    if tags_str:
        try:
            custom_tags = json.loads(tags_str)
            cluster_payload['custom_tags'] = custom_tags
        except json.JSONDecodeError:
            return jsonify({'error': 'Invalid JSON in tags field.'}), 400

    try:
        resp = http_requests.post(
            f'{host}/api/2.0/clusters/create',
            headers=headers,
            json=cluster_payload,
            timeout=30,
        )
        try:
            result = resp.json()
        except (ValueError, Exception):
            return jsonify({'error': f'Invalid response (HTTP {resp.status_code})', 'details': resp.text[:200]}), 502
        if resp.status_code == 200:
            audit_service.log_event(
                user=session.get('username', 'unknown'),
                action='create_cluster',
                resource=result.get('cluster_id', ''),
                status='success',
                details=f"name={data.get('cluster_name')}",
            )
            return jsonify({'status': 'created', 'cluster_id': result.get('cluster_id'), 'response': result}), 200
        return jsonify({'error': result.get('message', 'Unknown error'), 'response': result}), resp.status_code
    except Exception as e:
        logger.error(f"Failed to create cluster: {e}")
        return jsonify({'error': str(e)}), 500


# --- Audit Log ---

@admin_bp.route('/audit', methods=['GET'])
@require_admin
def audit_log():
    """Render the audit log viewer."""
    user_filter = request.args.get('user')
    action_filter = request.args.get('action')
    events = audit_service.get_events(user=user_filter, action=action_filter, limit=200)
    return render_template(
        'admin/audit.html',
        events=events,
        permissions=session.get('permissions', []),
    )


# --- Token Diagnostics (temporary) ---

@admin_bp.route('/token-debug', methods=['GET'])
@require_admin
def token_debug():
    """Diagnostic: inspect forwarded headers and token claims."""
    import base64

    token = request.headers.get('X-Forwarded-Access-Token', '')
    email = request.headers.get('X-Forwarded-Email', '')
    user = request.headers.get('X-Forwarded-User', '')

    info = {
        'x_forwarded_email': email,
        'x_forwarded_user': user,
        'token_present': bool(token),
        'token_length': len(token),
        'token_prefix': token[:20] + '...' if token else '',
        'is_jwt': token.count('.') == 2 if token else False,
        'claims': None,
    }

    # Try to decode JWT payload (without verification) to check scopes
    if token and token.count('.') == 2:
        try:
            payload_b64 = token.split('.')[1]
            # Add padding
            padding = 4 - len(payload_b64) % 4
            if padding != 4:
                payload_b64 += '=' * padding
            payload_bytes = base64.urlsafe_b64decode(payload_b64)
            import json as json_mod
            claims = json_mod.loads(payload_bytes)
            info['claims'] = {
                'iss': claims.get('iss', ''),
                'sub': claims.get('sub', ''),
                'aud': claims.get('aud', ''),
                'scp': claims.get('scp', claims.get('scope', '')),
                'azp': claims.get('azp', ''),
                'exp': claims.get('exp', ''),
            }
        except Exception as e:
            info['claims_error'] = str(e)

    return jsonify(info), 200
