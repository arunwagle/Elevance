"""Permissions service — resolves and manages user permissions.

Phase 1: Uses in-memory DEFAULT_GROUPS from models.permission.
Phase 2: Reads from Delta tables in Unity Catalog.
"""

import logging
from typing import List, Set, Dict
from models.permission import DEFAULT_GROUPS, ALL_PERMISSIONS, GroupPermission

logger = logging.getLogger(__name__)


class PermissionsService:
    """Manages permission resolution and group operations."""

    def __init__(self):
        # Phase 1: in-memory store. Phase 2: read from Delta tables.
        self._groups: Dict[str, GroupPermission] = DEFAULT_GROUPS.copy()

    def get_user_permissions(self, user_groups: List[str]) -> Set[str]:
        """Resolve the union of all permissions from the user's groups."""
        permissions = set()
        for group_id in user_groups:
            group = self._groups.get(group_id)
            if group:
                permissions.update(group.permissions)
        return permissions

    def has_permission(self, user_groups: List[str], permission_id: str) -> bool:
        """Check if any of the user's groups grant a specific permission."""
        return permission_id in self.get_user_permissions(user_groups)

    def get_all_groups(self) -> Dict[str, GroupPermission]:
        """Return all defined groups with their permissions."""
        return self._groups

    def get_all_permissions(self) -> List[str]:
        """Return list of all available permission IDs."""
        return ALL_PERMISSIONS.copy()

    def get_group(self, group_id: str) -> GroupPermission:
        """Get a specific group's permission definition."""
        return self._groups.get(group_id)

    def update_group_permissions(self, group_id: str, permissions: List[str]) -> bool:
        """Update permissions for a group. Returns True on success."""
        if group_id not in self._groups:
            logger.error(f"Cannot update unknown group: {group_id}")
            return False

        # Validate all permission IDs
        invalid = [p for p in permissions if p not in ALL_PERMISSIONS]
        if invalid:
            logger.error(f"Invalid permissions: {invalid}")
            return False

        self._groups[group_id] = GroupPermission(
            group_id=group_id,
            permissions=permissions,
        )
        logger.info(f"Updated permissions for group '{group_id}': {permissions}")
        return True

    def get_permissions_matrix(self) -> Dict[str, Dict[str, bool]]:
        """Return the full permissions matrix for the admin UI.

        Returns: {group_id: {permission_id: bool}}
        """
        matrix = {}
        for group_id, group in self._groups.items():
            matrix[group_id] = {
                perm: perm in group.permissions
                for perm in ALL_PERMISSIONS
            }
        return matrix
