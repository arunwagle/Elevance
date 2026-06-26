"""User and UserGroup domain models."""

from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class UserGroup:
    """Represents an application user group (maps to IDP/Databricks Account group)."""

    group_id: str
    display_name: str
    description: str = ''
    permissions: List[str] = field(default_factory=list)


@dataclass
class User:
    """Represents an authenticated application user."""

    user_id: str
    username: str
    display_name: str
    email: str = ''
    groups: List[str] = field(default_factory=list)
    is_active: bool = True

    @property
    def resolved_permissions(self) -> set:
        """Return the union of all permissions from all groups.

        Note: This is populated at login time by the PermissionsService.
        The actual resolution requires looking up group definitions.
        """
        # This property is a placeholder — actual resolution happens in PermissionsService
        return set()

    def has_group(self, group_id: str) -> bool:
        """Check if user belongs to a specific group."""
        return group_id in self.groups

    def to_session_dict(self) -> dict:
        """Serialize user for Flask session storage."""
        return {
            'user_id': self.user_id,
            'username': self.username,
            'display_name': self.display_name,
            'email': self.email,
            'groups': self.groups,
            'is_active': self.is_active,
        }

    @classmethod
    def from_session_dict(cls, data: dict) -> Optional['User']:
        """Deserialize user from Flask session."""
        if not data:
            return None
        return cls(
            user_id=data.get('user_id', ''),
            username=data.get('username', ''),
            display_name=data.get('display_name', ''),
            email=data.get('email', ''),
            groups=data.get('groups', []),
            is_active=data.get('is_active', True),
        )
