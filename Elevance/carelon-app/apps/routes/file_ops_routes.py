"""File Explorer routes — Browse, Download, Delete, Preview, Share.

Provides the File Explorer page where users can:
1. See folders they have access to (from permission_assignments)
2. Browse files within permitted folders
3. Perform actions (preview, download, share, detokenize, delete) based on their permissions
"""

import os
import logging
import requests as http_requests
from flask import Blueprint, render_template, request, jsonify, session, current_app
from middleware.auth_middleware import login_required
from services.volume_browser_service import VolumeBrowserService
from services.audit_service import audit_service

logger = logging.getLogger(__name__)
file_ops_bp = Blueprint('file_ops', __name__, url_prefix='/files')
volume_browser = VolumeBrowserService()

_CATALOG = 'aw_serverless_stable_catalog'
_SCHEMA = 'carelon'
_VOLUME = 'dxutility'
_VOLUME_ROOT = f'/Volumes/{_CATALOG}/{_SCHEMA}/{_VOLUME}'
_PERM_ASSIGNMENTS_TABLE = f'{_CATALOG}.{_SCHEMA}.permission_assignments'


def _get_user_token():
    """Get user's forwarded access token."""
    return request.headers.get('X-Forwarded-Access-Token', '')


def _get_user_email():
    """Get current user's email."""
    email = request.headers.get('X-Forwarded-Email', '')
    if not email:
        email = session.get('email', session.get('username', ''))
    return email


def _is_admin():
    """Check if the current user is an admin."""
    if session.get('is_admin'):
        return True
    if 'admin' in session.get('groups', []):
        return True
    email = _get_user_email()
    admin_users = current_app.config.get('ADMIN_USERS', [])
    return email.lower() in [e.lower() for e in admin_users]


# All file actions an admin can perform
_ALL_ACTIONS = ['browse', 'upload', 'download', 'delete', 'preview', 'detokenize', 'share']
_HIDDEN_FOLDER_NAMES = {'templates'}  # Folders hidden from File Explorer (managed separately)


def _get_sp_headers():
    """Get SP token headers for SQL queries."""
    host = os.environ.get('DATABRICKS_HOST', '').rstrip('/')
    if host and not host.startswith('http'):
        host = f'https://{host}'
    sp_client_id = os.environ.get('DATABRICKS_CLIENT_ID', '')
    sp_client_secret = os.environ.get('DATABRICKS_CLIENT_SECRET', '')
    if not sp_client_id or not sp_client_secret:
        return None, None
    try:
        resp = http_requests.post(
            f'{host}/oidc/v1/token',
            data={'grant_type': 'client_credentials', 'client_id': sp_client_id,
                  'client_secret': sp_client_secret, 'scope': 'all-apis'},
            timeout=10,
        )
        if resp.status_code == 200:
            token = resp.json().get('access_token')
            return {'Authorization': f'Bearer {token}', 'Content-Type': 'application/json'}, host
    except Exception as e:
        logger.error(f"SP token error: {e}")
    return None, None


def _execute_sql(headers, host, sql_text):
    """Execute SQL via Statement API."""
    resp = http_requests.post(
        f'{host}/api/2.0/sql/statements',
        headers=headers,
        json={
            'statement': sql_text,
            'warehouse_id': os.environ.get('DATABRICKS_SQL_WAREHOUSE_ID', ''),
            'wait_timeout': '30s',
            'disposition': 'INLINE',
            'format': 'JSON_ARRAY',
        },
        timeout=60,
    )
    if resp.status_code != 200:
        logger.error(f"SQL exec failed ({resp.status_code}): {resp.text[:300]}")
        return None
    data = resp.json()
    if data.get('status', {}).get('state') != 'SUCCEEDED':
        logger.error(f"SQL status: {data.get('status')}")
        return None
    return data


# ======== Page Route ========

@file_ops_bp.route('/', methods=['GET'])
@file_ops_bp.route('/browse', methods=['GET'])
@login_required
def file_explorer():
    """Render the File Explorer page."""
    return render_template(
        'file_explorer.html',
        permissions=session.get('permissions', []),
        volume_root=_VOLUME_ROOT,
    )


