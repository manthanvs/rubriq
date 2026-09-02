"""Subjects, enrollment, project cycles and review milestones.

Every public function here takes ``actor`` as its first argument and scopes
its query through :func:`core.academics.access.visible_subject_ids`. There is
no unscoped read in this package, and ``tests/core/test_actor_contract.py``
fails the build if one appears.

Deliberately no re-exports, for the same reason as ``core.auth`` — import
from the module that defines the thing.
"""
