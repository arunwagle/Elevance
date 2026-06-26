"""Share routes — Delta Sharing integration (placeholder for Phase 3)."""

import logging
from flask import Blueprint, render_template, request, jsonify, session
from middleware.auth_middleware import require_permission

logger = logging.getLogger(__name__)
share_bp = Blueprint('share', __name__, url_prefix='/share')


@share_bp.route('/<path:file_path>', methods=['GET'])
@require_permission('share')
def share_form(file_path: str):
    """Render the share configuration page."""
    return render_template(
        'share.html',
        file_path=file_path,
        permissions=session.get('permissions', []),
    )


@share_bp.route('/<path:file_path>', methods=['POST'])
@require_permission('share')
def share_file(file_path: str):
    """Share a file via Delta Sharing (placeholder)."""
    # Phase 3 implementation
    return jsonify({
        'status': 'not_implemented',
        'message': 'Delta Sharing integration coming in Phase 3.',
    }), 501
