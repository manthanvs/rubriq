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

from collections.abc import Iterator
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

#: The direct, graph-free path from Phase 5a. Kept because §10 says the graph
#: is "an upgrade to an already-functioning path, not a prerequisite" — if 5b
#: ever misbehaves, evaluate_submission still works.
GRAPH_VERSION = "direct-5a"

#: What ``stream_evaluation`` stamps. Imported lazily below so this module
#: still imports with no langgraph installed.
GRAPH_VERSION_GRAPH = "eval-graph-v1"


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

    #: Fix item 9: a run that could not complete is surfaced as FAILED with a
    #: reason, not swallowed as a silent zero.
    failed: bool = False
    failure_reason: str = ""

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
        return _GeminiProvider(settings.llm_api_key or "", settings.llm_model or "")
    if provider == "groq":
        return _GroqProvider(settings.llm_api_key or "", settings.llm_model or "")

    raise AIUnavailable(f"Unknown AI provider {provider!r}. Supported: gemini, groq.")


class _GeminiProvider:
    """Google Gemini — decision #4.

    The model is overridable from secrets because Google retires them on its
    own schedule: ``gemini-2.0-flash``, which CLAUDE.md originally named, was
    already returning 404 with a pointer to its successor by the time this was
    wired up. A hardcoded model is a demo that stops working without anyone
    touching the code.
    """

    name = "gemini"
    DEFAULT_MODEL = "gemini-3.6-flash"

    def __init__(self, api_key: str, model: str = "") -> None:
        self._api_key = api_key
        self.model = model or self.DEFAULT_MODEL

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
    """Groq — the other half of decision #4, kept implemented and reversible."""

    name = "groq"
    DEFAULT_MODEL = "llama-3.3-70b-versatile"

    def __init__(self, api_key: str, model: str = "") -> None:
        self._api_key = api_key
        self.model = model or self.DEFAULT_MODEL

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


# -- the graph path (Phase 5b) -------------------------------------------


def _rubric_payload(rubric: RubricDTO) -> dict:
    """Serialise a rubric for the graph state.

    Decimals become strings: the checkpointer writes state to SQLite as JSON,
    and a float here would reintroduce exactly the drift fix item 1 spent a
    column type avoiding.
    """
    return {
        "id": rubric.id,
        "milestone_id": rubric.milestone_id,
        "version": rubric.version,
        "criteria": [
            {
                "id": c.id,
                "code": c.code,
                "title": c.title,
                "description": c.description,
                "weight": str(c.weight),
                "max_score": str(c.max_score),
                "expected_evidence": c.expected_evidence,
                "is_mandatory": c.is_mandatory,
                "order_index": c.order_index,
            }
            for c in rubric.criteria
        ],
    }


def _result_from_state(state: dict, provider: LLMProvider) -> EvaluationResult:
    """Rebuild the public result from the graph's final state."""
    criteria = tuple(
        CriterionResult.model_validate(item) for item in state.get("parsed", [])
    )
    rejections = tuple(
        EvidenceRejection(
            code=r["code"],
            span=r["span"],
            match_score=r["match_score"],
            reason=r["reason"],
        )
        for r in state.get("rejections", [])
    )

    return EvaluationResult(
        criteria=criteria,
        rejections=rejections,
        overall_observations=tuple(state.get("observations", [])),
        missing_items=tuple(state.get("missing_items", [])),
        raw_response="\n---\n".join(state.get("raw_responses", [])),
        model_name=getattr(provider, "model", provider.name),
        graph_version=GRAPH_VERSION_GRAPH,
        failed=state.get("status") == "FAILED",
        failure_reason=state.get("last_error", "")
        if state.get("status") == "FAILED"
        else "",
    )


def stream_evaluation(
    rubric: RubricDTO,
    text: str,
    *,
    provider: LLMProvider,
    submission_id: int,
    evaluation_version: int,
    student_name: str = "",
    student_prn: str = "",
    student_email: str = "",
    checkpoint_path=None,
) -> Iterator[tuple[str, EvaluationResult | None]]:
    """Run the graph, yielding ``(node_name, result_or_None)`` as it goes.

    §6.6: *"``stream_evaluation`` is a generator in ``core/ai/`` that yields
    plain strings. Streamlit still never touches a graph object."* The final
    yield carries the assembled result; every earlier one carries ``None`` and
    exists so the UI can show the machine thinking rather than a frozen spinner.

    Resumability is the point of the ``thread_id``: re-entering with the same
    ``evaluation_version`` after a browser refresh replays completed nodes from
    the checkpoint instead of calling the model again.
    """
    if not rubric.criteria:
        raise AIResponseError("The rubric has no criteria to evaluate.")

    from core.ai.checkpoint import checkpointer, thread_id
    from core.ai.graphs.evaluation import build_graph

    graph = build_graph(provider)
    tid = thread_id(submission_id, evaluation_version)

    initial: dict = {
        "rubric": _rubric_payload(rubric),
        "text": text,
        "submission_ref": tid,
        "student_name": student_name,
        "student_prn": student_prn,
        "student_email": student_email,
    }

    with checkpointer(checkpoint_path) as saver:
        compiled = graph.compile(checkpointer=saver)
        config = {"configurable": {"thread_id": tid}}

        # Resuming means passing None. Handing the initial state back in would
        # overwrite the checkpoint and replay every node — which is exactly the
        # duplicate-LLM-call the Phase 5b exit criterion forbids.
        already_started = bool(compiled.get_state(config).values)
        payload = None if already_started else initial

        for update in compiled.stream(payload, config=config, stream_mode="updates"):
            for node_name in update:
                yield node_name, None

        final = compiled.get_state(config).values
        yield "done", _result_from_state(final, provider)


class RetryingProvider:
    """Wraps a provider with bounded backoff — fix item 9.

    *"Bounded backoff on rate limits."* Bounded is the operative word: a demo
    that silently retries forever looks identical to one that has hung, so the
    attempts are capped and the last error is raised rather than swallowed.

    Only transient-looking failures are retried. A malformed request or a bad
    key will fail identically on the third attempt, so retrying it just makes
    the faculty member wait longer for the same message.
    """

    #: Substrings that suggest waiting would help.
    TRANSIENT = ("429", "rate", "timeout", "timed out", "unavailable", "503", "500")

    def __init__(
        self,
        inner: LLMProvider,
        *,
        attempts: int = 3,
        base_delay: float = 1.0,
        sleep=None,
    ) -> None:
        self._inner = inner
        self._attempts = max(1, attempts)
        self._base_delay = base_delay
        # Injectable so tests do not actually wait three seconds.
        self._sleep = sleep or __import__("time").sleep

    @property
    def name(self) -> str:
        return self._inner.name

    @property
    def model(self) -> str:
        return getattr(self._inner, "model", self._inner.name)

    def _is_transient(self, exc: Exception) -> bool:
        text = str(exc).lower()
        return any(marker in text for marker in self.TRANSIENT)

    def complete(self, *, system: str, user: str) -> str:
        last: Exception | None = None

        for attempt in range(1, self._attempts + 1):
            try:
                return self._inner.complete(system=system, user=user)
            except Exception as exc:
                last = exc
                if attempt == self._attempts or not self._is_transient(exc):
                    raise
                # Exponential, so a rate limit gets a genuinely longer pause
                # on the second try rather than the same one again.
                self._sleep(self._base_delay * (2 ** (attempt - 1)))

        raise last  # unreachable, but keeps the type checker honest
