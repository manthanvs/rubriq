"""The Phase 5a exit criterion, and invariants #8 and #10.

*"Exit: guard correctly rejects fabricated evidence on a fixture, with no
LangGraph installed yet."* :class:`TestExitCriterion` is that, end to end
through the public function.

:class:`TestIdentityNeverLeaves` is fix item 5's third proof: a fixture whose
text contains the PRN pattern and the student's name, asserting neither
appears in the outgoing prompt. It inspects what the provider was actually
handed rather than trusting the scrubber in isolation.
"""

from __future__ import annotations

import json
from decimal import Decimal

import pytest

from core.ai.identity import PLACEHOLDER, assert_scrubbed, scrub_identity
from core.ai.provider import (
    AIUnavailable,
    StubProvider,
    build_provider,
    evaluate_submission,
)
from core.ai.schemas import AIResponseError
from core.config import Settings
from core.rubrics.dto import CriterionDTO, RubricDTO
from core.scoring.enums import Verdict

SUBMISSION = """\
Mini Project Synopsis

1. Problem statement
Faculty currently mark project reviews from memory against a rubric that
students never see before they submit. Marks vary between reviewers.

2. Objectives
- Publish a rubric per milestone before submission opens.
- Produce an evidence-backed estimated score sheet that faculty approve.
"""


def rubric() -> RubricDTO:
    return RubricDTO(
        id=1,
        milestone_id=1,
        version=1,
        published_at=None,
        published_by=None,
        criteria=(
            CriterionDTO(
                id=1,
                code="C1",
                title="Problem statement",
                description="Is the problem stated?",
                weight=Decimal("60"),
                max_score=Decimal("10"),
                expected_evidence="A stated problem and its consequence.",
                is_mandatory=True,
                order_index=1,
            ),
            CriterionDTO(
                id=2,
                code="C2",
                title="Objectives",
                description=None,
                weight=Decimal("40"),
                max_score=Decimal("10"),
                expected_evidence="At least two measurable objectives.",
                is_mandatory=False,
                order_index=2,
            ),
        ),
    )


def model_response(*, c1_evidence: str, c2_evidence: str) -> str:
    return json.dumps(
        {
            "criteria": [
                {
                    "code": "C1",
                    "verdict": "FOLLOWED",
                    "score": 8,
                    "max_score": 10,
                    "confidence": 0.92,
                    "evidence": c1_evidence,
                    "rationale": "The problem is stated with its consequence.",
                },
                {
                    "code": "C2",
                    "verdict": "PARTIAL",
                    "score": 6,
                    "max_score": 10,
                    "confidence": 0.7,
                    "evidence": c2_evidence,
                    "rationale": "Objectives are listed but not measurable.",
                },
            ],
            "overall_observations": ["Well structured."],
            "missing_items": ["No testing section."],
        }
    )


class RecordingProvider(StubProvider):
    """A stub that remembers what it was asked, so tests can inspect it."""

    name = "recording"

    def __init__(self, response: str) -> None:
        super().__init__(response)
        self.system: str = ""
        self.user: str = ""

    def complete(self, *, system: str, user: str) -> str:
        self.system = system
        self.user = user
        return super().complete(system=system, user=user)


