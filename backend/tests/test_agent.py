import asyncio
from datetime import date
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base
from app.models import AgentRun, AgentSettings, AgentSource, CandidateProfile, Job
from app.schemas import AgentSourceCreate, JobRecommendation, RecommendationBatch
from app.services.agent import run_agent_once
from app.services.career_sources import fetch_source
from app.services.llm import LLMNotConfiguredError
from pydantic import ValidationError


class CareerSourceTests(unittest.TestCase):
    def test_rss_entries_are_normalized_and_relative_links_resolved(self) -> None:
        source = AgentSource(
            id=1,
            name="Example Company",
            source_type="rss",
            url="https://example.com/careers/feed.xml",
            region="India",
            enabled=True,
        )
        feed = b"""<?xml version="1.0"?>
        <rss><channel><item><title>Software Engineer</title>
        <link>/jobs/123</link><location>Tokyo, Japan</location>
        <description><![CDATA[<p>Build <strong>React</strong> products.</p>]]></description>
        </item></channel></rss>"""
        with patch("app.services.career_sources._download", new=AsyncMock(return_value=feed)):
            listing = asyncio.run(fetch_source(source))

        self.assertEqual(len(listing), 1)
        self.assertEqual(listing[0]["region"], "Japan")
        self.assertEqual(listing[0]["source_url"], "https://example.com/jobs/123")
        self.assertIn("React", listing[0]["description"])

    def test_source_url_must_match_supported_public_board(self) -> None:
        source = AgentSourceCreate(
            name="Example",
            source_type="greenhouse",
            url="https://boards.greenhouse.io/example",
            region="Japan",
        )
        self.assertEqual(source.region, "Japan")
        from app.services.career_sources import _source_identifier

        self.assertEqual(
            _source_identifier("https://api.lever.co/v0/postings/example?mode=json", "lever"),
            "example",
        )
        with self.assertRaises(ValidationError):
            AgentSourceCreate(
                name="Private",
                source_type="rss",
                url="https://127.0.0.1/jobs.xml",
                region="India",
            )
        with self.assertRaises(ValidationError):
            AgentSourceCreate(
                name="Fake board",
                source_type="greenhouse",
                url="https://example.com/jobs",
                region="India",
            )


