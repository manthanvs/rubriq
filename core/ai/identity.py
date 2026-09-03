"""Identity stripping — invariant #8.

*"The AI never receives identity data. Strip name/PRN before the call; send
submission text + rubric only. Reattach after."*

Fix item 5 names the failure precisely: *"The student's name and PRN ride along
inside ``text_extract`` into the prompt."* They do, because a synopsis has a
title page. So the scrub runs on the extracted text itself, not merely on the
metadata around it, and it runs in ``prepare`` — before anything is sent.

Redaction is deliberately over-eager. A false positive costs the model a little
context; a false negative sends a real student's name to a third-party API.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

#: What replaces anything identifying. Kept short so it costs few tokens and
#: reads as an obvious hole rather than as content.
PLACEHOLDER = "[REDACTED]"

#: PCCOE PRNs look like ``125M1H064``: three digits, a letter, a digit, a
#: letter, three digits. Matched generically so an unknown student's PRN in a
#: group submission is caught too, not only the submitter's own.
PRN_PATTERN = re.compile(r"\b\d{3}[A-Za-z]\d[A-Za-z]\d{3}\b")

EMAIL_PATTERN = re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.-]+\b")

#: Long digit runs are phone numbers or enrolment numbers more often than they
#: are data. Ten or more, so years and marks survive.
LONG_NUMBER_PATTERN = re.compile(r"\b\d{10,}\b")

#: A name shorter than this is too likely to appear as an ordinary word —
#: redacting every "Raj" would shred the document.
MINIMUM_NAME_TOKEN = 4


@dataclass(frozen=True, slots=True)
class ScrubReport:
    """What was removed. Logged, and asserted in tests."""

    redactions: int
    kinds: dict[str, int] = field(default_factory=dict)

    @property
    def clean(self) -> bool:
        return self.redactions == 0


def _name_variants(name: str) -> list[str]:
    """The full name and each substantial part of it.

    "Manthan Sankpal" appears on a title page as the full name and in a
    footer as just the surname; both have to go.
    """
    name = (name or "").strip()
    if not name:
        return []

    variants = {name}
    for token in re.split(r"\s+", name):
        if len(token) >= MINIMUM_NAME_TOKEN:
            variants.add(token)

    # Longest first, so "Manthan Sankpal" is replaced as a unit rather than
    # leaving "[REDACTED] [REDACTED]".
    return sorted(variants, key=len, reverse=True)


def scrub_identity(
    text: str,
    *,
    name: str = "",
    prn: str = "",
    email: str = "",
) -> tuple[str, ScrubReport]:
    """Remove identifying data from submission text.

    Returns the scrubbed text and a report of what went. The report is what
    lets a test assert the prompt is clean rather than trusting that it is.
    """
    if not text:
        return "", ScrubReport(redactions=0)

    counts: dict[str, int] = {}
    scrubbed = text

    def replace(pattern: re.Pattern[str], kind: str) -> None:
        nonlocal scrubbed
        scrubbed, hits = pattern.subn(PLACEHOLDER, scrubbed)
        if hits:
            counts[kind] = counts.get(kind, 0) + hits

    # The known values first, so a specific match wins over a generic one.
    for variant in _name_variants(name):
        replace(re.compile(re.escape(variant), re.IGNORECASE), "name")

    if prn.strip():
        replace(re.compile(re.escape(prn.strip()), re.IGNORECASE), "prn")

    if email.strip():
        replace(re.compile(re.escape(email.strip()), re.IGNORECASE), "email")

    # Then the shapes, catching co-authors and anyone the caller did not name.
    replace(EMAIL_PATTERN, "email_pattern")
    replace(PRN_PATTERN, "prn_pattern")
    replace(LONG_NUMBER_PATTERN, "long_number")

    return scrubbed, ScrubReport(redactions=sum(counts.values()), kinds=counts)


def assert_scrubbed(text: str, *, name: str = "", prn: str = "", email: str = "") -> None:
    """Raise if anything identifying survived. A belt for the braces above.

    Called immediately before the prompt is handed to a provider, so a bug in
    :func:`scrub_identity` fails loudly here instead of silently sending a
    student's name to a third party.
    """
    haystack = text.casefold()
    leaked: list[str] = []

    for value, label in ((prn, "PRN"), (email, "email")):
        if value.strip() and value.strip().casefold() in haystack:
            leaked.append(label)

    for variant in _name_variants(name):
        if variant.casefold() in haystack:
            leaked.append("name")
            break

    if PRN_PATTERN.search(text):
        leaked.append("a PRN-shaped string")
    if EMAIL_PATTERN.search(text):
        leaked.append("an email address")

    if leaked:
        raise AssertionError(
            "Refusing to send identifying data to the AI provider "
            f"(invariant #8). Found: {', '.join(sorted(set(leaked)))}."
        )