class TestExitCriterion:
    """Fabricated evidence is rejected, end to end, with no LangGraph."""

    def test_the_5a_path_does_not_depend_on_langgraph(self) -> None:
        """§10: the graph is "an upgrade to an already-functioning path".

        Until Phase 5b this asserted langgraph was absent. It is installed now,
        so the assertion that still carries the original meaning is that the
        direct path does not reach for it: schemas, guards and identity import
        no graph machinery, and evaluate_submission runs without one.
        """
        import ast
        from pathlib import Path

        core_ai = Path(__file__).resolve().parents[3] / "core" / "ai"
        standalone = ("schemas.py", "guards.py", "identity.py")

        for name in standalone:
            tree = ast.parse((core_ai / name).read_text(encoding="utf-8"))
            imported = {
                (node.module or "").split(".")[0]
                for node in ast.walk(tree)
                if isinstance(node, ast.ImportFrom)
            } | {
                alias.name.split(".")[0]
                for node in ast.walk(tree)
                if isinstance(node, ast.Import)
                for alias in node.names
            }
            assert "langgraph" not in imported, f"{name} now depends on the graph"

    def test_a_fabricated_span_is_demoted_and_recorded(self) -> None:
        provider = StubProvider(
            model_response(
                c1_evidence="Marks vary between reviewers",
                c2_evidence="The system is deployed on a Kubernetes cluster.",
            )
        )

        result = evaluate_submission(
            rubric(), SUBMISSION, provider=provider, submission_ref="sub-1"
        )

        by_code = {c.code: c for c in result.criteria}

        assert by_code["C1"].verdict is Verdict.FOLLOWED
        assert by_code["C1"].score == Decimal("8")

        assert by_code["C2"].verdict is Verdict.NO_EVIDENCE
        assert by_code["C2"].score == 0

        assert len(result.rejections) == 1
        assert result.rejections[0].code == "C2"
        assert "Kubernetes" in result.rejections[0].span
        assert result.rejection_rate == 0.5

    def test_a_wholly_genuine_response_passes_untouched(self) -> None:
        provider = StubProvider(
            model_response(
                c1_evidence="Marks vary between reviewers",
                c2_evidence="Publish a rubric per milestone before submission opens",
            )
        )

        result = evaluate_submission(rubric(), SUBMISSION, provider=provider)

        assert result.rejections == ()
        assert all(c.verdict is not Verdict.NO_EVIDENCE for c in result.criteria)

    def test_the_raw_response_is_kept_verbatim(self) -> None:
        """§6.5: "Store raw_response verbatim whatever happens"."""
        raw = model_response(
            c1_evidence="Marks vary between reviewers",
            c2_evidence="Invented entirely.",
        )
        result = evaluate_submission(rubric(), SUBMISSION, provider=StubProvider(raw))

        assert result.raw_response == raw

    def test_the_result_is_stamped_for_reproducibility(self) -> None:
        """§6.5: tag every Evaluation with prompt_version and graph_version."""
        result = evaluate_submission(
            rubric(),
            SUBMISSION,
            provider=StubProvider(
                model_response(
                    c1_evidence="Marks vary between reviewers",
                    c2_evidence="Publish a rubric per milestone",
                )
            ),
        )

        assert result.prompt_version == "eval-v1"
        assert result.graph_version == "direct-5a"
        assert result.model_name


class TestIdentityNeverLeaves:
    """Invariant #8, checked on the prompt the provider actually received."""

    IDENTIFIED = (
        "Mini Project Synopsis\n"
        "Submitted by Manthan Sankpal (PRN 125M1H064)\n"
        "Contact: manthan.sankpal@pccoepune.org\n\n"
        "Faculty currently mark project reviews from memory.\n"
        "Marks vary between reviewers.\n"
    )

    def test_neither_the_name_nor_the_prn_reaches_the_prompt(self) -> None:
        provider = RecordingProvider(
            model_response(
                c1_evidence="Marks vary between reviewers",
                c2_evidence="Faculty currently mark project reviews from memory",
            )
        )

        evaluate_submission(
            rubric(),
            self.IDENTIFIED,
            provider=provider,
            student_name="Manthan Sankpal",
            student_prn="125M1H064",
            student_email="manthan.sankpal@pccoepune.org",
        )

        sent = provider.user

        assert "Manthan" not in sent
        assert "Sankpal" not in sent
        assert "125M1H064" not in sent
        assert "manthan.sankpal@pccoepune.org" not in sent
        assert PLACEHOLDER in sent

    def test_the_rest_of_the_submission_survives(self) -> None:
        """Over-eager redaction that shredded the document would be useless."""
        scrubbed, report = scrub_identity(
            self.IDENTIFIED,
            name="Manthan Sankpal",
            prn="125M1H064",
            email="manthan.sankpal@pccoepune.org",
        )

        assert "Marks vary between reviewers" in scrubbed
        assert report.redactions > 0

    def test_an_unnamed_students_prn_is_caught_by_shape(self) -> None:
        """A group submission carries co-authors the caller never named."""
        scrubbed, _ = scrub_identity("Co-author: 125M1H099 contributed §3.")

        assert "125M1H099" not in scrubbed

    def test_a_stray_email_is_caught_by_shape(self) -> None:
        scrubbed, _ = scrub_identity("Reach us at team.four@pccoepune.org today.")

        assert "@pccoepune.org" not in scrubbed

    def test_the_assertion_fires_if_scrubbing_missed_something(self) -> None:
        """The belt for the braces: a scrubber bug must fail loudly."""
        with pytest.raises(AssertionError, match="invariant #8"):
            assert_scrubbed("Submitted by Manthan Sankpal", name="Manthan Sankpal")

    def test_the_assertion_catches_a_prn_shape_nobody_declared(self) -> None:
        with pytest.raises(AssertionError):
            assert_scrubbed("Roll number 125M1H064 appears here.")

    def test_clean_text_passes_the_assertion(self) -> None:
        assert_scrubbed("Faculty currently mark project reviews from memory.")


