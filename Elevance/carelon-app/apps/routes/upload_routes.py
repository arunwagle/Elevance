"""Upload routes — file tokenization and upload to Volume.

Provides:
- GET /upload/ — renders the 5-step upload wizard
- POST /upload/tokenize — accepts parsed data from the wizard,
  applies mock Protegrity tokenization on PHI columns (identified by
  phi_type from the processing template), and uploads the tokenized
  output to the selected Volume folder.
"""

import os
import io
import csv
import hashlib
import logging
from datetime import datetime, timezone
from flask import Blueprint, render_template, request, jsonify, session, current_app
from middleware.auth_middleware import require_permission
from services.audit_service import audit_service
import requests as http_requests

logger = logging.getLogger(__name__)
upload_bp = Blueprint('upload', __name__, url_prefix='/upload')

_VOLUME_ROOT = '/Volumes/aw_serverless_stable_catalog/carelon/dxutility'


def _get_user_token():
    """Get the user's forwarded access token for Volume operations."""
    return request.headers.get('X-Forwarded-Access-Token', '')


def _get_host():
    """Get Databricks workspace host."""
    host = os.environ.get('DATABRICKS_HOST', '').rstrip('/')
    if host and not host.startswith('http'):
        host = f'https://{host}'
    return host


# ======== Mock Protegrity Tokenization ========
# ONLY columns with an explicit phi_type from the template are masked.
# The phi_type value determines the masking function applied.

def _mask_value(value, phi_type):
    """Apply masking to a PHI value based on its declared phi_type from the template.

    Only columns explicitly marked with a non-empty phi_type in the
    processing template reach this function. All other columns are
    left unchanged.
    """
    if not value or not value.strip():
        return value

    t = phi_type.lower().strip()

    # SSN
    if t in ('ssn', 'social_security', 'social security', 'social security number'):
        digits = ''.join(c for c in value if c.isdigit())
        if len(digits) >= 9:
            return f"***-**-{digits[-4:]}"
        return '***-**-' + value[-4:] if len(value) >= 4 else '****'

    # Phone
    if t in ('phone', 'telephone', 'mobile', 'phone_number', 'phone number', 'cell'):
        digits = ''.join(c for c in value if c.isdigit())
        if len(digits) >= 7:
            return f"(***) ***-{digits[-4:]}"
        return '***-' + value[-4:] if len(value) >= 4 else '****'

    # Email
    if t in ('email', 'email_address', 'email address', 'e-mail'):
        if '@' in value:
            local, domain = value.rsplit('@', 1)
            masked_local = local[0] + '*' * (len(local) - 1) if local else '***'
            return f"{masked_local}@{domain}"
        return '***@***.***'

    # Date of Birth
    if t in ('dob', 'date_of_birth', 'date of birth', 'birth_date', 'birthdate'):
        for fmt in ('%Y-%m-%d', '%m/%d/%Y', '%m-%d-%Y', '%Y%m%d'):
            try:
                dt = datetime.strptime(value.strip(), fmt)
                return f"****-**-** ({dt.year})"
            except ValueError:
                continue
        return '****-**-**'

    # Name
    if t in ('name', 'first_name', 'last_name', 'full_name', 'first name', 'last name',
             'patient_name', 'member_name', 'subscriber_name'):
        return value[0].upper() + '*' * (len(value) - 1) if value else '****'

    # Address
    if t in ('address', 'street', 'street_address', 'address_line', 'addr',
             'address1', 'address2', 'mailing_address'):
        parts = value.split()
        if len(parts) > 1:
            return parts[0] + ' ' + ' '.join('*' * len(p) for p in parts[1:])
        return '*' * len(value)

    # ZIP / Postal Code
    if t in ('zip', 'zip_code', 'zipcode', 'postal', 'postal_code'):
        digits = ''.join(c for c in value if c.isdigit())
        if len(digits) >= 5:
            return digits[:3] + '**'
        return value[:3] + '**' if len(value) >= 3 else '***'

    # Member ID / Patient ID / Account Number
    if t in ('member_id', 'patient_id', 'subscriber_id', 'id', 'mrn',
             'medical_record_number', 'account_number', 'policy_number'):
        token = hashlib.sha256(value.encode()).hexdigest()[:12].upper()
        return f"TOK_{token}"

    # Generic PHI fallback (any other declared phi_type): mask middle
    if len(value) > 4:
        return value[0] + '*' * (len(value) - 2) + value[-1]
    elif len(value) > 1:
        return value[0] + '*' * (len(value) - 1)
    return '*'