# ======== API: User's Permitted Folders + Actions ========

@file_ops_bp.route('/api/my-access', methods=['GET'])
@login_required
def get_my_access():
    """Return the current user's permitted folders AND actions per folder.

    Returns: {
        folders: [
            { path, display_name, actions: ['browse','upload','download',...] }
        ]
    }
    """
    user_email = _get_user_email()
    if not user_email:
        return jsonify({'folders': [], 'error': 'Could not determine user identity.'}), 401

    # Admin users get access to ALL folders with ALL actions
    if _is_admin():
        return _get_admin_all_folders(user_email)

    headers, host = _get_sp_headers()
    if not headers:
        return jsonify({'folders': [], 'error': 'SP token unavailable.'}), 500

    safe_email = user_email.replace("'", "''")

    sql = f"""
        SELECT resource_path, action, entity_name, entity_type
        FROM {_PERM_ASSIGNMENTS_TABLE}
        WHERE permission_type = 'files'
          AND is_active = TRUE
          AND resource_path IS NOT NULL
          AND resource_path != ''
          AND (
              entity_name = '{safe_email}'
              OR entity_type = 'group'
          )
        ORDER BY resource_path, action
    """

    result = _execute_sql(headers, host, sql)
    if result is None:
        return jsonify({'folders': [], 'error': 'Failed to query permissions.'}), 500

    columns = [col['name'] for col in result.get('manifest', {}).get('schema', {}).get('columns', [])]
    rows = result.get('result', {}).get('data_array', [])

    # Group by folder path
    folder_map = {}  # path -> set of actions
    for row in rows:
        row_dict = dict(zip(columns, row))
        path = row_dict.get('resource_path', '')
        action = row_dict.get('action', '')
        if path:
            if path not in folder_map:
                folder_map[path] = set()
            folder_map[path].add(action)

    _templates_path = f'{_VOLUME_ROOT}/templates'
    folders = []
    for path, actions in sorted(folder_map.items()):
        # Hide templates folder
        if path == _templates_path or path.startswith(_templates_path + '/'):
            continue
        display = path.replace(_VOLUME_ROOT + '/', '').replace(_VOLUME_ROOT, 'Root')
        folders.append({
            'path': path,
            'display_name': display or 'Root',
            'actions': sorted(list(actions)),
        })

    logger.info(f"File Explorer access for {user_email}: {len(folders)} folders")
    return jsonify({'folders': folders, 'user': user_email}), 200


def _get_admin_all_folders(user_email):
    """Admin override: list ALL top-level folders from the volume with all actions."""
    token = _get_user_token()
    if not token:
        return jsonify({'folders': [], 'error': 'User token unavailable.'}), 401

    try:
        result = volume_browser.list_directory(
            volume_path=_VOLUME_ROOT, subfolder='', user_token=token
        )
        items = result.get('items', [])
        folders = []

        # Add Root as a browseable entry
        folders.append({
            'path': _VOLUME_ROOT,
            'display_name': 'Root',
            'actions': _ALL_ACTIONS,
        })

        # Add all top-level subdirectories (excluding hidden folders)
        for item in items:
            if item.get('is_directory'):
                if item['name'] in _HIDDEN_FOLDER_NAMES:
                    continue
                folder_path = f"{_VOLUME_ROOT}/{item['name']}"
                folders.append({
                    'path': folder_path,
                    'display_name': item['name'],
                    'actions': _ALL_ACTIONS,
                })

        logger.info(f"File Explorer ADMIN access for {user_email}: {len(folders)} folders (all)")
        return jsonify({'folders': folders, 'user': user_email, 'is_admin': True}), 200

    except Exception as e:
        logger.error(f"Admin folder listing failed: {e}")
        # Fallback: just return root
        return jsonify({
            'folders': [{'path': _VOLUME_ROOT, 'display_name': 'Root', 'actions': _ALL_ACTIONS}],
            'user': user_email,
            'is_admin': True,
        }), 200



# ======== API: Folder Children (for lazy-loading tree) ========

