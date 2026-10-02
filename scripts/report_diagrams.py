"""Architecture and ER diagrams for the report, drawn with Pillow.

The versions in ``docs/diagrams/`` are Mermaid, which is right for the
repository — they diff, and GitHub renders them. A Word document cannot, and
there is no Mermaid renderer on this machine, so these redraw the same two
diagrams as images.

They are deliberately *simplified* rather than transcribed. A twenty-table ER
diagram printed at A4 is unreadable; what a reader needs from the report is the
shape of the model and the three relationships that carry the design decisions.
The full version stays in ``docs/diagrams/er.md`` and is referenced from the
report text.
"""

from __future__ import annotations

import math
from pathlib import Path

from PIL import Image, ImageDraw

from scripts.synopsis_diagram import (
    ACCENT_EDGE,
    ACCENT_FILL,
    ARROW,
    BOX_EDGE,
    BOX_FILL,
    GUARD_EDGE,
    GUARD_FILL,
    INK,
    SCALE,
    _box,
    _font,
    _wrap,
)

CORE_FILL = (234, 241, 234)
CORE_EDGE = (46, 110, 70)
APP_FILL = (238, 242, 252)
APP_EDGE = (60, 76, 130)


def _band(draw, xy, label, *, fill, edge, note=""):
    x0, y0, x1, y1 = (v * SCALE for v in xy)
    draw.rounded_rectangle(
        (x0, y0, x1, y1), radius=12 * SCALE, fill=fill, outline=edge, width=2 * SCALE
    )
    font = _font(True, 14)
    draw.text((x0 + 14 * SCALE, y0 + 10 * SCALE), label, font=font, fill=edge)
    if note:
        draw.text(
            (x0 + 14 * SCALE, y0 + 30 * SCALE),
            note,
            font=_font(False, 11),
            fill=(90, 96, 118),
        )


def _plain(draw, xy, text, *, fill, edge):
    _box(draw, xy, text, "", fill=fill, edge=edge, radius=7)


def _line(draw, x0, y0, x1, y1, *, arrow=True, dashed=False):
    x0, y0, x1, y1 = (v * SCALE for v in (x0, y0, x1, y1))
    if dashed:
        steps = 26
        for i in range(0, steps, 2):
            a, b = i / steps, (i + 1) / steps
            draw.line(
                (
                    x0 + (x1 - x0) * a,
                    y0 + (y1 - y0) * a,
                    x0 + (x1 - x0) * b,
                    y0 + (y1 - y0) * b,
                ),
                fill=ARROW,
                width=2 * SCALE,
            )
    else:
        draw.line((x0, y0, x1, y1), fill=ARROW, width=2 * SCALE)

    if arrow and y1 != y0:
        tip = 8 * SCALE if y1 > y0 else -8 * SCALE
        draw.polygon(
            [
                (x1, y1),
                (x1 - 5 * SCALE, y1 - tip),
                (x1 + 5 * SCALE, y1 - tip),
            ],
            fill=ARROW,
        )