def _mock_protegrity_api_call(headers, rows, phi_columns, phi_indices, phi_types):
    """Simulate Protegrity REST API batch tokenization.

    ONLY columns with a declared phi_type are processed.
    The phi_type determines the masking function (SSN, DOB, Name, etc.).

    In production this would be:
        POST https://protegrity-dsg.example.com/api/v1/tokenize
        Body: { "data_elements": [...], "policy": "..." }

    Args:
        headers: list of column names
        rows: list of row arrays
        phi_columns: list of PHI column names
        phi_indices: list of column indices that are PHI
        phi_types: list of phi_type strings (parallel to phi_columns)

    Returns: (tokenized_rows, api_response_metadata)
    """
    logger.info(f"[MOCK] Protegrity API called: {len(rows)} rows, "
                f"PHI columns: {list(zip(phi_columns, phi_types))}")

    tokenized_rows = []
    for row in rows:
        new_row = list(row)
        for col_idx, phi_type in zip(phi_indices, phi_types):
            if col_idx < len(new_row):
                new_row[col_idx] = _mask_value(new_row[col_idx], phi_type)
        tokenized_rows.append(new_row)

    api_metadata = {
        'api_endpoint': 'https://protegrity-dsg.mock.internal/api/v1/tokenize',
        'policy_applied': 'CARELON_PHI_MASKING_v1',
        'tokens_generated': len(rows) * len(phi_columns),
        'phi_types_applied': dict(zip(phi_columns, phi_types)),
        'processing_time_ms': len(rows) * 2,
        'status': 'SUCCESS',
    }

    return tokenized_rows, api_metadata


# ======== Page Route ========

@upload_bp.route('/', methods=['GET'])
@require_permission('upload')
def upload_form():
    """Render the 5-step upload wizard page."""
    return render_template(
        'upload.html',
        permissions=session.get('permissions', []),
        default_volume_path=current_app.config.get('VOLUME_PATH', _VOLUME_ROOT),
    )


# ======== Processing Templates Listing ========

_PROC_TEMPLATES_PATH = '/Volumes/aw_serverless_stable_catalog/carelon/dxutility/templates/input_file_parsing'


@upload_bp.route('/processing-templates', methods=['GET'])
@require_permission('upload')
def list_processing_templates():
    """List available processing templates from the Volume folder."""
    token = _get_user_token()
    if not token:
        return jsonify({'error': 'User token not available.'}), 401

    host = _get_host()
    api_path = _PROC_TEMPLATES_PATH.lstrip('/')
    url = f"{host}/api/2.0/fs/directories/{api_path}"

    try:
        resp = http_requests.get(
            url,
            headers={'Authorization': f'Bearer {token}'},
            timeout=30,
        )

        if resp.status_code == 404:
            return jsonify({'templates': [], 'path': _PROC_TEMPLATES_PATH}), 200

        if resp.status_code != 200:
            return jsonify({'error': f'Failed to list templates (HTTP {resp.status_code})'}), resp.status_code

        data = resp.json()
        items = data.get('contents', [])

        templates = []
        for item in items:
            if item.get('is_directory'):
                continue
            name = item.get('name', '')
            templates.append({
                'name': name,
                'path': item.get('path', f"{_PROC_TEMPLATES_PATH}/{name}"),
                'size': item.get('file_size', 0),
                'last_modified': item.get('last_modified', ''),
            })

        return jsonify({'templates': templates, 'path': _PROC_TEMPLATES_PATH}), 200

    except Exception as e:
        logger.error(f"List processing templates failed: {e}")
        return jsonify({'error': str(e)}), 500


@upload_bp.route('/processing-templates/download', methods=['GET'])
@require_permission('upload')
def download_processing_template():
    """Download a processing template file for client-side parsing with SheetJS."""
    file_path = request.args.get('path', '')
    if not file_path or not file_path.startswith(_PROC_TEMPLATES_PATH):
        return jsonify({'error': 'Invalid template path.'}), 400

    token = _get_user_token()
    if not token:
        return jsonify({'error': 'User token not available.'}), 401

    host = _get_host()
    api_path = file_path.lstrip('/')
    url = f"{host}/api/2.0/fs/files/{api_path}"

    try:
        resp = http_requests.get(
            url,
            headers={'Authorization': f'Bearer {token}'},
            timeout=60,
        )

        if resp.status_code != 200:
            return jsonify({'error': f'Cannot download template (HTTP {resp.status_code})'}), resp.status_code

        # Return binary content as-is with appropriate content type
        file_name = file_path.split('/')[-1]
        ext = file_name.rsplit('.', 1)[-1].lower() if '.' in file_name else ''
        content_type = 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet' if ext == 'xlsx' else 'application/octet-stream'

        from flask import Response
        return Response(
            resp.content,
            mimetype=content_type,
            headers={'Content-Disposition': f'inline; filename="{file_name}"'},
        )

    except Exception as e:
        logger.error(f"Download processing template failed: {e}")
        return jsonify({'error': str(e)}), 500


