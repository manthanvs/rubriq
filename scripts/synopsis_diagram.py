"""Draw the system flow diagram for the synopsis, as a PNG.

Pillow rather than a drawing tool, for the same reason the synopsis itself is a
script: the flow will change before the viva, and a diagram nobody can
regenerate goes stale the first time it does.

Drawn at 3x and downscaled on the way out, because a diagram that looks fine on
screen and furry in print is the usual failure here.
"""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

SCALE = 3
WIDTH, HEIGHT = 900, 1180

INK = (25, 32, 56)
BOX_FILL = (242, 245, 252)
BOX_EDGE = (60, 76, 130)
ACCENT_FILL = (232, 243, 236)
ACCENT_EDGE = (46, 110, 70)
GUARD_FILL = (253, 242, 234)
GUARD_EDGE = (168, 92, 32)
ARROW = (90, 100, 130)

FONT_DIR = Path("C:/Windows/Fonts")


def _font(bold: bool, size: int) -> ImageFont.FreeTypeFont:
    name = "timesbd.ttf" if bold else "times.ttf"
    path = FONT_DIR / name
    if path.exists():
        return ImageFont.truetype(str(path), size * SCALE)
    return ImageFont.load_default()


def _wrap(draw, text: str, font, max_width: int) -> list[str]:
    words, lines, line = text.split(), [], ""
    for word in words:
        trial = f"{line} {word}".strip()
        if draw.textlength(trial, font=font) <= max_width:
            line = trial
        else:
            if line:
                lines.append(line)
            line = word
    if line:
        lines.append(line)
    return lines


def _box(draw, xy, title, subtitle, *, fill, edge, radius=10):
    x0, y0, x1, y1 = (v * SCALE for v in xy)
    draw.rounded_rectangle(
        (x0, y0, x1, y1), radius=radius * SCALE, fill=fill, outline=edge, width=2 * SCALE
    )

    title_font = _font(True, 15)
    sub_font = _font(False, 12)
    inner = (x1 - x0) - 24 * SCALE

    title_lines = _wrap(draw, title, title_font, inner)
    sub_lines = _wrap(draw, subtitle, sub_font, inner) if subtitle else []

    line_h = 20 * SCALE
    sub_h = 17 * SCALE
    total = len(title_lines) * line_h + len(sub_lines) * sub_h
    y = (y0 + y1) / 2 - total / 2

    for line in title_lines:
        w = draw.textlength(line, font=title_font)
        draw.text(((x0 + x1) / 2 - w / 2, y), line, font=title_font, fill=INK)
        y += line_h

    for line in sub_lines:
        w = draw.textlength(line, font=sub_font)
        draw.text(((x0 + x1) / 2 - w / 2, y + 2 * SCALE), line, font=sub_font, fill=INK)
        y += sub_h


def _arrow(draw, x, y0, y1, label=None):
    x, y0, y1 = x * SCALE, y0 * SCALE, y1 * SCALE
    draw.line((x, y0, x, y1 - 7 * SCALE), fill=ARROW, width=2 * SCALE)
    draw.polygon(
        [
            (x, y1),
            (x - 5 * SCALE, y1 - 9 * SCALE),
            (x + 5 * SCALE, y1 - 9 * SCALE),
        ],
        fill=ARROW,
    )
    if label:
        font = _font(False, 11)
        draw.text(
            (x + 10 * SCALE, (y0 + y1) / 2 - 8 * SCALE),
            label,
            font=font,
            fill=ARROW,
        )


def _side_arrow(draw, x0, x1, y, label=None, *, back=False):
    x0, x1, y = x0 * SCALE, x1 * SCALE, y * SCALE
    draw.line((x0, y, x1, y), fill=ARROW, width=2 * SCALE)
    tip, back_off = (x1, -9 * SCALE) if not back else (x1, 9 * SCALE)
    draw.polygon(
        [
            (tip, y),
            (tip + back_off, y - 5 * SCALE),
            (tip + back_off, y + 5 * SCALE),
        ],
        fill=ARROW,
    )
    if label:
        font = _font(False, 11)
        w = draw.textlength(label, font=font)
        draw.text(((x0 + x1) / 2 - w / 2, y - 20 * SCALE), label, font=font, fill=ARROW)