def build_architecture(out_path: Path) -> Path:
    """The one architectural rule, drawn: core/ has no Streamlit in it."""
    width, height = 900, 660
    image = Image.new("RGB", (width * SCALE, height * SCALE), "white")
    draw = ImageDraw.Draw(image)

    title = "System Architecture"
    font = _font(True, 17)
    draw.text(
        (width * SCALE / 2 - draw.textlength(title, font=font) / 2, 16 * SCALE),
        title,
        font=font,
        fill=INK,
    )

    _plain(
        draw, (330, 58, 570, 98), "Browser", fill=(245, 245, 248), edge=(120, 126, 148)
    )

    _band(
        draw,
        (60, 122, 840, 262),
        "app/  —  view layer",
        fill=APP_FILL,
        edge=APP_EDGE,
        note="may import streamlit · computes no marks · writes no queries",
    )
    for xy, label in (
        ((80, 172, 250, 212), "main.py\nauth gate"),
        ((266, 172, 436, 212), "pages/\nfaculty · student"),
        ((452, 172, 622, 212), "components/\ncalendar · grid"),
        ((638, 172, 820, 212), "state.py\ncache · flash"),
    ):
        _plain(draw, xy, label.replace("\n", " — "), fill="white", edge=APP_EDGE)

    _band(
        draw,
        (60, 296, 840, 500),
        "core/  —  domain",
        fill=CORE_FILL,
        edge=CORE_EDGE,
        note="ZERO streamlit imports · every function takes actor first",
    )
    row1 = (
        ((80, 348, 232, 386), "auth/"),
        ((244, 348, 396, 386), "academics/"),
        ((408, 348, 560, 386), "rubrics/"),
        ((572, 348, 724, 386), "submissions/"),
        ((736, 348, 820, 386), "groups/"),
    )
    row2 = (
        ((80, 398, 232, 436), "scoring/"),
        ((244, 398, 396, 436), "ai/"),
        ((408, 398, 560, 436), "queries/"),
        ((572, 398, 724, 436), "exports/"),
        ((736, 398, 820, 436), "reports/"),
    )
    for xy, label in row1 + row2:
        fill = GUARD_FILL if label in ("scoring/", "ai/") else "white"
        edge = GUARD_EDGE if label in ("scoring/", "ai/") else CORE_EDGE
        _plain(draw, xy, label, fill=fill, edge=edge)

    _plain(
        draw,
        (80, 448, 396, 484),
        "db/  —  engine · models · types",
        fill="white",
        edge=CORE_EDGE,
    )
    _plain(
        draw,
        (408, 448, 820, 484),
        "audit.py  —  one row per mutation",
        fill="white",
        edge=CORE_EDGE,
    )

    for xy, label in (
        ((110, 536, 330, 584), "rubriq.db (SQLite)"),
        ((350, 536, 550, 584), "uploads/"),
        ((570, 536, 800, 584), "Gemini API (optional)"),
    ):
        _plain(draw, xy, label, fill=(250, 248, 244), edge=(150, 130, 100))

    _line(draw, 450, 98, 450, 122)
    _line(draw, 450, 262, 450, 296)
    _line(draw, 220, 500, 220, 536)
    _line(draw, 450, 500, 450, 536)
    _line(draw, 685, 500, 685, 536)

    note = (
        "The dividing line is enforced by a test: it searches every file under "
        "core/ for a Streamlit import and fails if it finds one."
    )
    small = _font(False, 12)
    draw.text(
        (width * SCALE / 2 - draw.textlength(note, font=small) / 2, 612 * SCALE),
        note,
        font=small,
        fill=(90, 96, 118),
    )

    out_path.parent.mkdir(parents=True, exist_ok=True)
    image.resize((width, height), Image.LANCZOS).save(out_path, dpi=(220, 220))
    return out_path


