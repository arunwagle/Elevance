"""Audit service — logs all user actions for compliance and traceability.

Phase 1: In-memory list (lost on restart).
Phase 2: Write to Delta table in Unity Catalog.
"""

import logging
from datetime import datetime, timezone
from typing import List, Dict, Optional

logger = logging.getLogger(__name__)


class AuditService:
    """Records and queries audit events."""

    def __init__(self):
        # Phase 1: in-memory. Phase 2: Delta table.
        self._log: List[Dict] = []

    def log_event(
        self,
        user: str,
        action: str,
        resource: str,
        status: str = 'success',
        details: Optional[str] = None,
    ) -> None:
        """Record an audit event."""
        event = {
            'timestamp': datetime.now(timezone.utc).isoformat(),
            'user': user,
            'action': action,
            'resource': resource,
            'status': status,
            'details': details or '',
        }
        self._log.append(event)
        logger.info(f"AUDIT: {event}")

    def get_events(
        self,
        user: Optional[str] = None,
        action: Optional[str] = None,
        status: Optional[str] = None,
        limit: int = 100,
    ) -> List[Dict]:
        """Query audit events with optional filters."""
        results = self._log.copy()

        if user:
            results = [e for e in results if e['user'] == user]
        if action:
            results = [e for e in results if e['action'] == action]
        if status:
            results = [e for e in results if e['status'] == status]

        # Return most recent first
        results.reverse()
        return results[:limit]


# Singleton instance
audit_service = AuditService()
