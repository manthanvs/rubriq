"""Identity, roles, and page-access policy.

The domain assertion (invariant #4) and role resolution (invariant #5) are
pure functions, testable without a browser, a Google account, or a database.

Deliberately empty of re-exports. ``core.db.models`` needs :class:`Role`, and
``core.auth.service`` needs the models — re-exporting the service from here
would make that a genuine import cycle the moment Alembic loads the metadata.
Import from the module that defines the thing:

    from core.auth.roles import Role
    from core.auth.service import sign_in
"""
