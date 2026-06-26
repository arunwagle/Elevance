"""Volume browser API routes — powers the Volume folder picker modal.

Provides JSON API endpoints for browsing catalogs, schemas, volumes,
and directories within volumes. Used by the upload form's folder picker.

Also provides /permitted-folders endpoint that returns only the folders
the current user has 'upload' permission on (from permission_assignments).
"""

import os
import logging
import requests as http_requests
from flask import Blueprint, jsonify, request, session
from middleware.auth_middleware import login_required
from services.volume_browser_service import VolumeBrowserService

logger = logging.getLogger(__name__)
volume_api_bp = Blueprint('volume_api', __name__, url_prefix='/api/volumes')
volume_browser = VolumeBrowserService()


def _get_user_token():
    """Get the user's forwarded access token from platform headers."""
    token = request.headers.get('X-Forwarded-Access-Token', '')
    if not token:
        logger.warning("No X-Forwarded-Access-Token header found in request")
    return token


@volume_api_bp.route('/catalogs', methods=['GET'])
@login_required
def list_catalogs():
    """List all accessible catalogs."""
    token = _get_user_token()
    catalogs = volume_browser.list_catalogs(user_token=token)
    return jsonify({'catalogs': catalogs})


@volume_api_bp.route('/schemas', methods=['GET'])
@login_required
def list_schemas():
    """List schemas in a catalog. Query param: ?catalog=<name>"""
    catalog = request.args.get('catalog', '')
    if not catalog:
        return jsonify({'error': 'Missing required parameter: catalog'}), 400

    token = _get_user_token()
    schemas = volume_browser.list_schemas(catalog_name=catalog, user_token=token)
    return jsonify({'schemas': schemas, 'catalog': catalog})


@volume_api_bp.route('/list', methods=['GET'])
@login_required
def list_volumes():
    """List volumes in a schema. Query params: ?catalog=<name>&schema=<name>"""
    catalog = request.args.get('catalog', '')
    schema = request.args.get('schema', '')
    if not catalog or not schema:
        return jsonify({'error': 'Missing required parameters: catalog, schema'}), 400

    token = _get_user_token()
    volumes = volume_browser.list_volumes(catalog_name=catalog, schema_name=schema,
                                          user_token=token)
    return jsonify({'volumes': volumes, 'catalog': catalog, 'schema': schema})


@volume_api_bp.route('/browse', methods=['GET'])
@login_required
def browse_directory():
    """Browse directory contents within a volume.

    Query params:
        volume_path: /Volumes/catalog/schema/volume (required)
        subfolder: optional path within the volume
    """
    volume_path = request.args.get('volume_path', '')
    subfolder = request.args.get('subfolder', '')

    if not volume_path:
        return jsonify({'error': 'Missing required parameter: volume_path'}), 400

    token = _get_user_token()

    try:
        result = volume_browser.list_directory(
            volume_path=volume_path, subfolder=subfolder, user_token=token
        )
        return jsonify({
            'items': result['items'],
            'volume_path': volume_path,
            'subfolder': subfolder,
            'current_path': f"{volume_path}/{subfolder}".rstrip('/'),
        })
    except Exception as e:
        error_msg = str(e)
        logger.error(f"Browse directory failed (token={'present' if token else 'absent'}): {error_msg}")

        # Provide helpful error hint
        hint = ''
        if '401' in error_msg or '403' in error_msg or 'permission' in error_msg.lower():
            hint = ' (Hint: The app may need the "files.files" OAuth scope for user authorization)'

        return jsonify({
            'error': error_msg + hint,
            'items': [],
            'volume_path': volume_path,
            'subfolder': subfolder,
        }), 500


@volume_api_bp.route('/create-folder', methods=['POST'])
@login_required
def create_folder():
    """Create a new folder in a volume.

    JSON body:
        volume_path: /Volumes/catalog/schema/volume (required)
        folder_name: name of the new folder (required)
        subfolder: optional parent subfolder path
    """
    data = request.get_json()
    if not data:
        return jsonify({'error': 'Request body must be JSON'}), 400

    volume_path = data.get('volume_path', '')
    folder_name = data.get('folder_name', '')
    subfolder = data.get('subfolder', '')

    if not volume_path or not folder_name:
        return jsonify({'error': 'Missing required fields: volume_path, folder_name'}), 400

    # Basic validation on folder name
    if '/' in folder_name or '..' in folder_name:
        return jsonify({'error': 'Invalid folder name. Cannot contain / or ..'}), 400

    token = _get_user_token()
    result = volume_browser.create_folder(
        volume_path=volume_path,
        folder_name=folder_name,
        subfolder=subfolder,
        user_token=token,
    )

    if result['success']:
        return jsonify(result), 201
    return jsonify(result), 500


