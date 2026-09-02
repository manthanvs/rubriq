"""Where uploaded files live on disk.

Outside the database: the row is the record, the file is the payload. Keeping
multi-megabyte PDFs out of SQLite keeps the database a file you can copy into
the report appendix, which is half the point of decision #8.

Paths are built, never taken from the client. A filename arriving from a
browser is untrusted input — ``../..`` in it would otherwise write wherever it
liked, and on Windows names like ``CON`` and ``PRN`` are reserved devices.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from pathlib import Path, PurePath

#: Anything outside this set becomes an underscore.
_SAFE_CHARS = re.compile(r"[^A-Za-z0-9._-]+")

#: Reserved device names on Windows, which cannot be used as filenames even
#: with an extension.
_WINDOWS_RESERVED = frozenset(
    {"CON", "PRN", "AUX", "NUL"}
    | {f"COM{i}" for i in range(1, 10)}
    | {f"LPT{i}" for i in range(1, 10)}
)

MAX_FILENAME_LENGTH = 120


@dataclass(frozen=True, slots=True)
class StoredFile:
    """One file written to disk."""

    original_name: str
    stored_path: str
    size_bytes: int
    sha256: str


def safe_component(value: str) -> str:
    """Reduce arbitrary text to one safe path segment."""
    cleaned = _SAFE_CHARS.sub("_", value.strip()).strip("._") or "unnamed"
    return cleaned[:MAX_FILENAME_LENGTH]


def safe_filename(filename: str) -> str:
    """Make an uploaded filename safe to write, preserving its extension.

    ``PurePath(...).name`` drops any directory part, so ``../../etc/passwd``
    becomes ``passwd`` before anything else happens.
    """
    name = PurePath(filename).name
    suffix = PurePath(name).suffix.lower()
    stem = safe_component(PurePath(name).stem)

    if stem.upper() in _WINDOWS_RESERVED:
        stem = f"{stem}_file"

    return f"{stem}{suffix}"


def submission_dir(
    root: Path, *, milestone_id: int, student_email: str, version: int
) -> Path:
    """The directory for one submission version."""
    return (
        Path(root)
        / f"m{int(milestone_id)}"
        / safe_component(student_email)
        / f"v{int(version)}"
    )


def save_files(
    root: Path,
    *,
    milestone_id: int,
    student_email: str,
    version: int,
    files: dict[str, bytes],
) -> list[StoredFile]:
    """Write files for one submission version and return their records.

    Versioned directories mean a re-upload never overwrites the previous
    submission's files — invariant #7 applied to the filesystem, not just to
    the rows.
    """
    target = submission_dir(
        root, milestone_id=milestone_id, student_email=student_email, version=version
    )
    target.mkdir(parents=True, exist_ok=True)

    stored: list[StoredFile] = []

    for original_name, data in files.items():
        name = safe_filename(original_name)
        path = target / name

        # Two uploads with the same name in one submission would clobber.
        counter = 1
        while path.exists():
            path = target / f"{PurePath(name).stem}_{counter}{PurePath(name).suffix}"
            counter += 1

        path.write_bytes(data)

        stored.append(
            StoredFile(
                original_name=original_name,
                stored_path=str(path),
                size_bytes=len(data),
                sha256=hashlib.sha256(data).hexdigest(),
            )
        )

    return stored
