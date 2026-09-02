"""Fix item 7 — enrollment/import validation.

The named failure: *"A 40-row CSV imports 31 rows and reports success."* Every
test here is about the nine rows, not the thirty-one.
"""

from __future__ import annotations

import pytest
from sqlalchemy import select

from core.academics.enrollment import (
    TEMPLATE_CSV,
    ImportVerdict,
    commit_enrollment_import,
    list_enrollments,
    preview_enrollment_import,
    rejected_rows_csv,
)
from core.db.engine import session_scope
from core.db.models import Enrollment
from core.errors import NotAuthorized, ValidationError

GOOD_CSV = (
    "email,name,prn,batch,group_label\n"
    "new.one@pccoepune.org,New One,125M1H101,A,G1\n"
    "new.two@pccoepune.org,New Two,125M1H102,A,G1\n"
)


def _verdicts(preview):
    return [row.verdict for row in preview.rows]


class TestPreviewWritesNothing:
    def test_a_preview_commits_no_rows(self, db_factory, world, settings) -> None:
        with session_scope(db_factory) as session:
            preview = preview_enrollment_import(
                world.faculty_a,
                session,
                subject_id=world.subject_a,
                csv_text=GOOD_CSV,
                settings=settings,
            )
            assert len(preview.committable) == 2

        with session_scope(db_factory) as session:
            rows = session.scalars(
                select(Enrollment).where(Enrollment.subject_id == world.subject_a)
            ).all()

        assert len(rows) == 1, "only the fixture's student — preview must not write"


class TestPerRowVerdicts:
    def test_every_rejection_category_is_reported_separately(
        self, db_factory, world, settings
    ) -> None:
        csv_text = (
            "email,name,prn,batch,group_label\n"
            "new.one@pccoepune.org,New One,125M1H101,A,G1\n"  # NEW
            "outsider@gmail.com,Outsider,125M1H102,A,G1\n"  # INVALID_DOMAIN
            "not-an-email,Broken,125M1H103,A,G1\n"  # MALFORMED
            "new.one@pccoepune.org,Dupe,125M1H104,A,G1\n"  # DUPLICATE_IN_FILE
            "manthan.sankpal@pccoepune.org,Manthan,125M1H064,A,G1\n"  # ALREADY_ENROLLED
            "guide@pccoepune.org,Anjana,X,A,G1\n"  # FACULTY_ADDRESS
            ",No Email,125M1H105,A,G1\n"  # MALFORMED
        )

        with session_scope(db_factory) as session:
            preview = preview_enrollment_import(
                world.faculty_a,
                session,
                subject_id=world.subject_a,
                csv_text=csv_text,
                settings=settings,
            )

        assert _verdicts(preview) == [
            ImportVerdict.NEW,
            ImportVerdict.INVALID_DOMAIN,
            ImportVerdict.MALFORMED,
            ImportVerdict.DUPLICATE_IN_FILE,
            ImportVerdict.ALREADY_ENROLLED,
            ImportVerdict.FACULTY_ADDRESS,
            ImportVerdict.MALFORMED,
        ]
        assert len(preview.committable) == 1
        assert len(preview.rejected) == 6

    def test_line_numbers_point_at_the_file(self, db_factory, world, settings) -> None:
        """A verdict nobody can locate in the source file is not actionable."""
        with session_scope(db_factory) as session:
            preview = preview_enrollment_import(
                world.faculty_a,
                session,
                subject_id=world.subject_a,
                csv_text=GOOD_CSV,
                settings=settings,
            )

        assert [row.line_number for row in preview.rows] == [2, 3]

    def test_a_trailing_blank_line_is_not_an_error(
        self, db_factory, world, settings
    ) -> None:
        with session_scope(db_factory) as session:
            preview = preview_enrollment_import(
                world.faculty_a,
                session,
                subject_id=world.subject_a,
                csv_text=GOOD_CSV + "\n\n",
                settings=settings,
            )

        assert len(preview.rows) == 2