class TestOfflineDegradation:
    """Invariant #10 and fix item 9: failure is a message, not a traceback."""

    def test_no_configured_provider_says_what_still_works(self) -> None:
        with pytest.raises(AIUnavailable) as excinfo:
            build_provider(Settings(database_url="sqlite://"))

        message = str(excinfo.value)
        assert "Manual scoring" in message
        assert "secrets.toml" in message

    def test_an_unknown_provider_name_is_refused_clearly(self) -> None:
        settings = Settings(
            database_url="sqlite://", llm_provider="hal9000", llm_api_key="x"
        )

        with pytest.raises(AIUnavailable, match="Supported: gemini, groq"):
            build_provider(settings)

    def test_a_provider_that_raises_becomes_ai_unavailable(self) -> None:
        """Fix item 9: the app must render with the provider stubbed to raise."""
        provider = StubProvider(error=TimeoutError("connection reset"))

        with pytest.raises(AIUnavailable, match="connection reset"):
            evaluate_submission(rubric(), SUBMISSION, provider=provider)

    def test_a_malformed_response_is_an_ai_response_error(self) -> None:
        provider = StubProvider("I am unable to assist with that request.")

        with pytest.raises(AIResponseError):
            evaluate_submission(rubric(), SUBMISSION, provider=provider)

    def test_an_empty_rubric_is_refused_before_any_call(self) -> None:
        empty = RubricDTO(
            id=1,
            milestone_id=1,
            version=1,
            published_at=None,
            published_by=None,
            criteria=(),
        )
        provider = RecordingProvider("{}")

        with pytest.raises(AIResponseError):
            evaluate_submission(empty, SUBMISSION, provider=provider)

        assert provider.user == "", "no tokens should have been spent"


class TestPromptShape:
    def test_the_rubric_reaches_the_model(self) -> None:
        provider = RecordingProvider(
            model_response(
                c1_evidence="Marks vary between reviewers",
                c2_evidence="Publish a rubric per milestone",
            )
        )

        evaluate_submission(rubric(), SUBMISSION, provider=provider)

        assert "C1" in provider.user
        assert "Problem statement" in provider.user
        assert "A stated problem and its consequence." in provider.user
        assert "mandatory" in provider.user.lower()

    def test_the_system_prompt_forbids_invention(self) -> None:
        provider = RecordingProvider(
            model_response(
                c1_evidence="Marks vary between reviewers",
                c2_evidence="Publish a rubric per milestone",
            )
        )

        evaluate_submission(rubric(), SUBMISSION, provider=provider)

        assert "VERBATIM" in provider.system
        assert "NO_EVIDENCE" in provider.system
        assert "checked against the submission" in provider.system


