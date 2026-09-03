"""What submitting late actually costs, in a sentence a student can act on.

Fix item 10 asks for the consequence to be visible *before* the upload is
confirmed, not discovered afterwards. The wording has to follow §5.1's bands
rather than generalise them: at four days a submission is recorded ABSENT
rather than penalised by a percentage, and past five it needs an explicit
faculty reinstatement before it can be scored at all. "A late penalty will
apply" is wrong in both of those bands, and wrong in the direction that
understates it.

Pure: it turns a ``PenaltyBand`` into text and touches nothing else, so the
page can look the policy up and this can be tested without a database.
"""

from __future__ import annotations

from decimal import Decimal

from core.scoring.policy import PenaltyBand


def consequence_text(band: PenaltyBand, max_marks: Decimal) -> str:
    """One sentence naming the outcome of submitting into ``band``.

    ``max_marks`` turns the percentage into marks, because "10 %" and "2.50 of
    25" are the same fact and only one of them is one a student reads quickly.
    """
    if band.needs_reinstatement:
        return (
            "It will be recorded as ABSENT, and your guide has to reinstate it "
            "explicitly before it can be scored at all. Submit anyway — the "
            "work is still stored and still gets feedback."
        )

    if band.absent:
        return (
            "It will be recorded as ABSENT rather than scored. Submit anyway — "
            "the work is still stored and still gets feedback."
        )

    if band.percent > 0:
        # Two decimal places, matching every other mark in the system. `:g`
        # looks like it would trim a trailing zero and does not: Decimal keeps
        # the exponent it was constructed with, so "2.50" stays "2.50".
        marks = (band.percent * max_marks / 100).quantize(Decimal("0.01"))
        return (
            f"A {band.percent}% penalty will apply to the milestone total "
            f"— {marks} of {max_marks} marks."
        )

    return "No penalty applies."