@file_ops_bp.route('/api/tree', methods=['GET'])
@login_required
def get_folder_children():
    """Return immediate child folders for a given path (lazy tree expansion).

    Query params:
        path: full volume path (default: VOLUME_ROOT for top-level)

    Returns: { children: [{ name, path, has_children }] }
    Used by the folder tree panel for on-demand expansion.
    """
    folder_path = request.args.get('path', _VOLUME_ROOT)

    if not folder_path.startswith(_VOLUME_ROOT):
        return jsonify({'children': [], 'error': 'Invalid path.'}), 403

    token = _get_user_token()
    if not token:
        return jsonify({'children': [], 'error': 'User token unavailable.'}), 401

    subfolder = folder_path[len(_VOLUME_ROOT):].strip('/')

    try:
        result = volume_browser.list_directory(
            volume_path=_VOLUME_ROOT, subfolder=subfolder, user_token=token
        )
        items = result.get('items', [])
        children = []
        for item in items:
            if item.get('is_directory'):
                # Hide templates folder from tree at the root level
                if item['name'] in _HIDDEN_FOLDER_NAMES and folder_path == _VOLUME_ROOT:
                    continue
                children.append({
                    'name': item['name'],
                    'path': item['path'],
                    'has_children': True,  # assume expandable; UI will try
                })

        return jsonify({'children': children, 'parent_path': folder_path}), 200
    except Exception as e:
        error_msg = str(e)
        logger.error(f"Tree listing failed for {folder_path}: {error_msg}")
        return jsonify({'children': [], 'error': error_msg}), 500


# ======== API: List Files in Folder ========

@file_ops_bp.route('/api/list', methods=['GET'])
@login_required
def list_files():
    """List files in a permitted folder.

    Query params:
        folder_path: full volume path (e.g., /Volumes/catalog/schema/volume/subfolder)
    """
    folder_path = request.args.get('folder_path', '')
    if not folder_path:
        return jsonify({'files': [], 'error': 'Missing folder_path parameter.'}), 400

    # Security: verify this is under our volume root
    if not folder_path.startswith(_VOLUME_ROOT):
        return jsonify({'files': [], 'error': 'Invalid folder path.'}), 403

    token = _get_user_token()
    if not token:
        return jsonify({'files': [], 'error': 'User token not available.'}), 401

    # Extract subfolder relative to volume root
    subfolder = folder_path[len(_VOLUME_ROOT):].strip('/')

    result = volume_browser.list_directory(
        volume_path=_VOLUME_ROOT,
        subfolder=subfolder,
        user_token=token,
    )

    if result.get('error'):
        return jsonify({'files': [], 'error': result['error']}), 500

    # Separate files and subfolders
    items = result.get('items', [])
    files = []
    subfolders = []
    for item in items:
        entry = {
            'name': item['name'],
            'path': item['path'],
            'size': item.get('size', 0),
            'last_modified': item.get('last_modified', ''),
        }
        if item.get('is_directory'):
            entry['type'] = 'folder'
            subfolders.append(entry)
        else:
            entry['type'] = 'file'
            # Infer file extension
            ext = item['name'].rsplit('.', 1)[-1].lower() if '.' in item['name'] else ''
            entry['extension'] = ext
            files.append(entry)

    return jsonify({
        'files': files,
        'subfolders': subfolders,
        'folder_path': folder_path,
        'count': len(files),
    }), 200


# ======== API: Download ========

@file_ops_bp.route('/api/download', methods=['GET'])
@login_required
def download_file():
    """Download a file from the Volume (streams via Files API)."""
    file_path = request.args.get('file_path', '')
    if not file_path or not file_path.startswith(_VOLUME_ROOT):
        return jsonify({'error': 'Invalid file path.'}), 400

    token = _get_user_token()
    if not token:
        return jsonify({'error': 'User token not available.'}), 401

    host = os.environ.get('DATABRICKS_HOST', '').rstrip('/')
    if host and not host.startswith('http'):
        host = f'https://{host}'

    api_path = file_path.lstrip('/')
    url = f"{host}/api/2.0/fs/files/{api_path}"

    try:
        resp = http_requests.get(
            url,
            headers={'Authorization': f'Bearer {token}'},
            stream=True,
            timeout=120,
        )
        if resp.status_code != 200:
            return jsonify({'error': f'Download failed (HTTP {resp.status_code})'}), resp.status_code

        filename = file_path.split('/')[-1]
        from flask import Response
        return Response(
            resp.iter_content(chunk_size=8192),
            headers={
                'Content-Disposition': f'attachment; filename="{filename}"',
                'Content-Type': resp.headers.get('Content-Type', 'application/octet-stream'),
            },
        )
    except Exception as e:
        logger.error(f"Download failed: {e}")
        return jsonify({'error': str(e)}), 500


