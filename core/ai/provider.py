"""The public face of ``core/ai`` — §6.1.

Everything outside this package calls plain functions here. No caller sees a
prompt, an SDK, or (from Phase 5b) a graph. Phase 5a implements one of the
three §6.1 functions with a direct call and no orchestration; the signature is
the one the graph will keep.

**Invariant #10 lives here too.** If no provider is configured or the call
fails, :class:`AIUnavailable` is raised with a message a page can render. The
deterministic half of RubriQ — manual scoring, penalties, exports — is
unaffected, and the caller is expected to say so rather than show a traceback.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from core.ai.guards import EvidenceRejection, apply_guard
from core.ai.identity import assert_scrubbed, scrub_identity
from core.ai.prompts.evaluation_v1 import (
    PROMPT_VERSION,
    SYSTEM_PROMPT,
    build_user_prompt,
)
from core.ai.schemas import AIResponseError, CriterionResult, parse_response
from core.config import Settings
from core.errors import RubriQError
from core.rubrics.dto import RubricDTO

#: Bumped when the graph changes, in Phase 5b. Stamped alongside
#: ``prompt_version`` so a result is reproducible (§6.5).
GRAPH_VERSION = "direct-5a"


class AIUnavailable(RubriQError):
    """No provider configured, or the provider could not be reached."""


class LLMProvider(Protocol):
    """The whole surface an LLM needs to present.

    One method. Keeping it this small is what makes Gemini, Groq and a test
    stub interchangeable, and what stops an SDK type leaking past this module
    (§3: "never import an SDK outside this module").
    """

    name: str

    def complete(self, *, system: str, user: str) -> str: ...


@dataclass(frozen=True, slots=True)
class EvaluationResult:
    """What an evaluation produced, before anything is persisted.

    Carries the raw response verbatim (§6.5: *"Store raw_response verbatim
    whatever happens"*) and the rejections, which are the report's empirical
    result rather than incidental logging.
    """

    criteria: tuple[CriterionResult, ...]
    rejections: tuple[EvidenceRejection, ...]
    overall_observations: tuple[str, ...]
    missing_items: tuple[str, ...]
    raw_response: str
    model_name: str
    prompt_version: str = PROMPT_VERSION
    graph_version: str = GRAPH_VERSION

    @property
    def rejection_rate(self) -> float:
        if not self.criteria:
            return 0.0
        return len(self.rejections) / len(self.criteria)


# -- providers -----------------------------------------------------------


class StubProvider:
    """Returns a canned response. Used by the tests, and by ``make seed``.

    Its existence is also fix item 9's proof: the whole application must render
    with the provider stubbed, including stubbed to raise.
    """

    name = "stub"

    def __init__(self, response: str = "", error: Exception | None = None) -> None:
        self._response = response
        self._error = error

    def complete(self, *, system: str, user: str) -> str:
        if self._error is not None:
            raise self._error
        return self._response


def build_provider(settings: Settings) -> LLMProvider:
    """Construct the configured provider, or refuse clearly.

    The SDK import is inside the branch so an uninstalled provider is a
    readable message rather than an ImportError at startup — and so the rest
    of RubriQ runs with neither SDK present.
    """
    if not settings.has_llm:
        raise AIUnavailable(
            "No AI provider is configured. Add [llm] provider and api_key to "
            ".streamlit/secrets.toml. Manual scoring, penalties and exports "
            "work without it."
        )

    provider = (settings.llm_provider or "").strip().lower()

    if provider == "gemini":
        return _GeminiProvider(settings.llm_api_key or "")
    if provider == "groq":
        return _GroqProvider(settings.llm_api_key or "")

    raise AIUnavailable(f"Unknown AI provider {provider!r}. Supported: gemini, groq.")


class _GeminiProvider:
    """Google Gemini. Decision #4 is still open; both are implemented."""

    name = "gemini"
    model = "gemini-2.0-flash"

    def __init__(self, api_key: str) -> None:
        self._api_key = api_key

    def complete(self, *, system: str, user: str) -> str:
        try:
            from google import genai
            from google.genai import types
        except ImportError as exc:
            raise AIUnavailable(
                "The Gemini provider needs google-genai installed."
            ) from exc

        try:
            client = genai.Client(api_key=self._api_key)
            response = client.models.generate_content(
                model=self.model,
                contents=user,
                config=types.GenerateContentConfig(
                    system_instruction=system,
                    response_mime_type="application/json",
                ),
            )
            return response.text or ""
        except Exception as exc:
            raise AIUnavailable(f"Gemini could not be reached: {exc}") from exc


class _GroqProvider:
    """Groq. Decision #4 is still open; both are implemented."""

    name = "groq"
    model = "llama-3.3-70b-versatile"

    def __init__(self, api_key: str) -> None:
        self._api_key = api_key

    def complete(self, *, system: str, user: str) -> str:
        try:
            from groq import Groq
        except ImportError as exc:
            raise AIUnavailable("The Groq provider needs groq installed.") from exc

        try:
            client = Groq(api_key=self._api_key)
            completion = client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                response_format={"type": "json_object"},
            )
            return completion.choices[0].message.content or ""
        except Exception as exc:
            raise AIUnavailable(f"Groq could not be reached: {exc}") from exc


# -- the public function -------------------------------------------------


def evaluate_submission(
    rubric: RubricDTO,
    text: str,
    *,
    provider: LLMProvider,
    student_name: str = "",
    student_prn: str = "",
    student_email: str = "",
    submission_ref: str = "",
) -> EvaluationResult:
    """Evaluate one submission against one rubric.

    The order is the security model, and it is the same order §6.3's graph will
    use once it exists:

    1. scrub identity, then **assert** it is gone (invariant #8);
    2. build the prompt and call the model;
    3. parse and validate against the schema;
    4. guard every span against the submission text — no bypass;
    5. return, with rejections attached.

    Step 4 is the only route by which a result becomes persistable.
    """
    if not rubric.criteria:
        raise AIResponseError("The rubric has no criteria to evaluate.")

    scrubbed, _report = scrub_identity(
        text, name=student_name, prn=student_prn, email=student_email
    )
    assert_scrubbed(scrubbed, name=student_name, prn=student_prn, email=student_email)

    user_prompt = build_user_prompt(rubric, scrubbed)

    try:
        raw = provider.complete(system=SYSTEM_PROMPT, user=user_prompt)
    except AIUnavailable:
        raise
    except Exception as exc:
        raise AIUnavailable(f"The AI provider failed: {exc}") from exc

    response = parse_response(raw)

    # Guarded against the *scrubbed* text, which is what the model was shown.
    # Checking against the original would let a span quoting a redacted name
    # pass, and the student's feedback would then quote text the model never saw.
    outcome = apply_guard(
        list(response.criteria), scrubbed, submission_ref=submission_ref
    )

    return EvaluationResult(
        criteria=outcome.results,
        rejections=outcome.rejections,
        overall_observations=tuple(response.overall_observations),
        missing_items=tuple(response.missing_items),
        raw_response=raw,
        model_name=getattr(provider, "model", provider.name),
    )