# ======== Protegrity Templates Listing ========

_PROTEGRITY_TEMPLATES_PATH = '/Volumes/aw_serverless_stable_catalog/carelon/dxutility/templates/tokenization'


@upload_bp.route('/protegrity-templates', methods=['GET'])
@require_permission('upload')
def list_protegrity_templates():
    """List available Protegrity templates from the Volume folder."""
    token = _get_user_token()
    if not token:
        return jsonify({'error': 'User token not available.'}), 401

    host = _get_host()
    api_path = _PROTEGRITY_TEMPLATES_PATH.lstrip('/')
    url = f"{host}/api/2.0/fs/directories/{api_path}"

    try:
        resp = http_requests.get(
            url,
            headers={'Authorization': f'Bearer {token}'},
            timeout=30,
        )

        if resp.status_code == 404:
            return jsonify({'templates': [], 'path': _PROTEGRITY_TEMPLATES_PATH}), 200

        if resp.status_code != 200:
            return jsonify({'error': f'Failed to list templates (HTTP {resp.status_code})'}), resp.status_code

        data = resp.json()
        items = data.get('contents', [])

        templates = []
        for item in items:
            if item.get('is_directory'):
                continue
            name = item.get('name', '')
            templates.append({
                'name': name,
                'path': item.get('path', f"{_PROTEGRITY_TEMPLATES_PATH}/{name}"),
                'size': item.get('file_size', 0),
                'last_modified': item.get('last_modified', ''),
            })

        return jsonify({'templates': templates, 'path': _PROTEGRITY_TEMPLATES_PATH}), 200

    except Exception as e:
        logger.error(f"List protegrity templates failed: {e}")
        return jsonify({'error': str(e)}), 500


@upload_bp.route('/protegrity-templates/preview', methods=['GET'])
@require_permission('upload')
def preview_protegrity_template():
    """Fetch and return the content of a Protegrity template for preview."""
    file_path = request.args.get('path', '')
    if not file_path or not file_path.startswith(_PROTEGRITY_TEMPLATES_PATH):
        return jsonify({'error': 'Invalid template path.'}), 400

    token = _get_user_token()
    if not token:
        return jsonify({'error': 'User token not available.'}), 401

    host = _get_host()
    api_path = file_path.lstrip('/')
    url = f"{host}/api/2.0/fs/files/{api_path}"

    try:
        resp = http_requests.get(
            url,
            headers={'Authorization': f'Bearer {token}'},
            timeout=30,
        )

        if resp.status_code != 200:
            return jsonify({'error': f'Cannot read template (HTTP {resp.status_code})'}), resp.status_code

        raw = resp.content.decode('utf-8', errors='replace')

        # Try to parse as JSON for structured preview
        parsed = None
        try:
            import json
            parsed = json.loads(raw)
        except (json.JSONDecodeError, ValueError):
            pass

        return jsonify({
            'name': file_path.split('/')[-1],
            'path': file_path,
            'content': raw[:10000],  # cap at 10KB for preview
            'parsed': parsed,
            'truncated': len(raw) > 10000,
        }), 200

    except Exception as e:
        logger.error(f"Preview protegrity template failed: {e}")
        return jsonify({'error': str(e)}), 500


# ======== Tokenize + Upload Endpoint ========

