"""Authentication routes — auto-login via Databricks identity, logout, heartbeat.

No login form is needed. Databricks Apps authenticates users at the platform
level and passes identity via X-Forwarded-* headers.
"""

from flask import Blueprint, redirect, url_for, session, jsonify
from services.auth_service import AuthService
from services.audit_service import audit_service

auth_bp = Blueprint('auth', __name__)
auth_service = AuthService()


@auth_bp.route('/login', methods=['GET'])
def login():
    """Auto-login using Databricks platform identity headers.
    No form is shown — the platform has already authenticated the user."""
    if session.get('user_id'):
        return redirect(url_for('dashboard'))

    # Extract identity from platform headers and create session
    user = auth_service.get_user_from_headers()
    if not user:
        return "Unauthorized: No Databricks identity found in request headers.", 401

    auth_service.create_session(user)
    audit_service.log_event(user=user.username, action='login', resource='auth', status='success')
    return redirect(url_for('dashboard'))


@auth_bp.route('/logout', methods=['POST', 'GET'])
def logout():
    """Destroy session and redirect to login (re-creates session from headers)."""
    username = session.get('username', 'unknown')
    audit_service.log_event(user=username, action='logout', resource='auth', status='success')
    auth_service.destroy_session()
    return redirect(url_for('auth.login'))


@auth_bp.route('/auth/heartbeat', methods=['POST'])
def heartbeat():
    """Keep session alive (called by client-side inactivity timer)."""
    if auth_service.refresh_activity():
        return jsonify({'status': 'alive'}), 200
    return jsonify({'status': 'expired'}), 401
