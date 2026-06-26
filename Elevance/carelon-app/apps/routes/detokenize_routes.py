"""Detokenize routes — reverse tokenization, stream-only output."""

import logging
from flask import Blueprint, render_template, request, jsonify, session, send_file
from middleware.auth_middleware import require_permission
from services.audit_service import audit_service

logger = logging.getLogger(__name__)
detokenize_bp = Blueprint('detokenize', __name__, url_prefix='/detokenize')


@detokenize_bp.route('/', methods=['GET'])
@require_permission('detokenize')
def detokenize_form():
    """Render the detokenize page."""
    return render_template('detokenize.html', permissions=session.get('permissions', []))


@detokenize_bp.route('/<path:file_path>', methods=['POST'])
@require_permission('detokenize')
def detokenize(file_path: str):
    """Detokenize a file and stream for download (never stored).

    Requires Protegrity template to be uploaded.
    """
    from services.detokenizer import DetokenizationOrchestrator

    if 'protegrity_template' not in request.files:
        return jsonify({'error': 'Protegrity template file required for detokenization.'}), 400

    prot_template_file = request.files['protegrity_template']

    try:
        orchestrator = DetokenizationOrchestrator()
        output_stream, filename = orchestrator.detokenize(file_path, prot_template_file)

        audit_service.log_event(
            user=session.get('username', 'unknown'),
            action='detokenize',
            resource=file_path,
            status='success',
        )

        return send_file(
            output_stream,
            as_attachment=True,
            download_name=f"detokenized_{filename}",
        )
    except Exception as e:
        logger.error(f"Detokenization failed: {e}")
        audit_service.log_event(
            user=session.get('username', 'unknown'),
            action='detokenize',
            resource=file_path,
            status='failed',
            details=str(e),
        )
        return jsonify({'error': str(e)}), 500