# --- Config for permission lookups ---
_CATALOG = 'aw_serverless_stable_catalog'
_SCHEMA = 'carelon'
_PERM_ASSIGNMENTS_TABLE = f'{_CATALOG}.{_SCHEMA}.permission_assignments'


def _get_sp_token():
    """Get a service principal token for SQL query execution."""
    host = os.environ.get('DATABRICKS_HOST', '').rstrip('/')
    if host and not host.startswith('http'):
        host = f'https://{host}'
    sp_client_id = os.environ.get('DATABRICKS_CLIENT_ID', '')
    sp_client_secret = os.environ.get('DATABRICKS_CLIENT_SECRET', '')
    if not sp_client_id or not sp_client_secret:
        logger.error("SP credentials not configured")
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
    """Execute SQL via the Statement API."""
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


@volume_api_bp.route('/permitted-folders', methods=['GET'])
@login_required
def get_permitted_folders():
    """Return folders the current user has upload permission on.

    Admins see all folders. Non-admins see only explicitly assigned folders.
    Returns: { folders: [{ path, display_name, entity_name, entity_type }] }
    """
    from flask import current_app

    user_email = request.headers.get('X-Forwarded-Email', '')
    if not user_email:
        user_email = session.get('email', session.get('username', ''))
    if not user_email:
        return jsonify({'folders': [], 'error': 'Could not determine user identity.'}), 401

    # Admin check
    is_admin = (session.get('is_admin') or
                'admin' in session.get('groups', []) or
                user_email.lower() in [e.lower() for e in current_app.config.get('ADMIN_USERS', [])])

    volume_root = f'/Volumes/{_CATALOG}/{_SCHEMA}/dxutility'

    if is_admin:
        token = _get_user_token()
        if not token:
            return jsonify({'folders': [], 'error': 'User token unavailable.'}), 401
        try:
            result = volume_browser.list_directory(volume_path=volume_root, subfolder='', user_token=token)
            folders = []
            for item in result.get('items', []):
                if item.get('is_directory'):
                    folders.append({
                        'path': item['path'],
                        'display_name': item['name'],
                        'entity_name': user_email,
                        'entity_type': 'admin',
                    })
            logger.info(f"Permitted folders (admin) for {user_email}: {len(folders)}")
            return jsonify({'folders': folders, 'is_admin': True}), 200
        except Exception as e:
            logger.error(f"Admin folder listing error: {e}")
            return jsonify({'folders': [], 'error': str(e)}), 500

    # Non-admin: query permission_assignments for upload action
    headers, host = _get_sp_token()
    if not headers:
        return jsonify({'folders': [], 'error': 'SP token unavailable.'}), 500

    safe_email = user_email.replace("'", "''")
    sql = f"""
        SELECT DISTINCT resource_path, entity_name, entity_type
        FROM {_PERM_ASSIGNMENTS_TABLE}
        WHERE permission_type = 'files'
          AND action = 'upload'
          AND is_active = TRUE
          AND resource_path IS NOT NULL
          AND resource_path != ''
          AND (
              entity_name = '{safe_email}'
              OR entity_type = 'group'
          )
        ORDER BY resource_path
    """

    result = _execute_sql(headers, host, sql)
    if result is None:
        return jsonify({'folders': [], 'error': 'Failed to query permissions.'}), 500

    columns = [col['name'] for col in result.get('manifest', {}).get('schema', {}).get('columns', [])]
    rows = result.get('result', {}).get('data_array', [])

    folders = []
    for row in rows:
        row_dict = dict(zip(columns, row))
        path = row_dict.get('resource_path', '')
        if path:
            display = path.replace(volume_root + '/', '').replace(volume_root, 'Root')
            folders.append({
                'path': path,
                'display_name': display or 'Root',
                'entity_name': row_dict.get('entity_name', ''),
                'entity_type': row_dict.get('entity_type', ''),
            })

    logger.info(f"Permitted folders for {user_email}: {len(folders)} found")
    return jsonify({'folders': folders}), 200