# ======== API: Delete ========

@file_ops_bp.route('/api/delete', methods=['DELETE'])
@login_required
def delete_file():
    """Delete a file from the Volume."""
    file_path = request.args.get('file_path', '')
    if not file_path or not file_path.startswith(_VOLUME_ROOT):
        return jsonify({'error': 'Invalid file path.'}), 400

    token = _get_user_token()
    if not token:
        return jsonify({'error': 'User token not available.'}), 401

    host = os.environ.get('DATABRICKS_HOST', '').rstrip('/')
    if host and not host.startswith('http'):
        host = f'https://{host}'

    api_path = file_path.lstrip('/')
    url = f"{host}/api/2.0/fs/files/{api_path}"

    try:
        resp = http_requests.delete(
            url,
            headers={'Authorization': f'Bearer {token}'},
            timeout=30,
        )
        if resp.status_code in (200, 204):
            user_email = _get_user_email()
            audit_service.log_event(
                user=user_email,
                action='delete',
                resource=file_path,
                status='success',
            )
            return jsonify({'status': 'deleted', 'path': file_path}), 200
        return jsonify({'error': f'Delete failed (HTTP {resp.status_code})'}), resp.status_code
    except Exception as e:
        logger.error(f"Delete failed: {e}")
        return jsonify({'error': str(e)}), 500


# ======== API: Preview ========

@file_ops_bp.route('/api/preview', methods=['GET'])
@login_required
def preview_file():
    """Return the first N lines of a file for preview.

    Query params:
        file_path: full Volume path to the file
        lines: number of lines to return (default 50, max 200)
    """
    file_path = request.args.get('file_path', '')
    max_lines = min(int(request.args.get('lines', 50)), 200)

    if not file_path or not file_path.startswith(_VOLUME_ROOT):
        return jsonify({'error': 'Invalid file path.'}), 400

    token = _get_user_token()
    if not token:
        return jsonify({'error': 'User token not available.'}), 401

    host = os.environ.get('DATABRICKS_HOST', '').rstrip('/')
    if host and not host.startswith('http'):
        host = f'https://{host}'

    api_path = file_path.lstrip('/')
    url = f"{host}/api/2.0/fs/files/{api_path}"

    try:
        resp = http_requests.get(
            url,
            headers={'Authorization': f'Bearer {token}'},
            timeout=30,
            stream=True,
        )

        if resp.status_code != 200:
            return jsonify({'error': f'Cannot read file (HTTP {resp.status_code})'}), resp.status_code

        # Read content up to max_lines — explicitly decode since Files API
        # returns application/octet-stream with no charset header
        lines_read = []
        truncated = False
        for raw_line in resp.iter_lines():
            line = raw_line.decode('utf-8', errors='replace') if isinstance(raw_line, bytes) else raw_line
            lines_read.append(line)
            if len(lines_read) >= max_lines:
                truncated = True
                break

        resp.close()

        # Detect delimiter and parse as tabular data if possible
        delimiter = None
        headers_row = []
        data_rows = []
        phi_columns = []  # indices of columns that appear masked

        if lines_read:
            # Auto-detect delimiter from first line
            first_line = lines_read[0]
            for delim in ('|', '\t', ','):
                if delim in first_line:
                    delimiter = delim
                    break

        if delimiter and len(lines_read) > 1:
            headers_row = [h.strip() for h in lines_read[0].split(delimiter)]
            data_rows = []
            for line in lines_read[1:]:
                row = [c.strip() for c in line.split(delimiter)]
                data_rows.append(row)

            # Detect PHI (masked) columns by checking for masking patterns
            # Patterns: ***-**-XXXX, (***) ***-XXXX, ****-**-**, TOK_, *@, X******
            import re
            mask_patterns = [
                r'^\*{2,}',             # starts with multiple asterisks
                r'\*{2,}',             # contains multiple consecutive asterisks
                r'^TOK_[A-F0-9]+$',     # hash-based token
                r'^\(.{0,4}\)\s*\*',  # phone mask: (***) ***-
            ]
            combined_re = re.compile('|'.join(mask_patterns))

            for col_idx in range(len(headers_row)):
                masked_count = 0
                sample_count = 0
                for row in data_rows[:20]:  # sample first 20 rows
                    if col_idx < len(row) and row[col_idx]:
                        sample_count += 1
                        if combined_re.search(row[col_idx]):
                            masked_count += 1
                # If >50% of sampled values look masked, flag as PHI
                if sample_count > 0 and masked_count / sample_count > 0.5:
                    phi_columns.append(col_idx)

        return jsonify({
            'file_path': file_path,
            'file_name': file_path.split('/')[-1],
            'lines': lines_read,
            'line_count': len(lines_read),
            'truncated': truncated,
            'tabular': delimiter is not None and len(headers_row) > 0,
            'delimiter': delimiter,
            'headers': headers_row,
            'rows': data_rows,
            'phi_columns': phi_columns,
        }), 200

    except Exception as e:
        logger.error(f"Preview failed: {e}")
        return jsonify({'error': str(e)}), 500