@upload_bp.route('/tokenize', methods=['POST'])
@require_permission('upload')
def tokenize_and_upload():
    """Accept parsed data from the upload wizard, tokenize PHI columns, upload to Volume.

    JSON body:
        headers: ['col1', 'col2', ...]
        rows: [['val1', 'val2', ...], ...]
        phi_columns: ['SSN', 'DOB', ...]        — column names marked as PHI
        phi_indices: [0, 3, ...]                 — their indices in the row
        phi_types: ['SSN', 'Date of Birth', ...] — the phi_type from template
        volume_path: '/Volumes/.../subfolder'
        original_filename: 'data.dat'

    Only columns with a phi_type are masked. All others pass through unchanged.
    """
    data = request.get_json()
    if not data:
        return jsonify({'error': 'Request body must be JSON.'}), 400

    headers = data.get('headers', [])
    rows = data.get('rows', [])
    phi_columns = data.get('phi_columns', [])
    phi_indices = data.get('phi_indices', [])
    phi_types = data.get('phi_types', [])
    volume_path = data.get('volume_path', '')
    original_filename = data.get('original_filename', 'output.txt')

    if not headers or not rows:
        return jsonify({'error': 'No parsed data provided. Ensure Step 3 preview was generated.'}), 400
    if not volume_path:
        return jsonify({'error': 'No target folder selected.'}), 400
    if not volume_path.startswith('/Volumes/'):
        return jsonify({'error': 'Invalid volume path.'}), 403

    user_token = _get_user_token()
    if not user_token:
        return jsonify({'error': 'User access token not available.'}), 401

    # Ensure phi_types matches phi_columns length
    if len(phi_types) != len(phi_columns):
        # Fallback: if phi_types not provided, skip masking
        logger.warning("phi_types length mismatch with phi_columns — no masking applied")
        phi_types = []
        phi_columns = []
        phi_indices = []

    try:
        # Step 1: Call mock Protegrity API — ONLY masks columns with a declared phi_type
        if phi_columns and phi_indices and phi_types:
            tokenized_rows, protegrity_meta = _mock_protegrity_api_call(
                headers, rows, phi_columns, phi_indices, phi_types
            )
            logger.info(f"Protegrity tokenization complete: "
                        f"{protegrity_meta['tokens_generated']} tokens across "
                        f"{len(phi_columns)} PHI columns")
        else:
            # No PHI columns identified — pass through unchanged
            tokenized_rows = rows
            protegrity_meta = {'status': 'SKIPPED', 'reason': 'No PHI columns declared in template'}

        # Step 2: Build output file in memory (pipe-delimited text)
        output_buffer = io.StringIO()
        writer = csv.writer(output_buffer, delimiter='|')
        writer.writerow(headers)
        writer.writerows(tokenized_rows)
        file_content = output_buffer.getvalue().encode('utf-8')

        # Step 3: Generate output filename — {original}_tokenized.txt
        name_base = original_filename.rsplit('.', 1)[0] if '.' in original_filename else original_filename
        output_filename = f"{name_base}_tokenized.txt"

        # Step 4: Upload to Volume via Files API
        output_path = f"{volume_path.rstrip('/')}/{output_filename}"
        api_path = output_path.lstrip('/')
        host = _get_host()
        upload_url = f"{host}/api/2.0/fs/files/{api_path}"

        resp = http_requests.put(
            upload_url,
            headers={
                'Authorization': f'Bearer {user_token}',
                'Content-Type': 'application/octet-stream',
            },
            data=file_content,
            timeout=120,
        )

        if resp.status_code not in (200, 201, 204):
            error_msg = resp.text[:300]
            logger.error(f"Volume upload failed ({resp.status_code}): {error_msg}")
            return jsonify({
                'error': f'Failed to upload to Volume (HTTP {resp.status_code}): {error_msg}',
            }), 500

        # Step 5: Audit log
        user_email = request.headers.get('X-Forwarded-Email', session.get('username', 'unknown'))
        audit_service.log_event(
            user=user_email,
            action='upload_tokenize',
            resource=output_filename,
            status='success',
            details=(
                f"rows={len(rows)}, phi_cols={phi_columns}, phi_types={phi_types}, "
                f"output={output_path}"
            ),
        )

        logger.info(f"Upload complete: {output_path} ({len(rows)} rows, "
                    f"{len(phi_columns)} PHI cols masked)")

        return jsonify({
            'message': 'File tokenized and uploaded successfully.',
            'output_path': output_path,
            'output_filename': output_filename,
            'rows_processed': len(rows),
            'columns_tokenized': phi_columns,
            'phi_types_applied': dict(zip(phi_columns, phi_types)) if phi_types else {},
            'total_columns': len(headers),
            'file_size_bytes': len(file_content),
            'protegrity_response': protegrity_meta,
        }), 200

    except Exception as e:
        logger.error(f"Tokenize and upload failed: {e}", exc_info=True)
        audit_service.log_event(
            user=request.headers.get('X-Forwarded-Email', 'unknown'),
            action='upload_tokenize',
            resource=original_filename,
            status='failed',
            details=str(e),
        )
        return jsonify({'error': f'Processing failed: {str(e)}'}), 500
