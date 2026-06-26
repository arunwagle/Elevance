"""Authentication service — uses Databricks Apps platform identity.

Databricks Apps automatically authenticates users and passes identity
via X-Forwarded-* headers. No login form is needed.

Headers available:
  - X-Forwarded-Email: user email from IdP
  - X-Forwarded-Preferred-Username: username from IdP
  - X-Forwarded-User: user identifier from IdP
  - X-Forwarded-Access-Token: user's OAuth access token
"""

import time
import logging
from typing import Optional
from flask import session, request, current_app
from models.user import User
from services.permissions_service import PermissionsService

logger = logging.getLogger(__name__)


class AuthService:
    """Handles authentication using Databricks platform identity headers."""

    def __init__(self):
        self.permissions_service = PermissionsService()

    def get_user_from_headers(self) -> Optional[User]:
        """Extract user identity from Databricks-forwarded headers."""
        email = request.headers.get('X-Forwarded-Email', '')
        username = request.headers.get('X-Forwarded-Preferred-Username', '')
        user_id = request.headers.get('X-Forwarded-User', '')

        if not email and not username:
            logger.warning("No identity headers found in request")
            return None

        # Use email prefix as username if username header is missing
        if not username and email:
            username = email.split('@')[0]

        if not user_id:
            user_id = username

        # Resolve groups based on admin list or default
        groups = self._resolve_groups(email)

        user = User(
            user_id=user_id,
            username=username,
            display_name=username,
            email=email,
            groups=groups,
            is_active=True,
        )
        logger.info(f"Resolved user from headers: {user.email} (groups: {groups})")
        return user

    def _resolve_groups(self, email: str) -> list:
        """Resolve user groups.
        Phase 1: Admin list from config + default group for others.
        Phase 2: Query Delta table / SCIM groups for group mappings.
        """
        admin_users = current_app.config.get('ADMIN_USERS', [])
        if email.lower() in [e.lower() for e in admin_users]:
            return ['admin']
        return ['analyst']

    def create_session(self, user: User) -> None:
        """Store user data and resolved permissions in Flask session."""
        permissions = self.permissions_service.get_user_permissions(user.groups)

        session['user_id'] = user.user_id
        session['username'] = user.username
        session['display_name'] = user.display_name
        session['email'] = user.email
        session['groups'] = user.groups
        session['permissions'] = list(permissions)
        session['is_admin'] = 'admin' in user.groups
        session['last_activity'] = time.time()
        session['timeout_seconds'] = current_app.config.get('SESSION_TIMEOUT_SECONDS', 60)

    def get_current_user(self) -> Optional[User]:
        """Retrieve the current user from session."""
        if not session.get('user_id'):
            return None
        return User(
            user_id=session['user_id'],
            username=session['username'],
            display_name=session.get('display_name', ''),
            email=session.get('email', ''),
            groups=session.get('groups', []),
        )

    def ensure_session(self) -> Optional[User]:
        """Get current user from session, or create session from headers.
        Call this on every request to auto-login the Databricks user."""
        user = self.get_current_user()
        if user:
            return user

        # No session yet — resolve from platform headers
        user = self.get_user_from_headers()
        if user:
            self.create_session(user)
        return user

    def get_access_token(self) -> Optional[str]:
        """Get the user's forwarded access token for downstream API calls."""
        return request.headers.get('X-Forwarded-Access-Token')

    def destroy_session(self) -> None:
        """Clear the session (logout)."""
        username = session.get('username', 'unknown')
        session.clear()
        logger.info(f"Session destroyed for user: {username}")

    def refresh_activity(self) -> bool:
        """Update last_activity timestamp. Returns False if session expired."""
        if not session.get('user_id'):
            return False
        session['last_activity'] = time.time()
        return True