class AgentRunTests(unittest.TestCase):
    def setUp(self) -> None:
        self.engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        Base.metadata.create_all(self.engine)
        self.session_factory = sessionmaker(bind=self.engine, expire_on_commit=False)
        db = self.session_factory()
        db.add(
            CandidateProfile(
                id=1,
                profile_json=(
                    '{"profile_summary":"Frontend engineer","skills":["React"],'
                    '"years_experience":2,"seniority":"Early career",'
                    '"target_roles":["Frontend Engineer"],"achievement_highlights":[]}'
                ),
            )
        )
        db.add(AgentSettings(id=1, interval_minutes=0, minimum_match_score=85))
        db.add(
            AgentSource(
                name="Example Company",
                source_type="rss",
                url="https://example.com/feed.xml",
                region="India",
                enabled=True,
            )
        )
        db.commit()
        db.close()
        self.session_patcher = patch("app.services.agent.SessionLocal", self.session_factory)
        self.session_patcher.start()
        # Never let a test reach a real LLM provider because the developer's .env has keys.
        self.llm_patcher = patch("app.services.agent.llm_configured", return_value=True)
        self.llm_patcher.start()

    def tearDown(self) -> None:
        self.llm_patcher.stop()
        self.session_patcher.stop()
        Base.metadata.drop_all(self.engine)
        self.engine.dispose()

    def test_run_saves_only_qualified_deduplicated_roles_and_syncs_them(self) -> None:
        listing = {
            "role_title": "Frontend Engineer",
            "company": "Example Company",
            "region": "India",
            "location": "Bengaluru",
            "description": "Build user-facing React and TypeScript products.",
            "source_url": "https://example.com/jobs/1",
        }
        recommendation = JobRecommendation(
            job_id=-1,
            match_score=92,
            match_summary="Your React experience matches the role.",
            matched_skills=["React"],
            skill_gaps=["Kubernetes"],
            outreach_pitch="I have built React products.",
        )
        with (
            patch(
                "app.services.agent.get_settings",
                return_value=SimpleNamespace(
                    gemini_api_key="test-key",
                    anthropic_api_key=None,
                    llm_provider="auto",
                    brave_search_api_key="brave-test-key",
                    notion_token="test-token",
                    notion_database_id="test-database",
                ),
            ),
            patch("app.services.agent.discover_web_jobs", return_value=[]),
            patch(
                "app.services.agent.fetch_sources",
                return_value=[
                    ("Example Company", [listing]),
                    ("Second Feed", [listing]),
                ],
            ),
            patch(
                "app.services.agent.recommend_jobs",
                return_value=RecommendationBatch(recommendations=[recommendation]),
            ) as recommend,
            patch("app.services.agent.sync_job", return_value="notion-page-id") as sync,
        ):
            result = run_agent_once()
            self.assertEqual(result["found_count"], 1)
            self.assertEqual(result["qualified_count"], 1)
            self.assertEqual(result["saved_count"], 1)
            self.assertEqual(result["synced_count"], 1)
            recommend.assert_called_once()
            sync.assert_called_once()

            db = self.session_factory()
            jobs = list(db.scalars(select(Job)))
            runs = list(db.scalars(select(AgentRun).order_by(AgentRun.id)))
            settings = db.get(AgentSettings, 1)
            self.assertEqual(len(jobs), 1)
            self.assertEqual(jobs[0].notion_page_id, "notion-page-id")
            self.assertEqual(jobs[0].source_type, "agent")
            self.assertEqual(jobs[0].match_score, 92)
            self.assertEqual(settings.last_status, "completed")
            self.assertIsNone(settings.next_run_at)
            self.assertEqual(runs[0].status, "completed")
            db.close()

            repeated = run_agent_once()
            self.assertEqual(repeated["found_count"], 0)
            recommend.assert_called_once()

    def test_run_requires_llm_before_fetching_sources(self) -> None:
        with (
            patch(
                "app.services.agent.get_settings",
                return_value=SimpleNamespace(
                    gemini_api_key=None, anthropic_api_key=None, llm_provider="auto",
                    brave_search_api_key="b", notion_token="token", notion_database_id="db",
                ),
            ),
            patch("app.services.agent.llm_configured", return_value=False),
            patch("app.services.agent.discover_web_jobs") as discover,
            patch("app.services.agent.fetch_sources") as fetch,
        ):
            with self.assertRaises(LLMNotConfiguredError):
                run_agent_once()
            fetch.assert_not_called()
            discover.assert_not_called()

    def test_web_discovery_runs_without_optional_sources_and_preserves_posted_date(self) -> None:
        db = self.session_factory()
        db.query(AgentSource).delete()
        db.commit()
        db.close()
        listing = {
            "role_title": "Frontend Engineer",
            "company": "Web Company",
            "region": "India",
            "location": "Bengaluru",
            "description": "Build user-facing React and TypeScript products.",
            "source_url": "https://jobs.example.com/frontend?utm_source=brave",
            "posted_at": date(2025, 4, 9),
            "source_type": "web",
        }
        duplicate = {**listing, "source_url": "https://jobs.example.com/frontend?utm_campaign=search"}
        recommendation = JobRecommendation(
            job_id=-1,
            match_score=92,
            match_summary="Your React experience matches the role.",
            matched_skills=["React"],
            skill_gaps=[],
            outreach_pitch="I have built React products.",
        )
        with (
            patch(
                "app.services.agent.get_settings",
                return_value=SimpleNamespace(
                    gemini_api_key="test-key",
                    anthropic_api_key=None,
                    llm_provider="auto",
                    brave_search_api_key="brave-test-key",
                    notion_token="test-token",
                    notion_database_id="test-database",
                ),
            ),
            patch(
                "app.services.agent.discover_web_jobs",
                return_value=[("India", [listing, duplicate]), ("Japan", []), ("Singapore", [])],
            ),
            patch("app.services.agent.fetch_sources", return_value=[]),
            patch(
                "app.services.agent.recommend_jobs",
                return_value=RecommendationBatch(recommendations=[recommendation]),
            ),
            patch("app.services.agent.sync_job", return_value="notion-page-id"),
        ):
            result = run_agent_once()

        self.assertEqual(result["found_count"], 1)
        db = self.session_factory()
        job = db.scalar(select(Job))
        self.assertEqual(job.source_type, "web")
        self.assertEqual(job.source_url, "https://jobs.example.com/frontend")
        self.assertEqual(job.posted_at, date(2025, 4, 9))
        db.close()


if __name__ == "__main__":
    unittest.main()
