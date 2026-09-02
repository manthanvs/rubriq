"""Fix item 2 — submission version consistency.

Phase 3 owns the schema half. The named failure it prevents: *"the student
uploads v2 while faculty is mid-grade on v1, and the approval lands on
whichever row the query happened to return."*

So the guarantee proved here is narrow and concrete: v1 survives v2 intact —
its row, its files, its extracted text and its version number — and exactly one
version is ever marked as the one currently standing.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy.exc import IntegrityError

from core.db.engine import session_scope
from core.db.models import Submission
from core.errors import NotAuthorized, ValidationError
from core.submissions.service import (
    get_submission,
    get_submission_text,
    latest_submission,
    list_submissions,
    submit,
)
from core.submissions.status import SubmissionStatus

V1 = {"synopsis.txt": b"Version one of the synopsis. Objectives and scope."}
V2 = {"synopsis.txt": b"Version two. Objectives, scope and a literature survey."}


@pytest.fixture
def uploads(tmp_path: Path) -> Path:
    return tmp_path / "uploads"


class TestFirstSubmission:
    def test_a_first_upload_is_version_one(self, db_factory, world, uploads) -> None:
        with session_scope(db_factory) as session:
            result = submit(
                world.student_1,
                session,
                milestone_id=world.milestone_visible,
                files=V1,
                uploads_root=uploads,
            )

        assert result.version == 1
        assert result.status is SubmissionStatus.SUBMITTED
        assert result.is_latest
        assert [f.filename for f in result.files] == ["synopsis.txt"]

    def test_text_is_extracted_at_upload(self, db_factory, world, uploads) -> None:
        """So Phase 5 never opens a file, and the guard has something to match."""
        with session_scope(db_factory) as session:
            result = submit(
                world.student_1,
                session,
                milestone_id=world.milestone_visible,
                files=V1,
                uploads_root=uploads,
            )
            text = get_submission_text(world.student_1, session, result.id)

        assert result.has_text
        assert "Objectives and scope" in text

    def test_the_file_is_actually_written(self, db_factory, world, uploads) -> None:
        with session_scope(db_factory) as session:
            submit(
                world.student_1,
                session,
                milestone_id=world.milestone_visible,
                files=V1,
                uploads_root=uploads,
            )

        written = list(uploads.rglob("synopsis.txt"))
        assert len(written) == 1
        assert written[0].read_bytes() == V1["synopsis.txt"]
        assert "v1" in written[0].parts


class TestVersioning:
    def test_a_re_upload_creates_v2_and_leaves_v1_retrievable(
        self, db_factory, world, uploads
    ) -> None:
        """The Phase 3 exit criterion, stated directly."""
        with session_scope(db_factory) as session:
            first = submit(
                world.student_1,
                session,
                milestone_id=world.milestone_visible,
                files=V1,
                uploads_root=uploads,
            )

        with session_scope(db_factory) as session:
            second = submit(
                world.student_1,
                session,
                milestone_id=world.milestone_visible,
                files=V2,
                uploads_root=uploads,
            )

        assert (first.version, second.version) == (1, 2)

        with session_scope(db_factory) as session:
            still_there = get_submission(world.student_1, session, first.id)
            original_text = get_submission_text(world.student_1, session, first.id)

        assert still_there.version == 1
        assert "Version one" in original_text
        assert "literature survey" not in original_text, "v1 must not see v2's text"

    def test_only_the_newest_version_is_marked_standing(
        self, db_factory, world, uploads
    ) -> None:
        for files in (V1, V2, V1):
            with session_scope(db_factory) as session:
                submit(
                    world.student_1,
                    session,
                    milestone_id=world.milestone_visible,
                    files=files,
                    uploads_root=uploads,
                )

        with session_scope(db_factory) as session:
            history = list_submissions(
                world.student_1, session, milestone_id=world.milestone_visible
            )

        assert [s.version for s in history] == [3, 2, 1]
        assert [s.is_latest for s in history] == [True, False, False]
        assert sum(s.is_latest for s in history) == 1

    def test_each_version_keeps_its_own_files_on_disk(
        self, db_factory, world, uploads
    ) -> None:
        """Invariant #7 applied to the filesystem, not just the rows."""
        with session_scope(db_factory) as session:
            submit(
                world.student_1,
                session,
                milestone_id=world.milestone_visible,
                files=V1,
                uploads_root=uploads,
            )
        with session_scope(db_factory) as session:
            submit(
                world.student_1,
                session,
                milestone_id=world.milestone_visible,
                files=V2,
                uploads_root=uploads,
            )

        written = sorted(uploads.rglob("synopsis.txt"))
        assert len(written) == 2, "v2 overwrote v1's file"

        contents = {path.read_bytes() for path in written}
        assert contents == {V1["synopsis.txt"], V2["synopsis.txt"]}

    def test_latest_submission_returns_the_newest(
        self, db_factory, world, uploads
    ) -> None:
        with session_scope(db_factory) as session:
            submit(
                world.student_1,
                session,
                milestone_id=world.milestone_visible,
                files=V1,
                uploads_root=uploads,
            )
        with session_scope(db_factory) as session:
            submit(
                world.student_1,
                session,
                milestone_id=world.milestone_visible,
                files=V2,
                uploads_root=uploads,
            )

        with session_scope(db_factory) as session:
            latest = latest_submission(
                world.student_1,
                session,
                milestone_id=world.milestone_visible,
                student_email=world.student_1.email,
            )

        assert latest.version == 2

    def test_duplicate_versions_are_impossible_in_the_database(
        self, db_factory, world, uploads
    ) -> None:
        """The unique constraint, not just the service logic, forbids it."""
        with session_scope(db_factory) as session:
            submit(
                world.student_1,
                session,
                milestone_id=world.milestone_visible,
                files=V1,
                uploads_root=uploads,
            )

        with pytest.raises(IntegrityError):
            with session_scope(db_factory) as session:
                session.add(
                    Submission(
                        milestone_id=world.milestone_visible,
                        student_email=world.student_1.email,
                        version=1,
                        text_extract="forged",
                    )
                )


