import json
import re
import unittest
from io import BytesIO
from types import SimpleNamespace
from unittest.mock import Mock, patch

import fitz
from docx import Document

from app.schemas import ResumeProfile
from app.services.llm import parse_resume, recommend_jobs
from app.services.resume_parser import (
    MAX_RESUME_BYTES,
    MAX_RESUME_TEXT_LENGTH,
    ResumeExtractionError,
    extract_resume_text,
)


RESUME_TEXT = (
    "Frontend engineer with two years of experience building React and TypeScript applications. "
    "Developed REST APIs in Python and FastAPI, improved page performance by 30 percent, and "
    "collaborated with product and design teams. Skills include React, TypeScript, Python, SQL, "
    "accessibility, testing, and Git. Seeking frontend and full-stack engineering roles."
)


class ResumeExtractionTests(unittest.TestCase):
    def test_extracts_utf8_text_and_applies_text_limit(self) -> None:
        extracted = extract_resume_text("resume.txt", RESUME_TEXT.encode("utf-8"))
        self.assertIn("Frontend engineer", extracted)
        long_text = ("resume skills experience " * (MAX_RESUME_TEXT_LENGTH // 20)).encode()
        self.assertEqual(len(extract_resume_text("resume.md", long_text)), MAX_RESUME_TEXT_LENGTH)

    def test_extracts_pdf_and_docx(self) -> None:
        pdf = fitz.open()
        pdf.new_page().insert_text((40, 40), RESUME_TEXT)
        pdf_bytes = pdf.tobytes()
        pdf.close()

        docx = Document()
        docx.add_paragraph(RESUME_TEXT)
        docx_bytes = BytesIO()
        docx.save(docx_bytes)

        self.assertIn("Frontend engineer", extract_resume_text("resume.pdf", pdf_bytes))
        self.assertIn("Frontend engineer", extract_resume_text("resume.docx", docx_bytes.getvalue()))

    def test_rejects_unsupported_oversized_and_unreadable_resumes(self) -> None:
        with self.assertRaisesRegex(ResumeExtractionError, "PDF, DOCX, TXT"):
            extract_resume_text("resume.exe", b"x" * 100)
        with self.assertRaisesRegex(ResumeExtractionError, "5 MB"):
            extract_resume_text("resume.txt", b"x" * (MAX_RESUME_BYTES + 1))
        with self.assertRaisesRegex(ResumeExtractionError, "enough text"):
            extract_resume_text("resume.txt", b"too short")


GEMINI_ONLY = SimpleNamespace(
    anthropic_api_key=None, gemini_api_key="test", llm_provider="auto", gemini_model="m",
    anthropic_profile_model="p", anthropic_scoring_model="s", llm_timeout_seconds=5.0,
)


class GeminiRecommendationTests(unittest.TestCase):
    def test_resume_parser_redacts_contact_details_before_gemini(self) -> None:
        profile_data = {
            "profile_summary": "Frontend engineer experienced in React and Python.",
            "skills": ["React", "Python"],
            "years_experience": 2,
            "seniority": "Early career",
            "target_roles": ["Frontend Engineer"],
            "achievement_highlights": ["Improved page performance by 30 percent."],
        }
        generate_content = Mock(return_value=SimpleNamespace(text=json.dumps(profile_data)))
        fake_client = SimpleNamespace(models=SimpleNamespace(generate_content=generate_content))
        with (
            patch("app.services.llm.get_settings", return_value=GEMINI_ONLY),
            patch("app.services.gemini.get_settings", return_value=GEMINI_ONLY),
            patch("app.services.gemini.genai.Client", return_value=fake_client),
        ):
            profile = parse_resume(
                f"{RESUME_TEXT} Email: candidate@example.com. Phone: +1 (415) 555-0132."
            )

        self.assertIsInstance(profile, ResumeProfile)
        prompt = generate_content.call_args.kwargs["contents"]
        self.assertNotIn("candidate@example.com", prompt)
        self.assertNotIn("415", prompt)

    def test_recommendations_are_batched_and_keep_job_ids(self) -> None:
        profile = ResumeProfile(
            profile_summary="Frontend engineer with React experience.",
            skills=["React", "TypeScript"],
            years_experience=2,
            seniority="Early career",
            target_roles=["Frontend Engineer"],
            achievement_highlights=[],
        )
        jobs = [
            SimpleNamespace(
                id=job_id,
                role_title=f"Engineer {job_id}",
                company=f"Company {job_id}",
                region="India",
                location="Bengaluru",
                description="Build React and TypeScript products.",
            )
            for job_id in range(1, 14)
        ]
        generated_ids: list[int] = []

        def generate_content(*, contents: str, **_: object) -> SimpleNamespace:
            ids = [int(value) for value in re.findall(r'"job_id":\s*(\d+)', contents)]
            generated_ids.extend(ids)
            return SimpleNamespace(
                text=json.dumps(
                    {
                        "recommendations": [
                            {
                                "job_id": job_id,
                                "match_score": 88,
                                "match_summary": "React fits the role.",
                                "matched_skills": ["React"],
                                "skill_gaps": ["Kubernetes"],
                                "outreach_pitch": "I have built React products.",
                            }
                            for job_id in ids
                        ]
                    }
                )
            )

        fake_client = SimpleNamespace(models=SimpleNamespace(generate_content=generate_content))
        with (
            patch("app.services.llm.get_settings", return_value=GEMINI_ONLY),
            patch("app.services.gemini.get_settings", return_value=GEMINI_ONLY),
            patch("app.services.gemini.genai.Client", return_value=fake_client),
        ):
            result = recommend_jobs(profile, jobs)

        self.assertEqual(len(result.recommendations), len(jobs))
        self.assertEqual(generated_ids, list(range(1, 14)))
        self.assertEqual([item.job_id for item in result.recommendations], list(range(1, 14)))


if __name__ == "__main__":
    unittest.main()
