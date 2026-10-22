"""Build a silent walkthrough video of RubriQ's features.

A title card, then one caption card and one screen per feature, then a
closing card — encoded to MP4 at 1280x720.

**This is not a substitute for a narrated screen recording**, and it does not
pretend to be. It shows static captures with text over them; it cannot show a
dialog opening or a filter being applied. Record the real thing with Win+G or
OBS and talk over it — `docs/viva-script.md` is the shot list. This exists so
there is something to submit, embed in a presentation, or play on a loop
while talking.

The captures it uses are 800x450, so the picture is upscaled and soft. Drop
higher-resolution files into `docs/report/screens/` and rebuild; the frame
size here is the only thing that caps it.

    make video
    python scripts/build_demo_video.py
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

import imageio.v2 as imageio  # noqa: E402
import numpy as np  # noqa: E402
from PIL import Image, ImageDraw  # noqa: E402

from scripts.build_output_screens_docx import find as find_screen  # noqa: E402
from scripts.synopsis_diagram import FONT_DIR  # noqa: E402

DEFAULT_OUT = REPO_ROOT / "docs" / "report" / "RubriQ_Walkthrough.mp4"

W, H = 1280, 720
FPS = 30

INK = (22, 26, 36)
MUTED = (104, 112, 130)
ACCENT = (47, 91, 208)
PAPER = (255, 255, 255)
CARD = (245, 247, 250)

#: (seconds on screen, screen stem or None for a text-only card, heading, body)
#: A card with no screen is a section marker; one with a screen shows it below
#: the heading. Timings are deliberately slow — this is read, not narrated.
STORY: tuple[tuple[float, str | None, str, str], ...] = (
    (
        4.0,
        None,
        "RubriQ",
        "Rubric-driven, AI-assisted project review for PCCOE\n"
        "Manthan Sankpal · 125M1H064 · MCA Semester III",
    ),
    (
        5.0,
        None,
        "The problem",
        "Students are marked against a rubric they usually see only after "
        "they have been marked, and the reasoning behind a mark is rarely "
        "written down anywhere.",
    ),
    (
        5.0,
        "01-sign-in",
        "Institute sign-in",
        "Google sign-in restricted to @pccoepune.org, checked on the server. "
        "Faculty or student is decided from a list — never self-selected.",
    ),
    (
        5.5,
        "03-rubric-builder",
        "The rubric is published first, and frozen",
        "Five criteria, each with the evidence it expects. Once published it "
        "cannot be edited: changes create a new version, so work already "
        "graded stays valid.",
    ),
    (
        6.0,
        "05-student-submit",
        "The student reads it before submitting",
        "“What you are being marked on” sits above the upload box. The "
        "lateness penalty is stated before anything is confirmed. This is the "
        "whole idea of the project.",
    ),
    (
        5.0,
        "04-student-dashboard",
        "Deadlines, and where each review stands",
        "A countdown to the next deadline, and a status for every review — "
        "submitted at which version, or not yet.",
    ),
    (
        6.0,
        None,
        "How the AI is used",
        "It suggests a score per criterion and must quote the student's own "
        "words. Identity is stripped first. Every quote is checked back "
        "against the document — a quote that is not really there is thrown "
        "away and recorded as no evidence.",
    ),
    (
        6.0,
        "06-review-grid",
        "The review grid",
        "One row per student, one column per criterion. Absent is a status, "
        "not a zero. A student who never submitted still keeps a row.",
    ),
    (
        5.5,
        "02-faculty-dashboard",
        "Nothing is a mark until a person approves it",
        "Approval carries a name and a time, and is blocked while a mandatory "
        "criterion has no evidence. Every override needs a written reason.",
    ),
    (
        5.5,
        "07-reports",
        "Reports and export",
        "Distribution across the class and the department's grading bands. "
        "Exports to Excel carry the same numbers as the screen.",
    ),
    (
        5.0,
        None,
        "Built to be checked",
        "All domain logic sits in a package with zero Streamlit imports, "
        "enforced by a test. Every mark is arithmetic in ordinary code, never "
        "in the model.",
    ),
    (
        4.5,
        None,
        "RubriQ",
        "github.com/manthanvs/rubriq\nrubriq.streamlit.app",
    ),
)


def _font(bold: bool, px: int):
    """A font at the size asked for.

    Not ``synopsis_diagram._font``: that one multiplies by SCALE, because
    those diagrams are drawn at three times their final size and downscaled.
    Reusing it here tripled every size on the frame — which is why the first
    cut had a heading running off the edge and a screenshot the size of a
    stamp.
    """
    from PIL import ImageFont

    path = FONT_DIR / ("timesbd.ttf" if bold else "times.ttf")
    if path.exists():
        return ImageFont.truetype(str(path), px)
    return ImageFont.load_default(px)


def _wrap(draw, text: str, font, max_width: int) -> list[str]:
    words, lines, line = text.split(), [], ""
    for word in words:
        trial = f"{line} {word}".strip()
        if draw.textlength(trial, font=font) <= max_width or not line:
            line = trial
        else:
            lines.append(line)
            line = word
    if line:
        lines.append(line)
    return lines


def _text(draw, xy, text, font, fill, *, max_width=None, leading=10):
    """Draw text, wrapping it if a width is given. Returns the y it ended at."""
    x, y = xy
    lines = []
    for paragraph in text.split("\n"):
        wrapped = _wrap(draw, paragraph, font, max_width) if max_width else None
        lines.extend(wrapped if wrapped is not None else [paragraph])
    for line in lines:
        draw.text((x, y), line, font=font, fill=fill)
        y += font.size + leading
    return y


def _frame(heading: str, body: str, screen: Path | None) -> Image.Image:
    image = Image.new("RGB", (W, H), PAPER)
    draw = ImageDraw.Draw(image)
    draw.rectangle((0, 0, W, 6), fill=ACCENT)

    if screen is None:
        # A section marker: one centred block, nothing else competing.
        title_font, body_font = _font(True, 62), _font(False, 30)
        inner = W - 300
        title_lines = _wrap(draw, heading, title_font, inner)
        body_lines = [
            line
            for paragraph in body.splitlines()
            for line in _wrap(draw, paragraph, body_font, inner)
        ]
        total = (
            len(title_lines) * (title_font.size + 14)
            + 26
            + len(body_lines) * (body_font.size + 14)
        )
        y = max(60, (H - total) // 2)
        for line in title_lines:
            draw.text((150, y), line, font=title_font, fill=INK)
            y += title_font.size + 14
        y += 26
        for line in body_lines:
            draw.text((150, y), line, font=body_font, fill=MUTED)
            y += body_font.size + 14
        return image

    # A screen card. The picture is the point, so the text is kept to two or
    # three lines and everything left over goes to the image.
    title_font, body_font = _font(True, 30), _font(False, 18)
    margin = 60
    inner = W - margin * 2

    y = 26
    for line in _wrap(draw, heading, title_font, inner):
        draw.text((margin, y), line, font=title_font, fill=INK)
        y += title_font.size + 6
    y += 4
    for paragraph in body.splitlines():
        for line in _wrap(draw, paragraph, body_font, inner):
            draw.text((margin, y), line, font=body_font, fill=MUTED)
            y += body_font.size + 5

    shot = Image.open(screen).convert("RGB")
    available = (inner, H - y - 34)
    scale = min(available[0] / shot.width, available[1] / shot.height)
    shot = shot.resize(
        (int(shot.width * scale), int(shot.height * scale)), Image.LANCZOS
    )
    x = (W - shot.width) // 2
    top = y + 16
    draw.rectangle(
        (x - 3, top - 3, x + shot.width + 2, top + shot.height + 2), fill=CARD
    )
    image.paste(shot, (x, top))
    return image


def build(out_path: Path = DEFAULT_OUT) -> Path:
    missing = [stem for _, stem, *_ in STORY if stem and find_screen(stem) is None]
    if missing:
        raise SystemExit(f"missing screenshots: {missing}")

    out_path.parent.mkdir(parents=True, exist_ok=True)
    writer = imageio.get_writer(
        out_path, fps=FPS, codec="libx264", quality=9, macro_block_size=1
    )
    try:
        for seconds, stem, heading, body in STORY:
            frame = np.asarray(
                _frame(heading, body, find_screen(stem) if stem else None)
            )
            for _ in range(int(seconds * FPS)):
                writer.append_data(frame)
    finally:
        writer.close()
    return out_path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = parser.parse_args()
    out = args.out if args.out.is_absolute() else REPO_ROOT / args.out
    path = build(out)
    seconds = sum(s for s, *_ in STORY)
    size = path.stat().st_size / 1_048_576
    print(f"Wrote {path.relative_to(REPO_ROOT)}  {seconds:.0f}s  {size:.1f} MB")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
