"""Sign-in: domain assertion first, role from the allow-list, audit on change."""

from __future__ import annotations

import pytest
from sqlalchemy import select

from core.auth.roles import Role
from core.auth.service import authenticate, sign_in
from core.config import Settings
from core.db.engine import session_scope
from core.db.models import AuditLog, User
from core.errors import AuthError

FACULTY_EMAIL = "guide@pccoepune.org"
STUDENT_EMAIL = "manthan.sankpal@pccoepune.org"


@pytest.fixture
def settings() -> Settings:
    return Settings(
        database_url="sqlite://",
        faculty_allowlist=(FACULTY_EMAIL,),
    )


class TestAuthenticate:
    def test_resolves_a_student(self, settings: Settings) -> None:
        actor = authenticate({"email": STUDENT_EMAIL, "name": "Manthan"}, settings)

        assert actor.role is Role.STUDENT
        assert actor.is_student and not actor.is_faculty

    def test_resolves_faculty_from_the_allow_list(self, settings: Settings) -> None:
        actor = authenticate({"email": FACULTY_EMAIL, "name": "Anjana"}, settings)

        assert actor.role is Role.FACULTY
        assert actor.is_faculty

    def test_a_gmail_claim_is_refused(self, settings: Settings) -> None:
        with pytest.raises(AuthError):
            authenticate({"email": "manthan@gmail.com"}, settings)

    def test_role_follows_the_allow_list_not_the_stored_row(
        self, settings: Settings
    ) -> None:
        """Invariant #5: demotion takes effect immediately, from settings."""
        demoted = Settings(database_url="sqlite://", faculty_allowlist=())

        assert authenticate({"email": FACULTY_EMAIL}, settings).role is Role.FACULTY
        assert authenticate({"email": FACULTY_EMAIL}, demoted).role is Role.STUDENT


class TestSignIn:
    def test_creates_the_user_and_an_audit_row(self, db_factory, settings) -> None:
        with session_scope(db_factory) as session:
            actor = sign_in(
                session, claims={"email": STUDENT_EMAIL, "name": "M"}, settings=settings
            )

        assert actor.email == STUDENT_EMAIL

        with session_scope(db_factory) as session:
            user = session.get(User, STUDENT_EMAIL)
            actions = session.scalars(select(AuditLog.action)).all()

        assert user is not None
        assert user.role is Role.STUDENT
        assert actions == ["user.created"]

    def test_signing_in_twice_does_not_duplicate_the_user(
        self, db_factory, settings
    ) -> None:
        claims = {"email": STUDENT_EMAIL, "name": "M"}

        for _ in range(3):
            with session_scope(db_factory) as session:
                sign_in(session, claims=claims, settings=settings)

        with session_scope(db_factory) as session:
            users = session.scalars(select(User)).all()
            actions = session.scalars(select(AuditLog.action)).all()

        assert len(users) == 1
        assert actions == ["user.created"], (
            "an unchanged sign-in must not write audit noise"
        )

    def test_promotion_updates_the_row_and_is_audited(self, db_factory, settings) -> None:
        student_settings = Settings(database_url="sqlite://", faculty_allowlist=())
        claims = {"email": FACULTY_EMAIL, "name": "Anjana"}

        with session_scope(db_factory) as session:
            sign_in(session, claims=claims, settings=student_settings)

        with session_scope(db_factory) as session:
            sign_in(session, claims=claims, settings=settings)

        with session_scope(db_factory) as session:
            user = session.get(User, FACULTY_EMAIL)
            entry = session.scalars(
                select(AuditLog).where(AuditLog.action == "user.role_changed")
            ).one()

        assert user.role is Role.FACULTY
        assert entry.payload == {"from": "STUDENT", "to": "FACULTY"}

    def test_a_rejected_domain_never_reaches_the_database(
        self, db_factory, settings
    ) -> None:
        """Invariant #4: not even as a row a later query could return."""
        with pytest.raises(AuthError):
            with session_scope(db_factory) as session:
                sign_in(session, claims={"email": "x@gmail.com"}, settings=settings)

        with session_scope(db_factory) as session:
            assert session.scalars(select(User)).all() == []
            assert session.scalars(select(AuditLog)).all() == []

    def test_the_display_name_is_refreshed(self, db_factory, settings) -> None:
        with session_scope(db_factory) as session:
            sign_in(
                session, claims={"email": STUDENT_EMAIL, "name": "Old"}, settings=settings
            )

        with session_scope(db_factory) as session:
            sign_in(
                session, claims={"email": STUDENT_EMAIL, "name": "New"}, settings=settings
            )

        with session_scope(db_factory) as session:
            assert session.get(User, STUDENT_EMAIL).name == "New"
