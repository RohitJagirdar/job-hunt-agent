import unittest
from types import SimpleNamespace
from unittest.mock import patch

from app.schemas import ParsedJob, RecommendationBatch, ResumeProfile
from app.services import llm
from app.services.job_filters import is_tech_title, listing_key


def settings(**overrides):
    values = dict(
        anthropic_api_key="a-key",
        gemini_api_key="g-key",
        llm_provider="auto",
        anthropic_profile_model="profile-model",
        anthropic_scoring_model="scoring-model",
        gemini_model="gemini-model",
        llm_timeout_seconds=5.0,
    )
    values.update(overrides)
    return SimpleNamespace(**values)


PROFILE = ResumeProfile(
    profile_summary="Frontend engineer",
    skills=["React"],
    years_experience=2,
    seniority="Early career",
    target_roles=["Frontend Engineer"],
    achievement_highlights=[],
)


def job(job_id: int) -> SimpleNamespace:
    return SimpleNamespace(
        id=job_id, role_title="Engineer", company="Co", region="India", location="Pune", description="Build things."
    )


def recommendation(job_id: int) -> dict:
    return {
        "job_id": job_id,
        "match_score": 90,
        "match_summary": "Good fit.",
        "matched_skills": ["React"],
        "skill_gaps": [],
        "outreach_pitch": "Hello.",
    }


class RedactionTests(unittest.TestCase):
    def test_date_ranges_survive_but_phone_numbers_do_not(self) -> None:
        text = "Acme 2019 - 2021 and Beta 2021-2023. Call +1 (415) 555-0132 or 98765 43210."
        redacted = llm._redact_contact_info(text)
        self.assertIn("2019 - 2021", redacted)
        self.assertIn("2021-2023", redacted)
        self.assertNotIn("415", redacted)
        self.assertNotIn("98765", redacted)

    def test_email_and_profile_links_are_removed(self) -> None:
        redacted = llm._redact_contact_info("me@example.com https://www.linkedin.com/in/someone github.com/someone")
        self.assertNotIn("example.com", redacted)
        self.assertNotIn("someone", redacted)

    def test_name_line_is_removed_only_when_it_looks_like_a_name(self) -> None:
        self.assertTrue(llm._redact_name_line("Jane Q. Doe\nReact developer").startswith("[name removed]"))
        self.assertEqual(llm._redact_name_line("Summary of experience\nx"), "Summary of experience\nx")
        self.assertEqual(llm._redact_name_line("Software Engineer, 5 years\nx"), "Software Engineer, 5 years\nx")


class ProviderTests(unittest.TestCase):
    def test_no_keys_raises_not_configured(self) -> None:
        with patch("app.services.llm.get_settings", return_value=settings(anthropic_api_key=None, gemini_api_key=None)):
            with self.assertRaises(llm.LLMNotConfiguredError):
                llm.generate_structured("x", ParsedJob)
            self.assertFalse(llm.llm_configured())

    def test_claude_is_used_first_with_the_right_model(self) -> None:
        parsed = SimpleNamespace(parsed_output=RecommendationBatch(recommendations=[]), stop_reason="end_turn")
        with (
            patch("app.services.llm.get_settings", return_value=settings()),
            patch("app.services.llm.anthropic.Anthropic") as client,
            patch("app.services.llm.gemini.generate_json") as gemini_call,
        ):
            client.return_value.messages.parse.return_value = parsed
            llm.generate_structured("prompt", RecommendationBatch, scoring=True)
        self.assertEqual(client.return_value.messages.parse.call_args.kwargs["model"], "scoring-model")
        self.assertIs(client.return_value.messages.parse.call_args.kwargs["output_format"], RecommendationBatch)
        gemini_call.assert_not_called()

    def test_gemini_is_the_fallback_when_claude_fails_or_refuses(self) -> None:
        refusal = SimpleNamespace(parsed_output=None, stop_reason="refusal")
        for claude_outcome in (RuntimeError("overloaded"), refusal):
            with (
                patch("app.services.llm.get_settings", return_value=settings()),
                patch("app.services.llm.anthropic.Anthropic") as client,
                patch("app.services.llm.gemini.generate_json", return_value={"recommendations": []}) as gemini_call,
            ):
                if isinstance(claude_outcome, Exception):
                    client.return_value.messages.parse.side_effect = claude_outcome
                else:
                    client.return_value.messages.parse.return_value = claude_outcome
                result = llm.generate_structured("prompt", RecommendationBatch)
            self.assertEqual(result.recommendations, [])
            gemini_call.assert_called_once()

    def test_all_providers_failing_raises_llm_error(self) -> None:
        with (
            patch("app.services.llm.get_settings", return_value=settings()),
            patch("app.services.llm.anthropic.Anthropic") as client,
            patch("app.services.llm.gemini.generate_json", side_effect=RuntimeError("down")),
        ):
            client.return_value.messages.parse.side_effect = RuntimeError("also down")
            with self.assertRaisesRegex(llm.LLMError, "anthropic.*gemini"):
                llm.generate_structured("prompt", RecommendationBatch)

    def test_single_provider_setting_disables_fallback(self) -> None:
        with (
            patch("app.services.llm.get_settings", return_value=settings(llm_provider="anthropic")),
            patch("app.services.llm.anthropic.Anthropic") as client,
            patch("app.services.llm.gemini.generate_json") as gemini_call,
        ):
            client.return_value.messages.parse.side_effect = RuntimeError("down")
            with self.assertRaises(llm.LLMError):
                llm.generate_structured("prompt", RecommendationBatch)
        gemini_call.assert_not_called()


class RecommendJobsTests(unittest.TestCase):
    def test_failed_batch_is_reported_and_other_batches_survive(self) -> None:
        jobs = [job(i) for i in range(1, 14)]  # batches of 12 and 1

        def fake_generate(prompt, schema, scoring=False):
            if '"job_id": 13' in prompt:
                raise llm.LLMError("boom")
            return RecommendationBatch.model_validate(
                {"recommendations": [recommendation(i) for i in range(1, 13)] + [recommendation(99), recommendation(1)]}
            )

        errors: list[str] = []
        with patch("app.services.llm.generate_structured", side_effect=fake_generate):
            result = llm.recommend_jobs(PROFILE, jobs, errors)
            with self.assertRaises(llm.LLMError):
                llm.recommend_jobs(PROFILE, jobs)
        self.assertEqual([item.job_id for item in result.recommendations], list(range(1, 13)))  # no unknown/duplicate ids
        self.assertEqual(len(errors), 1)


class JobFilterTests(unittest.TestCase):
    def test_titles(self) -> None:
        for title in ("Senior Software Engineer", "Front-End Developer", "Data Scientist", "SRE", "QA Analyst"):
            self.assertTrue(is_tech_title(title), title)
        for title in ("Data Entry Clerk", "Sales Manager", "Squad Leader", "Qatar Country Manager", "Database Admin Assistant"):
            self.assertFalse(is_tech_title(title), title)

    def test_listing_key_ignores_case_and_punctuation(self) -> None:
        self.assertEqual(listing_key("Acme, Inc.", "Software Engineer", "Pune"), listing_key("ACME Inc", "software-engineer", "pune"))


if __name__ == "__main__":
    unittest.main()