def build_er(out_path: Path) -> Path:
    """The model's shape, and the three relationships that carry the design."""
    width, height = 900, 780
    image = Image.new("RGB", (width * SCALE, height * SCALE), "white")
    draw = ImageDraw.Draw(image)

    title = "Entity–Relationship Overview"
    font = _font(True, 17)
    draw.text(
        (width * SCALE / 2 - draw.textlength(title, font=font) / 2, 16 * SCALE),
        title,
        font=font,
        fill=INK,
    )

    entities = [
        (
            (60, 62, 250, 116),
            "USER",
            "email PK · role · prn · github",
            BOX_FILL,
            BOX_EDGE,
        ),
        (
            (340, 62, 560, 116),
            "SUBJECT",
            "code · name · semester · owner",
            BOX_FILL,
            BOX_EDGE,
        ),
        ((650, 62, 850, 116), "ENROLLMENT", "student · subject", BOX_FILL, BOX_EDGE),
        (
            (340, 152, 560, 206),
            "PROJECT_CYCLE",
            "subject · title · year",
            BOX_FILL,
            BOX_EDGE,
        ),
        (
            (340, 242, 560, 300),
            "REVIEW_MILESTONE",
            "due_at · max_marks · visible",
            BOX_FILL,
            BOX_EDGE,
        ),
        (
            (60, 242, 268, 300),
            "RUBRIC",
            "version · published_at",
            ACCENT_FILL,
            ACCENT_EDGE,
        ),
        (
            (60, 336, 268, 394),
            "CRITERION",
            "code · weight · max · mandatory",
            ACCENT_FILL,
            ACCENT_EDGE,
        ),
        (
            (640, 242, 850, 300),
            "PROJECT_GROUP",
            "status · decided_by",
            GUARD_FILL,
            GUARD_EDGE,
        ),
        ((640, 336, 850, 394), "GROUP_MEMBER", "group · student", GUARD_FILL, GUARD_EDGE),
        (
            (340, 336, 560, 394),
            "SUBMISSION",
            "version · text · group_id",
            BOX_FILL,
            BOX_EDGE,
        ),
        (
            (340, 424, 560, 478),
            "SUBMISSION_LINK",
            "owner · repo · matched",
            BOX_FILL,
            BOX_EDGE,
        ),
        (
            (60, 424, 268, 478),
            "EVALUATION",
            "pins submission + rubric version",
            ACCENT_FILL,
            ACCENT_EDGE,
        ),
        (
            (60, 508, 268, 562),
            "CRITERION_SCORE",
            "verdict · evidence · score",
            ACCENT_FILL,
            ACCENT_EDGE,
        ),
        (
            (340, 508, 560, 566),
            "SCORE_SHEET",
            "totals · approved_by · at",
            ACCENT_FILL,
            ACCENT_EDGE,
        ),
        (
            (640, 508, 850, 566),
            "SCORE_OVERRIDE",
            "old · new · reason",
            GUARD_FILL,
            GUARD_EDGE,
        ),
        (
            (640, 598, 850, 656),
            "MEMBER_ADJUSTMENT",
            "delta · reason",
            GUARD_FILL,
            GUARD_EDGE,
        ),
        (
            (340, 598, 560, 652),
            "STUDENT_QUERY",
            "question · escalated",
            BOX_FILL,
            BOX_EDGE,
        ),
        (
            (60, 598, 268, 652),
            "AUDIT_LOG",
            "actor · action · payload",
            BOX_FILL,
            BOX_EDGE,
        ),
    ]
    for xy, name, fields, fill, edge in entities:
        _box(draw, xy, name, fields, fill=fill, edge=edge, radius=7)

    # STUDENT_QUERY and AUDIT_LOG are deliberately unlinked here: a query
    # belongs to a milestone and an audit row to nothing at all, and drawing
    # either to SCORE_SHEET would assert a relationship that does not exist.
    links = [
        (250, 89, 340, 89),
        (560, 89, 650, 89),
        (450, 116, 450, 152),
        (450, 206, 450, 242),
        (340, 271, 268, 271),
        (164, 300, 164, 336),
        (560, 271, 640, 271),
        (745, 300, 745, 336),
        (450, 300, 450, 336),
        (450, 394, 450, 424),
        (340, 365, 268, 424),
        (164, 478, 164, 508),
        (268, 451, 340, 530),
        (560, 537, 640, 537),
        (745, 566, 745, 598),
    ]
    for x0, y0, x1, y1 in links:
        _line(draw, x0, y0, x1, y1, arrow=False)

    legend = [
        ("Versioned and frozen once published", ACCENT_FILL, ACCENT_EDGE),
        ("Requires an explicit faculty decision", GUARD_FILL, GUARD_EDGE),
    ]
    y = 690
    for text, fill, edge in legend:
        draw.rounded_rectangle(
            (70 * SCALE, y * SCALE, 96 * SCALE, (y + 18) * SCALE),
            radius=4 * SCALE,
            fill=fill,
            outline=edge,
            width=2 * SCALE,
        )
        draw.text((108 * SCALE, (y + 1) * SCALE), text, font=_font(False, 12), fill=INK)
        y += 28

    note = (
        "Twenty tables in full — see docs/diagrams/er.md for every column and constraint."
    )
    small = _font(False, 12)
    draw.text(
        (width * SCALE / 2 - draw.textlength(note, font=small) / 2, 748 * SCALE),
        note,
        font=small,
        fill=(90, 96, 118),
    )

    out_path.parent.mkdir(parents=True, exist_ok=True)
    image.resize((width, height), Image.LANCZOS).save(out_path, dpi=(220, 220))
    return out_path


