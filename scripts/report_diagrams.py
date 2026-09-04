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


if __name__ == "__main__":
    root = Path(__file__).resolve().parents[1] / "docs" / "report"
    print(build_architecture(root / "architecture.png"))
    print(build_er(root / "er.png"))
