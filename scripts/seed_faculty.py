"""Seed the faculty allow-list into the ``users`` table.

Invariant #5 says a role comes from a seeded allow-list. This is the seeding
step: it creates a row for each allow-listed address so a faculty member shows
up in the system before they have ever signed in — which is what lets a
subject be created and assigned to them on day one.

Reads ``.streamlit/secrets.toml`` directly with :mod:`tomllib` (standard
library) rather than importing Streamlit, and hands the result to the same
``Settings.from_mapping`` the app uses. One parser, one shape, no drift.

    python scripts/seed_faculty.py
    python scripts/seed_faculty.py --dry-run
"""

from __future__ import annotations

import argparse
import sys
import tomllib
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from core.audit import record  # noqa: E402
from core.auth.roles import Role  # noqa: E402
from core.clock import utc_now  # noqa: E402
from core.config import ConfigError, Settings  # noqa: E402
from core.db.engine import (  # noqa: E402
    build_engine,
    build_session_factory,
    session_scope,
)
from core.db.models import User  # noqa: E402

SECRETS = REPO_ROOT / ".streamlit" / "secrets.toml"

#: Whoever runs the seed script is acting as the system, not as a person.
SEED_ACTOR = "system:seed_faculty"


def load_settings() -> Settings:
    if SECRETS.exists():
        with SECRETS.open("rb") as handle:
            return Settings.from_mapping(tomllib.load(handle))
    return Settings.from_env()


def seed(settings: Settings, *, dry_run: bool = False) -> int:
    """Upsert a FACULTY row per allow-listed email. Returns the change count."""
    if not settings.faculty_allowlist and not settings.admin_allowlist:
        print("Allow-list is empty — nothing to seed.")
        print("Add [rubriq] faculty_allowlist to .streamlit/secrets.toml.")
        return 0

    wanted: dict[str, Role] = {}
    for email in settings.faculty_allowlist:
        wanted[email] = Role.FACULTY
    for email in settings.admin_allowlist:  # admin wins, same as resolve_role
        wanted[email] = Role.ADMIN

    factory = build_session_factory(build_engine(settings))
    changes = 0

    with session_scope(factory) as session:
        for email, role in sorted(wanted.items()):
            user = session.get(User, email)

            if user is None:
                print(f"  NEW       {email:<40} {role}")
                changes += 1
                if not dry_run:
                    now = utc_now()
                    session.add(
                        User(
                            email=email,
                            role=role,
                            name="",
                            created_at=now,
                            last_seen_at=now,
                        )
                    )
                    record(
                        session,
                        actor_email=SEED_ACTOR,
                        action="user.seeded",
                        entity="User",
                        entity_id=email,
                        payload={"role": str(role)},
                    )
            elif user.role != role:
                print(f"  PROMOTED  {email:<40} {user.role} -> {role}")
                changes += 1
                if not dry_run:
                    record(
                        session,
                        actor_email=SEED_ACTOR,
                        action="user.role_changed",
                        entity="User",
                        entity_id=email,
                        payload={"from": str(user.role), "to": str(role)},
                    )
                    user.role = role
            else:
                print(f"  UNCHANGED {email:<40} {role}")

        if dry_run:
            session.rollback()

    return changes


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="show what would change without writing anything",
    )
    args = parser.parse_args()

    try:
        settings = load_settings()
    except ConfigError as exc:
        print(f"Configuration error: {exc}", file=sys.stderr)
        return 1

    print(f"Database: {settings.redacted()['database_url']}")
    changes = seed(settings, dry_run=args.dry_run)

    if args.dry_run:
        print(f"\nDry run — {changes} change(s) would be made. Nothing written.")
    else:
        print(f"\n{changes} change(s) written.")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
