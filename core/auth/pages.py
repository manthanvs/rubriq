"""Which pages exist, and which roles may see them.

This is access-control policy, so it lives in ``core/`` as plain data and is
unit-tested. ``app/navigation.py`` turns these specs into ``st.Page`` objects
and constructs *only* the ones returned for the signed-in role — a student's
faculty pages are never built, so there is nothing to reach by URL (§8).

Adding a page means adding a spec here. There is no second list.
"""

from __future__ import annotations

from dataclasses import dataclass

from core.auth.roles import Role

FACULTY_ONLY = frozenset({Role.FACULTY, Role.ADMIN})
STUDENT_ONLY = frozenset({Role.STUDENT})


@dataclass(frozen=True, slots=True)
class PageSpec:
    """One navigable page.

    ``path`` is relative to ``app/``, because that is where the Streamlit
    entrypoint lives and what ``st.Page`` resolves against.
    """

    key: str
    title: str
    icon: str
    path: str
    roles: frozenset[Role]
    section: str
    default: bool = False


#: §8, in the order they should appear in the sidebar.
ALL_PAGES: tuple[PageSpec, ...] = (
    # --- Faculty ---
    PageSpec(
        key="faculty_dashboard",
        title="Dashboard",
        icon=":material/dashboard:",
        path="pages/faculty/dashboard.py",
        roles=FACULTY_ONLY,
        section="Teaching",
        default=True,
    ),
    PageSpec(
        key="faculty_subjects",
        title="Subjects",
        icon=":material/school:",
        path="pages/faculty/subjects.py",
        roles=FACULTY_ONLY,
        section="Teaching",
    ),
    PageSpec(
        key="faculty_rubrics",
        title="Rubric Builder",
        icon=":material/rule:",
        path="pages/faculty/rubric_builder.py",
        roles=FACULTY_ONLY,
        section="Teaching",
    ),
    PageSpec(
        key="faculty_calendar",
        title="Calendar",
        icon=":material/calendar_month:",
        path="pages/faculty/calendar.py",
        roles=FACULTY_ONLY,
        section="Teaching",
    ),
    PageSpec(
        key="faculty_review_grid",
        title="Review Grid",
        icon=":material/grid_on:",
        path="pages/faculty/review_grid.py",
        roles=FACULTY_ONLY,
        section="Review",
    ),
    PageSpec(
        key="faculty_query_inbox",
        title="Query Inbox",
        icon=":material/inbox:",
        path="pages/faculty/query_inbox.py",
        roles=FACULTY_ONLY,
        section="Review",
    ),
    PageSpec(
        key="faculty_reports",
        title="Reports",
        icon=":material/bar_chart:",
        path="pages/faculty/reports.py",
        roles=FACULTY_ONLY,
        section="Review",
    ),
    # Not in §8's original list. Fix item 15 asks for a filterable view of the
    # audit trail, and it needs somewhere to live.
    PageSpec(
        key="faculty_activity",
        title="Activity",
        icon=":material/history:",
        path="pages/faculty/activity.py",
        roles=FACULTY_ONLY,
        section="Review",
    ),
    # --- Student ---
    PageSpec(
        key="student_dashboard",
        title="Dashboard",
        icon=":material/dashboard:",
        path="pages/student/dashboard.py",
        roles=STUDENT_ONLY,
        section="My work",
        default=True,
    ),
    PageSpec(
        key="student_calendar",
        title="Calendar",
        icon=":material/calendar_month:",
        path="pages/student/calendar.py",
        roles=STUDENT_ONLY,
        section="My work",
    ),
    PageSpec(
        key="student_submit",
        title="Submit",
        icon=":material/upload_file:",
        path="pages/student/submit.py",
        roles=STUDENT_ONLY,
        section="My work",
    ),
    PageSpec(
        key="student_feedback",
        title="Feedback",
        icon=":material/reviews:",
        path="pages/student/feedback.py",
        roles=STUDENT_ONLY,
        section="My work",
    ),
    PageSpec(
        key="student_ask",
        title="Ask RubriQ",
        icon=":material/chat:",
        path="pages/student/ask.py",
        roles=STUDENT_ONLY,
        section="Help",
    ),
)


def pages_for(role: Role) -> tuple[PageSpec, ...]:
    """Every page this role may see, in sidebar order."""
    return tuple(spec for spec in ALL_PAGES if role in spec.roles)


def default_page_for(role: Role) -> PageSpec | None:
    """The page to land on after sign-in."""
    allowed = pages_for(role)
    for spec in allowed:
        if spec.default:
            return spec
    return allowed[0] if allowed else None


def can_access(role: Role, key: str) -> bool:
    """Whether ``role`` may open the page named ``key``.

    An unknown key is refused rather than ignored — a renamed page should
    lock, not silently open.
    """
    for spec in ALL_PAGES:
        if spec.key == key:
            return role in spec.roles
    return False
