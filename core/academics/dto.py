"""Plain values returned by the academics services.

Services hand back these, never ORM rows. Three reasons, all of them things
that bite in Streamlit specifically:

* A detached ``Subject`` lazy-loading a relationship after ``session_scope``
  closes raises, and it raises in the view layer where the traceback is
  useless (fix item 13).
* A frozen value cannot be mutated by a page and handed back to a service.
* It keeps ``app/`` unable to write its own queries, which is what stops
  scoping leaking out of ``core/`` (fix item 3).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal


@dataclass(frozen=True, slots=True)
class SubjectDTO:
    id: int
    code: str
    name: str
    semester: int
    owner_email: str
    enrolled_count: int = 0

    @property
    def label(self) -> str:
        return f"{self.code} — {self.name}"


@dataclass(frozen=True, slots=True)
class CycleDTO:
    id: int
    subject_id: int
    title: str
    academic_year: str


@dataclass(frozen=True, slots=True)
class MilestoneDTO:
    """A milestone, carrying enough subject context to render on its own.

    The subject code rides along because both calendars group by it, and a
    second query per row to fetch it is how a calendar page gets slow.
    """

    id: int
    cycle_id: int
    subject_id: int
    subject_code: str
    subject_name: str
    index: int
    title: str
    description: str | None
    due_at: datetime
    max_marks: Decimal
    is_visible: bool


@dataclass(frozen=True, slots=True)
class EnrollmentDTO:
    id: int
    student_email: str
    student_name: str
    prn: str | None
    batch: str | None
    group_label: str | None