# ---------------------------------------------------------------------------
# Shared notation for the DFDs, the use-case diagram and the state machine.
# ---------------------------------------------------------------------------


def _head(draw, x0, y0, x1, y1, *, size=9):
    """An arrowhead at (x1, y1) pointing along the line from (x0, y0).

    ``_line`` only draws a head when the line has vertical travel, which is
    fine for the stacked diagrams but useless for a DFD, where almost every
    flow is diagonal.
    """
    angle = math.atan2(y1 - y0, x1 - x0)
    back, half = size * SCALE, size * SCALE * 0.45
    bx, by = x1 - back * math.cos(angle), y1 - back * math.sin(angle)
    draw.polygon(
        [
            (x1, y1),
            (bx - half * math.sin(angle), by + half * math.cos(angle)),
            (bx + half * math.sin(angle), by - half * math.cos(angle)),
        ],
        fill=ARROW,
    )


def _flow(draw, p0, p1, label="", *, dashed=False, at=None, size=10, head=True):
    """A labelled flow from p0 to p1. ``at`` overrides the label anchor."""
    x0, y0, x1, y1 = (v * SCALE for v in (*p0, *p1))

    if dashed:
        steps = max(10, int(math.hypot(x1 - x0, y1 - y0) / (7 * SCALE)) | 1)
        for i in range(0, steps, 2):
            a, b = i / steps, (i + 1) / steps
            draw.line(
                (
                    x0 + (x1 - x0) * a,
                    y0 + (y1 - y0) * a,
                    x0 + (x1 - x0) * b,
                    y0 + (y1 - y0) * b,
                ),
                fill=ARROW,
                width=2 * SCALE,
            )
    else:
        draw.line((x0, y0, x1, y1), fill=ARROW, width=2 * SCALE)

    if head:
        _head(draw, x0, y0, x1, y1)

    if not label:
        return
    font = _font(False, size)
    lines = label.split("\n")
    cx, cy = (at[0] * SCALE, at[1] * SCALE) if at else ((x0 + x1) / 2, (y0 + y1) / 2)
    cy -= len(lines) * 7 * SCALE
    for line in lines:
        draw.text(
            (cx - draw.textlength(line, font=font) / 2, cy),
            line,
            font=font,
            fill=(96, 104, 128),
        )
        cy += 14 * SCALE


def _entity(draw, xy, text):
    """An external entity: a plain rectangle, per Yourdon/DeMarco."""
    _plain(draw, xy, text, fill=(246, 246, 249), edge=(96, 104, 128))


def _process(draw, centre, r, number, name):
    """A numbered DFD process: a circle with its number above its name."""
    cx, cy = centre
    draw.ellipse(
        ((cx - r) * SCALE, (cy - r) * SCALE, (cx + r) * SCALE, (cy + r) * SCALE),
        fill=ACCENT_FILL,
        outline=ACCENT_EDGE,
        width=2 * SCALE,
    )
    num = _font(True, 13)
    draw.text(
        ((cx * SCALE) - draw.textlength(number, font=num) / 2, (cy - r + 14) * SCALE),
        number,
        font=num,
        fill=ACCENT_EDGE,
    )
    body = _font(False, 11)
    lines = name.split("\n")
    y = cy * SCALE - (len(lines) - 1) * 7 * SCALE - 2 * SCALE
    for line in lines:
        draw.text(
            (cx * SCALE - draw.textlength(line, font=body) / 2, y),
            line,
            font=body,
            fill=INK,
        )
        y += 15 * SCALE


