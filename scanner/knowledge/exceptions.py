# -*- coding: utf-8 -*-
"""Knowledge layer exceptions."""


class KnowledgeError(Exception):
    """Base error for the knowledge module."""


class SnapshotNotFoundError(KnowledgeError):
    """Raised when a requested snapshot does not exist."""


class SnapshotValidationError(KnowledgeError):
    """Raised when snapshot payload fails validation."""


class RepositoryError(KnowledgeError):
    """Raised when persistence operations fail."""
