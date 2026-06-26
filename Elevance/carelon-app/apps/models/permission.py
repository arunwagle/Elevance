"""Permission and GroupPermission domain models."""

from dataclasses import dataclass
from typing import List


# All supported application permissions
ALL_PERMISSIONS = [
    'browse',
    'upload',
    'download',
    'delete',
    'preview',
    'detokenize',
    'share',
    'manage_permissions',
]


@dataclass
class Permission:
    """Represents a single application permission/operation."""

    permission_id: str
    display_name: str
    description: str = ''


@dataclass
class GroupPermission:
    """Maps a user group to its granted permissions."""

    group_id: str
    permissions: List[str]

    def has_permission(self, permission_id: str) -> bool:
        """Check if this group grants a specific permission."""
        return permission_id in self.permissions


# Default group definitions
DEFAULT_GROUPS = {
    'admin': GroupPermission(
        group_id='admin',
        permissions=ALL_PERMISSIONS.copy(),
    ),
    'data_steward': GroupPermission(
        group_id='data_steward',
        permissions=['browse', 'upload', 'download', 'delete', 'preview', 'detokenize'],
    ),
    'analyst': GroupPermission(
        group_id='analyst',
        permissions=['browse', 'upload', 'download', 'preview'],
    ),
    'viewer': GroupPermission(
        group_id='viewer',
        permissions=['browse', 'preview'],
    ),
}