def _store(draw, xy, tag, name):
    """A data store: open-ended, with the identifier in its own cell."""
    x0, y0, x1, y1 = (v * SCALE for v in xy)
    draw.rectangle(
        (x0, y0, x1, y1), fill=(250, 248, 242), outline=GUARD_EDGE, width=2 * SCALE
    )
    split = x0 + 34 * SCALE
    draw.line((split, y0, split, y1), fill=GUARD_EDGE, width=2 * SCALE)
    tf = _font(True, 12)
    draw.text(
        ((x0 + split) / 2 - draw.textlength(tag, font=tf) / 2, (y0 + y1) / 2 - 8 * SCALE),
        tag,
        font=tf,
        fill=GUARD_EDGE,
    )
    bf = _font(False, 11)
    lines = _wrap(draw, name, bf, (x1 - split) - 16 * SCALE)
    y = (y0 + y1) / 2 - len(lines) * 7 * SCALE
    for line in lines:
        draw.text((split + 9 * SCALE, y), line, font=bf, fill=INK)
        y += 14 * SCALE


def _oval(draw, centre, half, text, *, fill=BOX_FILL, edge=BOX_EDGE, size=11):
    """A use-case ellipse."""
    cx, cy = centre
    hw, hh = half
    draw.ellipse(
        ((cx - hw) * SCALE, (cy - hh) * SCALE, (cx + hw) * SCALE, (cy + hh) * SCALE),
        fill=fill,
        outline=edge,
        width=2 * SCALE,
    )
    font = _font(False, size)
    lines = text.split("\n")
    y = cy * SCALE - len(lines) * 7 * SCALE
    for line in lines:
        draw.text(
            (cx * SCALE - draw.textlength(line, font=font) / 2, y),
            line,
            font=font,
            fill=INK,
        )
        y += 14 * SCALE


def _stick(draw, centre, label):
    """A stick actor. A labelled box would do, but an examiner looks for this."""
    cx, cy = centre
    s, ink = SCALE, (60, 76, 130)
    draw.ellipse(
        ((cx - 11) * s, (cy - 34) * s, (cx + 11) * s, (cy - 12) * s),
        outline=ink,
        width=2 * s,
    )
    draw.line((cx * s, (cy - 12) * s, cx * s, (cy + 14) * s), fill=ink, width=2 * s)
    draw.line(
        ((cx - 18) * s, (cy - 2) * s, (cx + 18) * s, (cy - 2) * s), fill=ink, width=2 * s
    )
    draw.line(
        (cx * s, (cy + 14) * s, (cx - 15) * s, (cy + 38) * s), fill=ink, width=2 * s
    )
    draw.line(
        (cx * s, (cy + 14) * s, (cx + 15) * s, (cy + 38) * s), fill=ink, width=2 * s
    )
    font = _font(True, 13)
    draw.text(
        (cx * s - draw.textlength(label, font=font) / 2, (cy + 44) * s),
        label,
        font=font,
        fill=ink,
    )


def _canvas(width, height):
    image = Image.new("RGB", (width * SCALE, height * SCALE), "white")
    return image, ImageDraw.Draw(image)


def _save(image, out_path, width, height):
    out_path.parent.mkdir(parents=True, exist_ok=True)
    image.resize((width, height), Image.LANCZOS).save(out_path, dpi=(220, 220))
    return out_path


def _note(draw, width, y, text):
    font = _font(False, 12)
    draw.text(
        (width * SCALE / 2 - draw.textlength(text, font=font) / 2, y * SCALE),
        text,
        font=font,
        fill=(90, 96, 118),
    )


def build_dfd_l0(out_path: Path) -> Path:
    """Level 0: RubriQ as one process, and the four things outside it."""
    width, height = 900, 620
    image, draw = _canvas(width, height)

    _process(draw, (450, 310), 100, "0", "RubriQ\nReview\nSystem")

    _entity(draw, (40, 80, 200, 136), "Student")
    _entity(draw, (40, 484, 200, 540), "Faculty")
    _entity(draw, (700, 80, 860, 136), "Google OIDC")
    _entity(draw, (700, 484, 860, 540), "Gemini API")

    _flow(draw, (202, 104), (366, 252), "submission files,\nquestions", at=(322, 150))
    _flow(
        draw,
        (342, 282),
        (124, 140),
        "published rubric, deadline,\napproved feedback",
        at=(196, 258),
    )
    _flow(
        draw,
        (202, 516),
        (366, 368),
        "subjects, enrolment, rubrics,\nscores, overrides, approvals",
        at=(330, 500),
    )
    # Anchored well clear of its own line: a diagonal this long sweeps through
    # any label centred on it.
    _flow(
        draw,
        (342, 338),
        (124, 480),
        "review grid, estimates, evidence,\nreports, Excel and TSV",
        at=(150, 360),
    )
    _flow(draw, (698, 104), (534, 252), "email and name\nclaims", at=(578, 150))
    _flow(
        draw,
        (558, 282),
        (776, 140),
        "sign-in request\n(hd=pccoepune.org)",
        at=(706, 258),
    )
    _flow(
        draw,
        (558, 338),
        (776, 480),
        "rubric + de-identified\nsubmission text",
        at=(712, 392),
    )
    _flow(
        draw,
        (698, 516),
        (534, 368),
        "per-criterion JSON: verdict,\nscore, evidence, rationale",
        at=(574, 500),
    )

    _note(
        draw,
        width,
        580,
        "Nothing identifying crosses the boundary to the model, and what returns "
        "is an estimate until a faculty member approves it.",
    )
    return _save(image, out_path, width, height)


