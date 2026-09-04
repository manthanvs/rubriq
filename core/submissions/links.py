"""Repository URLs, parsed and bound to a registered profile (decision #6).

The requirement is not "accept a URL". It is *"accept the URLs according to
the students' actual GitHub profiles, which are already shared with the
teachers"* — so the check is an ownership check, and the thing it checks
against is a profile the **faculty** recorded, not one the student typed
alongside the URL. A student who could supply both halves of a match is not
being checked.

Everything here is pure string work: no network, no database. Nothing in
RubriQ fetches a repository. The URL is an artifact of the submission —
recorded, shown, exported — and evidence still has to be in the document,
because a model cannot cite a span from code it never saw.

Parsing is deliberately generous about *shape* and strict about *owner*. A
student pasting the URL from their browser's address bar, from a "clone"
button, or with a branch path attached should all work; a URL owned by
somebody else should not, however it is spelled.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from urllib.parse import unquote, urlsplit

from core.errors import ValidationError

#: GitHub's own rules: alphanumerics and single hyphens, 1–39 characters, and
#: it may not start or end with a hyphen.
USERNAME = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9]|-(?=[A-Za-z0-9])){0,38}$")

#: Repository names are laxer — letters, digits, dot, hyphen, underscore.
REPO = re.compile(r"^[A-Za-z0-9._-]{1,100}$")

#: Only GitHub. Decision #6 says GitHub profiles, and accepting arbitrary hosts
#: would mean accepting a URL nobody can check an owner against.
ALLOWED_HOSTS = frozenset({"github.com", "www.github.com"})

#: Path segments that follow ``owner/repo`` and introduce a ref or a view.
_REF_SEGMENTS = frozenset({"tree", "blob", "commit", "commits", "releases", "pull"})


@dataclass(frozen=True, slots=True)
class GitHubRef:
    """One parsed repository URL."""

    url: str
    """Exactly what the student typed."""

    owner: str
    repo: str
    ref: str | None

    @property
    def normalised_url(self) -> str:
        """The canonical ``https://github.com/<owner>/<repo>`` form.

        Stored alongside the raw string so two spellings of one repository
        compare equal without re-parsing either.
        """
        return f"https://github.com/{self.owner}/{self.repo}"

    @property
    def label(self) -> str:
        return f"{self.owner}/{self.repo}"


def _strip_credentials(netloc: str) -> str:
    """Drop any ``user:pass@`` prefix before looking at the host.

    ``https://github.com@evil.example/a/b`` has host ``evil.example``, and a
    naive "does it contain github.com" check would wave it through.
    """
    return netloc.rsplit("@", 1)[-1]


def parse_github_url(raw: str) -> GitHubRef:
    """Parse a GitHub repository URL, or explain why it is not one.

    Accepts the shapes a student actually has to hand:

    * ``https://github.com/owner/repo``
    * ``github.com/owner/repo`` — no scheme, as copied from a slide
    * ``https://github.com/owner/repo.git`` — the clone URL
    * ``git@github.com:owner/repo.git`` — the SSH clone URL
    * ``https://github.com/owner/repo/tree/main/docs`` — a deep link

    and rejects anything that is not one repository on GitHub.
    """
    text = (raw or "").strip()
    if not text:
        raise ValidationError("Enter a repository URL, or leave the field empty.")

    # git@github.com:owner/repo.git — rewrite to something urlsplit understands.
    ssh = re.match(r"^git@([^:]+):(.+)$", text)
    if ssh:
        text = f"https://{ssh.group(1)}/{ssh.group(2)}"

    if "://" not in text:
        text = f"https://{text}"

    parts = urlsplit(text)
    host = _strip_credentials(parts.netloc).lower()

    if host not in ALLOWED_HOSTS:
        raise ValidationError(
            f"Only github.com links are accepted — this one points at "
            f"{host or 'nowhere'}."
        )

    segments = [unquote(s) for s in parts.path.split("/") if s]
    if len(segments) < 2:
        raise ValidationError(
            "That is a GitHub link but not a repository — it needs to look "
            "like https://github.com/<owner>/<repository>."
        )

    owner, repo = segments[0], segments[1]
    if repo.lower().endswith(".git"):
        repo = repo[: -len(".git")]

    if not USERNAME.match(owner):
        raise ValidationError(f"'{owner}' is not a valid GitHub account name.")
    if not REPO.match(repo):
        raise ValidationError(f"'{repo}' is not a valid repository name.")

    ref = None
    if len(segments) >= 4 and segments[2] in _REF_SEGMENTS:
        ref = segments[3]

    return GitHubRef(url=raw.strip(), owner=owner, repo=repo, ref=ref)


def matching_profile(ref: GitHubRef, profiles: dict[str, str | None]) -> str | None:
    """Which registered profile, if any, owns this repository.

    ``profiles`` maps an email to the GitHub username faculty recorded for that
    person. Returns the email whose username owns the repository, or ``None``.

    Comparison is case-insensitive because GitHub usernames are, and a student
    whose URL says ``Manthan-VS`` while the register says ``manthan-vs`` has
    submitted their own repository.
    """
    wanted = ref.owner.casefold()
    for email, username in profiles.items():
        if username and username.strip().casefold() == wanted:
            return email
    return None


def assert_owned(ref: GitHubRef, profiles: dict[str, str | None]) -> str:
    """Return the owning profile's email, or refuse the URL.

    The refusal messages distinguish the two cases on purpose. "Nobody has a
    profile on record" is an administrative problem the student cannot fix by
    editing the URL, and telling them to try a different link would waste
    everyone's time.
    """
    owned = matching_profile(ref, profiles)
    if owned is not None:
        return owned

    known = sorted({u.strip() for u in profiles.values() if u and u.strip()})

    if not known:
        raise ValidationError(
            "No GitHub account is on record for you yet. Ask your guide to add "
            "it on the Subjects page, then submit the link again."
        )

    accounts = ", ".join(known)
    raise ValidationError(
        f"That repository belongs to '{ref.owner}', which is not an account on "
        f"record for this submission. Accepted: {accounts}."
    )