# ======== API: Detokenize (Download-Only Stream) ========

@file_ops_bp.route('/api/detokenize', methods=['GET'])
@login_required
def detokenize_file():
    """Detokenize a file and stream the result as a download.

    The detokenized data is NEVER stored — it is streamed directly
    to the user's browser as a file download.

    Query params:
        file_path: full Volume path to the tokenized file
    """
    file_path = request.args.get('file_path', '')
    if not file_path or not file_path.startswith(_VOLUME_ROOT):
        return jsonify({'error': 'Invalid file path.'}), 400

    token = _get_user_token()
    if not token:
        return jsonify({'error': 'User token not available.'}), 401

    host = os.environ.get('DATABRICKS_HOST', '').rstrip('/')
    if host and not host.startswith('http'):
        host = f'https://{host}'

    api_path = file_path.lstrip('/')
    url = f"{host}/api/2.0/fs/files/{api_path}"

    try:
        # 1. Fetch the tokenized file content
        resp = http_requests.get(
            url,
            headers={'Authorization': f'Bearer {token}'},
            timeout=60,
        )

        if resp.status_code != 200:
            return jsonify({'error': f'Cannot read file (HTTP {resp.status_code})'}), resp.status_code

        file_content = resp.text
        lines = file_content.split('\n')

        if len(lines) < 2:
            return jsonify({'error': 'File is empty or has no data rows.'}), 400

        # 2. Mock detokenization — reverse the masking
        # In production, this would call the Protegrity DSG REST API
        # For now, we simply return the tokenized content as-is with a header note
        # (Real detokenization requires the original mapping which Protegrity maintains)
        header_line = lines[0]
        detokenized_lines = [f"# DETOKENIZED (mock) — original PHI values not available in mock mode"]
        detokenized_lines.append(header_line)
        detokenized_lines.extend(lines[1:])
        detokenized_content = '\n'.join(detokenized_lines)

        # 3. Stream as download — NEVER stored
        file_name = file_path.split('/')[-1]
        base_name = file_name.replace('_tokenized', '_detokenized')

        # Audit log
        user_email = _get_user_email()
        audit_service.log_event(
            user=user_email,
            action='detokenize',
            resource=file_path,
            status='success',
            details=f'Streamed detokenized file to user (never stored)',
        )

        from flask import Response
        return Response(
            detokenized_content,
            mimetype='text/plain',
            headers={
                'Content-Disposition': f'attachment; filename="{base_name}"',
                'X-Detokenized': 'true',
                'X-Never-Stored': 'true',
            },
        )

    except Exception as e:
        logger.error(f"Detokenize failed: {e}")
        return jsonify({'error': str(e)}), 500