def build_dfd_l1(out_path: Path) -> Path:
    """Level 1: process 0 opened up. Seven processes, six stores.

    External entities are repeated down the left margin rather than being drawn
    once and connected seven times. Repeating an entity is conventional in a
    levelled DFD, and it is the difference between a diagram and a thicket.
    """
    width, height = 980, 1290
    image, draw = _canvas(width, height)

    rows = [
        ("Google OIDC", "1.0", "Authenticate\n& resolve role", "D1", "users"),
        (
            "Faculty",
            "2.0",
            "Subjects,\nenrolment,\nmilestones",
            "D2",
            "subjects / enrolment / milestones",
        ),
        ("Faculty", "3.0", "Author &\npublish rubric", "D3", "rubrics / criteria"),
        ("Student", "4.0", "Accept\nsubmission", "D4", "submissions / files / text"),
        (
            "Gemini API",
            "5.0",
            "Evaluate\nagainst rubric",
            "D5",
            "evaluations / criterion scores",
        ),
        ("Faculty", "6.0", "Score, approve\n& export", "D5", "sheets / overrides"),
        ("Student", "7.0", "Answer\nstudent query", "D5", "student queries"),
    ]

    ys = [96, 252, 408, 564, 720, 876, 1032]
    for y, (actor, num, name, tag, store) in zip(ys, rows, strict=True):
        _entity(draw, (28, y - 26, 178, y + 26), actor)
        _process(draw, (430, y), 62, num, name)
        _store(draw, (640, y - 28, 950, y + 28), tag, store)
        _flow(draw, (180, y - 6), (366, y - 6))
        _flow(draw, (494, y - 8), (638, y - 8))
        _flow(draw, (638, y + 10), (494, y + 10))
        _flow(draw, (366, y + 8), (180, y + 8))

    for a, b in zip(ys, ys[1:], strict=False):
        _flow(draw, (430, a + 64), (430, b - 64))

    # The two cross-reads that carry the design: they are the answer to "what
    # can the evaluation process actually see?"
    _flow(draw, (700, 436), (494, 700), "criteria", at=(722, 480), dashed=True)
    _flow(draw, (700, 592), (494, 712), "text_extract", at=(748, 614), dashed=True)

    # D6 is written by all seven. Seven arrows would say nothing that this one
    # and the note below do not.
    _store(draw, (330, 1156, 760, 1212), "D6", "audit log")
    _flow(draw, (430, 1096), (430, 1154), "one row per mutation", at=(548, 1130))

    _note(
        draw,
        width,
        1232,
        "Every process writes to D6, inside the same transaction as the change "
        "it records.",
    )
    _note(
        draw,
        width,
        1258,
        "Process 5.0 reads D3 and D4 and writes neither. It has no path to D1 "
        "or D2 at all, which is what “the graph has no tools” means.",
    )
    return _save(image, out_path, width, height)


