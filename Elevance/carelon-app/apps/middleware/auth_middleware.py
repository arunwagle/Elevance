"""Authentication and authorization middleware.

Provides decorators for route-level permission enforcement.
"""

import time
import functools
import logging
from flask import session, redirect, url_for, jsonify, request, render_template_string, current_app

logger = logging.getLogger(__name__)

# 403 page shown to non-admin users trying to access admin routes
_ACCESS_DENIED_HTML = """
<!DOCTYPE html>
<html><head><title>Access Denied</title>
<style>
  body { font-family: -apple-system, BlinkMacSystemFont, sans-serif; display: flex;
         align-items: center; justify-content: center; height: 100vh; margin: 0;
         background: #f8f9fa; color: #333; }
  .box { text-align: center; padding: 3rem; background: #fff; border-radius: 12px;
         box-shadow: 0 4px 24px rgba(0,0,0,0.08); max-width: 420px; }
  h1 { color: #6B2D8B; font-size: 1.6rem; margin-bottom: 0.5rem; }
  p { color: #666; line-height: 1.5; }
  a { color: #6B2D8B; text-decoration: none; font-weight: 500; }
</style>
</head><body><div class="box">
  <h1>🚫 Access Denied</h1>
  <p>You do not have admin privileges to access this page.</p>
  <p>Contact your administrator if you believe this is an error.</p>
  <p><a href="/dashboard">← Return to Dashboard</a></p>
</div></body></html>
"""


def login_required(f):
    """Decorator: require an authenticated session.

    Redirects to login page if no active session.
    Timeout check is disabled for now — will be re-enabled later.
    """
    @functools.wraps(f)
    def decorated_function(*args, **kwargs):
        # Check session exists
        if not session.get('user_id'):
            logger.warning(f"Unauthenticated access attempt to {request.path}")
            if request.is_json:
                return jsonify({'error': 'Authentication required'}), 401
            return redirect(url_for('auth.login'))

        # Update last activity timestamp (for future timeout use)
        session['last_activity'] = time.time()

        return f(*args, **kwargs)
    return decorated_function


def require_permission(permission_id):
    """Decorator: require a specific permission for the current user.

    Usage:
        @upload_bp.route('/file', methods=['POST'])
        @require_permission('upload')
        def upload_file():
            ...

    Checks:
    1. User is authenticated (login_required)
    2. User's resolved permissions include the required permission_id
    """
    def decorator(f):
        @functools.wraps(f)
        @login_required
        def decorated_function(*args, **kwargs):
            user_permissions = set(session.get('permissions', []))

            if permission_id not in user_permissions:
                logger.warning(
                    f"Permission denied: user={session.get('username')}, "
                    f"required={permission_id}, has={user_permissions}"
                )
                if request.is_json:
                    return jsonify({
                        'error': f'Access denied. Required permission: {permission_id}'
                    }), 403
                return jsonify({
                    'error': f'Access denied. You do not have "{permission_id}" permission.'
                }), 403

            return f(*args, **kwargs)
        return decorated_function
    return decorator


def require_admin(f):
    """Decorator: require admin group membership.

    Checks:
    1. User is authenticated (login_required)
    2. User's groups include 'admin' OR their email is in ADMIN_USERS config

    Returns a styled 403 page for browser requests, JSON for API calls.
    """
    @functools.wraps(f)
    @login_required
    def decorated_function(*args, **kwargs):
        user_groups = session.get('groups', [])
        user_email = session.get('email', '')

        # Check group membership
        is_admin = 'admin' in user_groups

        # Fallback: check ADMIN_USERS config directly
        if not is_admin:
            admin_users = current_app.config.get('ADMIN_USERS', [])
            is_admin = user_email.lower() in [e.lower() for e in admin_users]

        if not is_admin:
            logger.warning(
                f"Admin access denied: user={session.get('username')}, "
                f"email={user_email}, groups={user_groups}, path={request.path}"
            )
            if request.is_json:
                return jsonify({
                    'error': 'Access denied. Admin privileges required.'
                }), 403
            return _ACCESS_DENIED_HTML, 403

        return f(*args, **kwargs)
    return decorated_function