class TestValidation:
    def test_a_submission_needs_a_file(self, db_factory, world, uploads) -> None:
        with session_scope(db_factory) as session:
            with pytest.raises(ValidationError):
                submit(
                    world.student_1,
                    session,
                    milestone_id=world.milestone_visible,
                    files={},
                    uploads_root=uploads,
                )

    def test_an_unsupported_extension_is_refused(
        self, db_factory, world, uploads
    ) -> None:
        with session_scope(db_factory) as session:
            with pytest.raises(ValidationError) as excinfo:
                submit(
                    world.student_1,
                    session,
                    milestone_id=world.milestone_visible,
                    files={"code.zip": b"PK\x03\x04"},
                    uploads_root=uploads,
                )

        assert ".pdf" in str(excinfo.value)

    def test_an_empty_file_is_refused(self, db_factory, world, uploads) -> None:
        with session_scope(db_factory) as session:
            with pytest.raises(ValidationError):
                submit(
                    world.student_1,
                    session,
                    milestone_id=world.milestone_visible,
                    files={"empty.txt": b""},
                    uploads_root=uploads,
                )

    def test_a_path_traversal_filename_cannot_escape_the_upload_root(
        self, db_factory, world, uploads
    ) -> None:
        with session_scope(db_factory) as session:
            submit(
                world.student_1,
                session,
                milestone_id=world.milestone_visible,
                files={"../../evil.txt": b"payload"},
                uploads_root=uploads,
            )

        assert not (uploads.parent / "evil.txt").exists()
        assert list(uploads.rglob("evil.txt")), "it should land inside, renamed safely"


class TestScoping:
    def test_a_student_cannot_submit_to_a_draft_milestone(
        self, db_factory, world, uploads
    ) -> None:
        """An unpublished milestone is absent from a student's query."""
        with session_scope(db_factory) as session:
            with pytest.raises(NotAuthorized):
                submit(
                    world.student_1,
                    session,
                    milestone_id=world.milestone_hidden,
                    files=V1,
                    uploads_root=uploads,
                )

    def test_a_student_cannot_submit_to_another_subject(
        self, db_factory, world, uploads
    ) -> None:
        with session_scope(db_factory) as session:
            with pytest.raises(NotAuthorized):
                submit(
                    world.student_2,
                    session,
                    milestone_id=world.milestone_visible,
                    files=V1,
                    uploads_root=uploads,
                )

    def test_faculty_cannot_submit(self, db_factory, world, uploads) -> None:
        with session_scope(db_factory) as session:
            with pytest.raises(NotAuthorized):
                submit(
                    world.faculty_a,
                    session,
                    milestone_id=world.milestone_visible,
                    files=V1,
                    uploads_root=uploads,
                )

    def test_a_student_cannot_read_another_students_submission(
        self, db_factory, world, uploads
    ) -> None:
        with session_scope(db_factory) as session:
            mine = submit(
                world.student_1,
                session,
                milestone_id=world.milestone_visible,
                files=V1,
                uploads_root=uploads,
            )

        with session_scope(db_factory) as session:
            with pytest.raises(NotAuthorized):
                get_submission(world.student_2, session, mine.id)

    def test_listing_ignores_a_students_attempt_to_name_someone_else(
        self, db_factory, world, uploads
    ) -> None:
        with session_scope(db_factory) as session:
            submit(
                world.student_1,
                session,
                milestone_id=world.milestone_visible,
                files=V1,
                uploads_root=uploads,
            )

        with session_scope(db_factory) as session:
            rows = list_submissions(
                world.student_1,
                session,
                milestone_id=world.milestone_visible,
                student_email="someone.else@pccoepune.org",
            )

        assert {r.student_email for r in rows} == {world.student_1.email}

    def test_faculty_sees_the_whole_cohort_for_their_own_milestone(
        self, db_factory, world, uploads
    ) -> None:
        with session_scope(db_factory) as session:
            submit(
                world.student_1,
                session,
                milestone_id=world.milestone_visible,
                files=V1,
                uploads_root=uploads,
            )

        with session_scope(db_factory) as session:
            rows = list_submissions(
                world.faculty_a, session, milestone_id=world.milestone_visible
            )

        assert [r.student_email for r in rows] == [world.student_1.email]

    def test_another_faculty_sees_nothing(self, db_factory, world, uploads) -> None:
        with session_scope(db_factory) as session:
            submit(
                world.student_1,
                session,
                milestone_id=world.milestone_visible,
                files=V1,
                uploads_root=uploads,
            )

        with session_scope(db_factory) as session:
            with pytest.raises(NotAuthorized):
                list_submissions(
                    world.faculty_b, session, milestone_id=world.milestone_visible
                )