def build_use_case(out_path: Path) -> Path:
    """Eighteen use cases, two actors, and the seven «include» guards.

    One column, not two. A second column halves the height and costs more than
    it saves: every association from the lower actor then crosses the first
    column, striking through the labels it passes over.

    The guards get a column of their own because they are the reason to draw
    this at all — each dashed arrow is an invariant that cannot be skipped.
    """
    width, height = 1010, 1300
    image, draw = _canvas(width, height)

    draw.rectangle(
        (232 * SCALE, 56 * SCALE, 988 * SCALE, 1216 * SCALE),
        outline=(176, 182, 200),
        width=2 * SCALE,
    )
    draw.text(
        (246 * SCALE, 64 * SCALE), "RubriQ", font=_font(True, 14), fill=(110, 118, 140)
    )

    half = (112, 26)
    student = [
        "View published\nrubric",
        "Submit work",
        "Ask about\na milestone",
        "View feedback",
    ]
    faculty = [
        "Create subject\nand cycle",
        "Import enrolment\nfrom CSV",
        "Define review\nmilestone",
        "Author rubric",
        "Publish rubric",
        "Run AI\nevaluation",
        "Review and\noverride scores",
        "Approve\nscore sheet",
        "Export to\nExcel / TSV",
        "Answer escalated\nquestion",
        "View reports",
        "Reinstate an\nabsent student",
        "Browse\nactivity log",
    ]

    ys = [112 + i * 62 for i in range(18)]
    sign_in = ys[4]

    _stick(draw, (112, 196), "Student")
    _stick(draw, (112, 824), "Faculty")

    for text, y in zip(student, ys[:4], strict=True):
        _oval(draw, (470, y), half, text)
        _flow(draw, (150, 192), (356, y), head=False)

    _oval(draw, (470, sign_in), half, "Sign in with\ninstitute account")
    _flow(draw, (150, 200), (356, sign_in), head=False)
    _flow(draw, (150, 814), (356, sign_in), head=False)

    for text, y in zip(faculty, ys[5:], strict=True):
        _oval(draw, (470, y), half, text)
        _flow(draw, (150, 820), (356, y), head=False)

    guards = {
        "c": ("Extract text\nfrom files", 180),
        "a": ("Assert institute\ndomain & role", 340),
        "b": ("Validate weights\nsum to 100", 530),
        "e": ("Strip student\nidentity", 690),
        "d": ("Verify evidence\nagainst text", 830),
        "f": ("Apply late /\nabsence policy", 980),
        "g": ("Write audit row", 1130),
    }
    for text, y in guards.values():
        _oval(draw, (852, y), (92, 26), text, fill=GUARD_FILL, edge=GUARD_EDGE)

    includes = [
        (ys[1], "c"),
        (sign_in, "a"),
        (ys[9], "b"),
        (ys[10], "e"),
        (ys[10], "d"),
        (ys[12], "f"),
        (ys[12], "g"),
        (ys[11], "g"),
        (ys[9], "g"),
        (ys[6], "g"),
        (ys[16], "g"),
    ]
    # Five of these land on "Write audit row". Aimed at one point their
    # arrowheads stack into a blot, so they fan across the oval's left arc.
    grouped: dict[str, list[int]] = {}
    for sy, key in includes:
        grouped.setdefault(key, []).append(sy)
    for key, sources in grouped.items():
        gy = guards[key][1]
        for i, sy in enumerate(sources):
            offset = 0.0 if len(sources) == 1 else (i - (len(sources) - 1) / 2) * 11
            _flow(
                draw,
                (584, sy),
                (758 + abs(offset) * 0.4, gy + offset),
                dashed=True,
            )

    draw.text(
        (700 * SCALE, 1182 * SCALE),
        "– – –  «include»",
        font=_font(False, 12),
        fill=ARROW,
    )
    _note(
        draw,
        width,
        1240,
        "Google OIDC and the Gemini API are secondary actors. They are drawn as "
        "external entities on the context diagram rather than repeated here.",
    )
    return _save(image, out_path, width, height)