def build(out_path: Path) -> Path:
    image = Image.new("RGB", (WIDTH * SCALE, HEIGHT * SCALE), "white")
    draw = ImageDraw.Draw(image)

    heading = _font(True, 17)
    text = "RubriQ — Flow of Work"
    w = draw.textlength(text, font=heading)
    draw.text((WIDTH * SCALE / 2 - w / 2, 18 * SCALE), text, font=heading, fill=INK)

    left, right = 250, 650
    mid = (left + right) / 2

    steps = [
        (
            72,
            "Faculty creates the rubric",
            "Criteria, weights, marks; weights must total 100",
            BOX_FILL,
            BOX_EDGE,
        ),
        (
            162,
            "Rubric is published",
            "The version is frozen and cannot be edited",
            BOX_FILL,
            BOX_EDGE,
        ),
        (
            252,
            "Student sees the rubric before submitting",
            "This is the main idea of the system",
            ACCENT_FILL,
            ACCENT_EDGE,
        ),
        (
            342,
            "Student uploads the work",
            "PDF / DOCX / TXT, and an optional GitHub link",
            BOX_FILL,
            BOX_EDGE,
        ),
        (
            432,
            "Text is read out of the file",
            "Stored at upload, so no later step opens the file",
            BOX_FILL,
            BOX_EDGE,
        ),
        (
            522,
            "AI checks the work against each criterion",
            "Returns a verdict, a score and a quoted line",
            BOX_FILL,
            BOX_EDGE,
        ),
        (
            612,
            "Evidence check",
            "Is the quoted line really in the student's file?",
            GUARD_FILL,
            GUARD_EDGE,
        ),
        (
            722,
            "Estimated score sheet",
            "Marks and late penalty calculated in Python, not by the AI",
            BOX_FILL,
            BOX_EDGE,
        ),
        (
            812,
            "Faculty reviews and may override",
            "Any change needs a reason, and is recorded",
            BOX_FILL,
            BOX_EDGE,
        ),
        (
            902,
            "Faculty approves",
            "Only now does the estimate become a real mark",
            ACCENT_FILL,
            ACCENT_EDGE,
        ),
    ]

    for top, title, subtitle, fill, edge in steps:
        _box(draw, (left, top, right, top + 58), title, subtitle, fill=fill, edge=edge)

    for i in range(len(steps) - 1):
        top = steps[i][0]
        # The arrow leaving the evidence check is the "found" path.
        label = "found" if steps[i][1] == "Evidence check" else None
        _arrow(draw, mid, top + 58, steps[i + 1][0], label)

    # The guard's failure branch. The success path is simply the arrow that
    # continues downward, so it is labelled rather than drawn twice.
    _box(
        draw,
        (672, 596, 890, 668),
        "Marked NO EVIDENCE",
        "Score 0, flagged for the faculty member",
        fill=GUARD_FILL,
        edge=GUARD_EDGE,
    )
    _side_arrow(draw, right, 672, 632, "not found")

    # Two outputs after approval.
    _box(
        draw,
        (60, 1010, 420, 1070),
        "Excel / TSV export",
        "For the department's records",
        fill=BOX_FILL,
        edge=BOX_EDGE,
    )
    _box(
        draw,
        (480, 1010, 840, 1070),
        "Student sees the feedback",
        "What was followed, and what was not",
        fill=ACCENT_FILL,
        edge=ACCENT_EDGE,
    )
    draw.line(
        (240 * SCALE, 980 * SCALE, 660 * SCALE, 980 * SCALE),
        fill=ARROW,
        width=2 * SCALE,
    )
    _arrow(draw, mid, 960, 980)
    _arrow(draw, 240, 980, 1010)
    _arrow(draw, 660, 980, 1010)

    note = "Every step above writes one audit row: who did what, and when."
    font = _font(False, 12)
    w = draw.textlength(note, font=font)
    draw.text(
        (WIDTH * SCALE / 2 - w / 2, 1110 * SCALE), note, font=font, fill=(90, 96, 118)
    )

    out_path.parent.mkdir(parents=True, exist_ok=True)
    image.resize((WIDTH, HEIGHT), Image.LANCZOS).save(out_path, dpi=(220, 220))
    return out_path


if __name__ == "__main__":
    print(build(Path(__file__).resolve().parents[1] / "docs" / "report" / "flow.png"))