class TestHeaders:
    def test_a_missing_required_column_is_refused_not_guessed(
        self, db_factory, world, settings
    ) -> None:
        with session_scope(db_factory) as session:
            with pytest.raises(ValidationError) as excinfo:
                preview_enrollment_import(
                    world.faculty_a,
                    session,
                    subject_id=world.subject_a,
                    csv_text="email,name\na@pccoepune.org,A\n",
                    settings=settings,
                )

        assert "prn" in str(excinfo.value)

    def test_the_excel_utf8_bom_does_not_break_the_first_header(
        self, db_factory, world, settings
    ) -> None:
        """Excel's "CSV UTF-8" writes a BOM that lands on the `email` header."""
        with session_scope(db_factory) as session:
            preview = preview_enrollment_import(
                world.faculty_a,
                session,
                subject_id=world.subject_a,
                csv_text="﻿" + GOOD_CSV,
                settings=settings,
            )

        assert _verdicts(preview) == [ImportVerdict.NEW, ImportVerdict.NEW]

    def test_the_template_is_importable_as_is(self, db_factory, world, settings) -> None:
        """The downloadable template must not itself be rejected."""
        with session_scope(db_factory) as session:
            preview = preview_enrollment_import(
                world.faculty_a,
                session,
                subject_id=world.subject_a,
                csv_text=TEMPLATE_CSV,
                settings=settings,
            )

        assert len(preview.committable) == 2


class TestCommit:
    def test_commit_enrolls_only_the_committable_rows(
        self, db_factory, world, settings
    ) -> None:
        csv_text = GOOD_CSV + "outsider@gmail.com,Outsider,125M1H109,A,G1\n"

        with session_scope(db_factory) as session:
            result = commit_enrollment_import(
                world.faculty_a,
                session,
                subject_id=world.subject_a,
                csv_text=csv_text,
                settings=settings,
            )

        assert len(result.committable) == 2
        assert len(result.rejected) == 1

        with session_scope(db_factory) as session:
            roll = list_enrollments(world.faculty_a, session, world.subject_a)

        emails = {e.student_email for e in roll}
        assert emails == {
            world.student_1.email,
            "new.one@pccoepune.org",
            "new.two@pccoepune.org",
        }
        assert "outsider@gmail.com" not in emails

    def test_re_importing_the_same_file_changes_nothing(
        self, db_factory, world, settings
    ) -> None:
        """Idempotence: the fix for "re-running the import doubles everyone"."""
        for _ in range(3):
            with session_scope(db_factory) as session:
                commit_enrollment_import(
                    world.faculty_a,
                    session,
                    subject_id=world.subject_a,
                    csv_text=GOOD_CSV,
                    settings=settings,
                )

        with session_scope(db_factory) as session:
            roll = list_enrollments(world.faculty_a, session, world.subject_a)

        assert len(roll) == 3  # fixture student + the two imported, once each

    def test_a_failure_mid_import_leaves_nothing_behind(
        self, db_factory, world, settings
    ) -> None:
        """All-or-nothing: the transaction is the unit, not the row."""
        with pytest.raises(RuntimeError):
            with session_scope(db_factory) as session:
                commit_enrollment_import(
                    world.faculty_a,
                    session,
                    subject_id=world.subject_a,
                    csv_text=GOOD_CSV,
                    settings=settings,
                )
                raise RuntimeError("something later in the transaction failed")

        with session_scope(db_factory) as session:
            roll = list_enrollments(world.faculty_a, session, world.subject_a)

        assert len(roll) == 1, "a rolled-back import must enrol nobody"

    def test_another_faculty_cannot_import_into_your_subject(
        self, db_factory, world, settings
    ) -> None:
        with session_scope(db_factory) as session:
            with pytest.raises(NotAuthorized):
                commit_enrollment_import(
                    world.faculty_b,
                    session,
                    subject_id=world.subject_a,
                    csv_text=GOOD_CSV,
                    settings=settings,
                )

    def test_a_student_cannot_import_at_all(self, db_factory, world, settings) -> None:
        with session_scope(db_factory) as session:
            with pytest.raises(NotAuthorized):
                commit_enrollment_import(
                    world.student_1,
                    session,
                    subject_id=world.subject_a,
                    csv_text=GOOD_CSV,
                    settings=settings,
                )


class TestRejectedRowsCsv:
    def test_rejects_come_back_as_a_fixable_csv(
        self, db_factory, world, settings
    ) -> None:
        csv_text = GOOD_CSV + "outsider@gmail.com,Outsider,125M1H109,B,G2\n"

        with session_scope(db_factory) as session:
            preview = preview_enrollment_import(
                world.faculty_a,
                session,
                subject_id=world.subject_a,
                csv_text=csv_text,
                settings=settings,
            )

        output = rejected_rows_csv(preview)
        lines = output.strip().splitlines()

        assert lines[0].startswith("email,name,prn,batch,group_label,verdict")
        assert len(lines) == 2, "only the rejected row, plus the header"
        assert "outsider@gmail.com" in lines[1]
        assert "INVALID_DOMAIN" in lines[1]
        # The original values survive, so the fix is an edit not a retype.
        assert "125M1H109" in lines[1]
        assert "B,G2" in lines[1]