def build_eval_state(out_path: Path) -> Path:
    """The evaluation state machine, with both failure loops drawn.

    This stands in for a sequence diagram on purpose. The flow has two
    conditional loops, which a state machine draws exactly and a sequence
    diagram draws badly.
    """
    width, height = 940, 820
    image, draw = _canvas(width, height)

    def dot(x, y, *, ring=False):
        draw.ellipse(
            ((x - 9) * SCALE, (y - 9) * SCALE, (x + 9) * SCALE, (y + 9) * SCALE),
            fill="white" if ring else INK,
            outline=INK,
            width=2 * SCALE,
        )
        if ring:
            draw.ellipse(
                ((x - 5) * SCALE, (y - 5) * SCALE, (x + 5) * SCALE, (y + 5) * SCALE),
                fill=INK,
            )

    dot(430, 32)
    _box(
        draw,
        (300, 62, 560, 122),
        "prepare",
        "strip identity, chunk criteria",
        fill=ACCENT_FILL,
        edge=ACCENT_EDGE,
    )
    _box(
        draw,
        (300, 172, 560, 232),
        "evaluate",
        "one model call for one batch",
        fill=BOX_FILL,
        edge=BOX_EDGE,
    )
    _box(
        draw,
        (288, 282, 572, 346),
        "parse_schema",
        "Pydantic validation",
        fill=BOX_FILL,
        edge=BOX_EDGE,
    )
    _box(
        draw,
        (652, 278, 920, 342),
        "repair",
        "re-prompt with the error",
        fill=GUARD_FILL,
        edge=GUARD_EDGE,
    )
    _box(
        draw,
        (300, 408, 572, 480),
        "verify_evidence",
        "rapidfuzz >= 90 vs text",
        fill=ACCENT_FILL,
        edge=ACCENT_EDGE,
    )
    _box(
        draw,
        (16, 408, 268, 480),
        "demote_criterion",
        "NO_EVIDENCE, score 0",
        fill=GUARD_FILL,
        edge=GUARD_EDGE,
    )
    _box(
        draw,
        (300, 548, 572, 616),
        "aggregate",
        "collect, advance cursor",
        fill=BOX_FILL,
        edge=BOX_EDGE,
    )
    dot(430, 690, ring=True)

    _flow(draw, (430, 42), (430, 60))
    _flow(draw, (430, 124), (430, 170))
    _flow(draw, (430, 234), (430, 280))
    _flow(draw, (430, 348), (430, 406), "valid", at=(462, 386))
    _flow(draw, (574, 292), (650, 292), "invalid, attempt 1", at=(612, 282))
    _flow(draw, (650, 326), (574, 326), "re-validate", at=(612, 316))
    _flow(draw, (286, 314), (270, 414), "invalid, attempts\nexhausted", at=(176, 372))
    _flow(draw, (430, 482), (430, 546))
    _flow(draw, (170, 482), (300, 566))

    # Provider failure: parse_schema straight to aggregate, down the right
    # gutter. It leaves below both repair arrows so the three never overlap.
    _flow(draw, (574, 344), (624, 344), head=False)
    _flow(draw, (624, 344), (624, 582), head=False)
    _flow(draw, (624, 582), (576, 582), "provider failed", at=(686, 462))

    # Batches remain: aggregate back up into evaluate, up the left gutter.
    _flow(draw, (300, 592), (284, 592), head=False)
    _flow(draw, (284, 592), (284, 202), head=False)
    _flow(draw, (284, 202), (298, 202), "batches remain", at=(284, 150))

    _flow(draw, (430, 618), (430, 678), "all batches done,\nor run FAILED", at=(540, 652))

    _note(
        draw,
        width,
        724,
        "One repair attempt per batch. A bad batch resolves to NO_EVIDENCE and "
        "the run continues; a dead provider fails the run instead of recording "
        "a page of zeroes.",
    )
    _note(
        draw,
        width,
        756,
        "No arithmetic happens in this machine. Totals are computed afterwards, "
        "from the persisted rows.",
    )
    return _save(image, out_path, width, height)


if __name__ == "__main__":
    root = Path(__file__).resolve().parents[1] / "docs" / "report"
    for builder, name in (
        (build_architecture, "architecture.png"),
        (build_er, "er.png"),
        (build_dfd_l0, "dfd-l0.png"),
        (build_dfd_l1, "dfd-l1.png"),
        (build_use_case, "use-case.png"),
        (build_eval_state, "eval-state.png"),
    ):
        print(builder(root / name))
