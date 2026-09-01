"""Dashboard — faculty.

Owned subjects, upcoming due dates, and the count of score sheets still
waiting on approval. The count comes from the same 'needs attention' predicate
the Review Grid filters on, so the two can never disagree.
"""

from app.components.placeholder import coming_soon

coming_soon(
    "Dashboard",
    phase=4,
    blurb=(
        "Owned subjects, upcoming due dates, and the count of score sheets "
        "still waiting on approval. The count comes from the same 'needs "
        "attention' predicate the Review Grid filters on, so the two can "
        "never disagree."
    ),
)