class TestOpenAICompatibleGateways:
    """OpenRouter and NVIDIA reach the same weights through the same API.

    No live call: what matters is the request shape, because that is what
    decides whether §6.5's JSON contract is enforced by the API or only
    requested by the prompt.
    """

    @staticmethod
    def _settings(provider: str = "openrouter", model: str = "") -> Settings:
        return Settings(
            database_url="sqlite://",
            llm_provider=provider,
            llm_api_key="test-key",
            llm_model=model,
        )

    def _fake_openai(self, monkeypatch, *, raises: Exception | None = None):
        """Intercept the lazily imported client and record what it was sent.

        Construction and completion are recorded separately — counting them
        together is how the first version of this double never fired its
        simulated failure.
        """
        import openai

        class Recorder:
            init: list[dict] = []
            attempts: list[dict] = []

        class _Completions:
            def create(self, **kwargs):
                Recorder.attempts.append(kwargs)
                if raises is not None and len(Recorder.attempts) == 1:
                    raise raises
                message = type("M", (), {"content": '{"criteria": []}'})()
                choice = type("C", (), {"message": message})()
                return type("R", (), {"choices": [choice]})()

        class _Client:
            def __init__(self, **kwargs):
                Recorder.init.append(kwargs)
                self.chat = type("Chat", (), {"completions": _Completions()})()

        Recorder.init, Recorder.attempts = [], []
        monkeypatch.setattr(openai, "OpenAI", _Client)
        return Recorder

    @pytest.mark.parametrize(
        ("provider", "base_url", "default_model"),
        [
            (
                "openrouter",
                "https://openrouter.ai/api/v1",
                "nvidia/nemotron-3-super-120b-a12b:free",
            ),
            (
                "nvidia",
                "https://integrate.api.nvidia.com/v1",
                "nvidia/nemotron-3-super-120b-a12b",
            ),
        ],
    )
    def test_each_gateway_is_selectable_and_has_its_own_defaults(
        self, provider, base_url, default_model, monkeypatch
    ) -> None:
        """The ``:free`` suffix is OpenRouter's, not NVIDIA's. Confusing the
        two is a 404 at the worst moment."""
        built = build_provider(self._settings(provider))
        assert built.name == provider
        assert built.model == default_model

        rec = self._fake_openai(monkeypatch)
        built.complete(system="S", user="U")
        assert rec.init[0]["base_url"] == base_url

    def test_the_model_is_overridable_from_secrets(self) -> None:
        built = build_provider(
            self._settings("openrouter", "nvidia/nemotron-3-ultra-550b-a55b:free")
        )
        assert built.model == "nvidia/nemotron-3-ultra-550b-a55b:free"

    def test_it_asks_the_api_to_enforce_json(self, monkeypatch) -> None:
        rec = self._fake_openai(monkeypatch)
        build_provider(self._settings()).complete(system="S", user="U")
        assert rec.attempts[0]["response_format"] == {"type": "json_object"}

    def test_both_messages_are_sent_in_order(self, monkeypatch) -> None:
        rec = self._fake_openai(monkeypatch)
        build_provider(self._settings()).complete(system="S", user="U")
        assert [m["role"] for m in rec.attempts[0]["messages"]] == ["system", "user"]
        assert [m["content"] for m in rec.attempts[0]["messages"]] == ["S", "U"]

    def test_a_gateway_that_rejects_response_format_is_retried_without_it(
        self, monkeypatch
    ) -> None:
        """Not every endpoint ignores what it cannot honour; some 400 on it."""
        rejection = ValueError("400: unsupported parameter: response_format")
        rec = self._fake_openai(monkeypatch, raises=rejection)

        assert build_provider(self._settings()).complete(system="S", user="U")

        assert len(rec.attempts) == 2, "should have retried exactly once"
        assert "response_format" in rec.attempts[0]
        assert "response_format" not in rec.attempts[1]

    def test_an_unrelated_failure_is_not_retried(self, monkeypatch) -> None:
        """The retry is narrow: an outage must still look like an outage."""
        rec = self._fake_openai(monkeypatch, raises=TimeoutError("gateway timeout"))

        with pytest.raises(AIUnavailable, match="gateway timeout"):
            build_provider(self._settings()).complete(system="S", user="U")

        assert len(rec.attempts) == 1, "must not retry"
