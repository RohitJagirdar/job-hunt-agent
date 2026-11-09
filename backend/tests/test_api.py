import unittest
from types import SimpleNamespace
from unittest.mock import patch

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base, get_db
from app.main import app
from app.models import AgentRun, Job
from app.services.agent import agent_not_ready_reason, recover_interrupted_runs


class ApiTests(unittest.TestCase):
    def setUp(self) -> None:
        self.engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
        Base.metadata.create_all(self.engine)
        self.session_factory = sessionmaker(bind=self.engine, expire_on_commit=False)

        def override_db():
            db = self.session_factory()
            try:
                yield db
            finally:
                db.close()

        app.dependency_overrides[get_db] = override_db
        self.client = TestClient(app)  # not used as a context manager, so no lifespan/scheduler

    def tearDown(self) -> None:
        app.dependency_overrides.clear()
        self.engine.dispose()

    def _add_job(self, **overrides) -> int:
        db = self.session_factory()
        job = Job(role_title="Engineer", company="Co", region="India", source_url="https://example.com/j", **overrides)
        db.add(job)
        db.commit()
        job_id = job.id
        db.close()
        return job_id

    def test_manual_sync_stores_the_notion_page_id(self) -> None:
        job_id = self._add_job()
        with patch("app.main.sync_job", return_value="page-123"):
            response = self.client.post(f"/api/jobs/{job_id}/sync")
        self.assertEqual(response.status_code, 200)
        db = self.session_factory()
        self.assertEqual(db.get(Job, job_id).notion_page_id, "page-123")
        db.close()

    def test_manual_sync_reports_notion_failures_as_502(self) -> None:
        job_id = self._add_job()
        with patch("app.main.sync_job", side_effect=RuntimeError("notion down")):
            response = self.client.post(f"/api/jobs/{job_id}/sync")
        self.assertEqual(response.status_code, 502)
        self.assertIn("notion down", response.json()["detail"])

    def test_patch_cannot_change_source_type(self) -> None:
        job_id = self._add_job(source_type="manual")
        response = self.client.patch(f"/api/jobs/{job_id}", json={"source_type": "agent", "status": "Applied"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["source_type"], "manual")
        self.assertEqual(response.json()["status"], "Applied")

    def test_seeded_jobs_are_marked_as_samples(self) -> None:
        response = self.client.post("/api/jobs/seed")
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json())
        self.assertEqual({job["source_type"] for job in response.json()}, {"sample"})

    def test_recommendations_apply_partial_results(self) -> None:
        from app.models import CandidateProfile
        from app.schemas import JobRecommendation, RecommendationBatch

        first, second = self._add_job(), self._add_job()
        db = self.session_factory()
        db.add(
            CandidateProfile(
                id=1,
                profile_json='{"profile_summary":"x","skills":[],"years_experience":null,"seniority":"s",'
                '"target_roles":[],"achievement_highlights":[]}',
            )
        )
        db.commit()
        db.close()

        def partial(profile, jobs, errors):
            errors.append("batch 2 failed")
            return RecommendationBatch(
                recommendations=[
                    JobRecommendation(
                        job_id=first, match_score=77, match_summary="ok", matched_skills=[], skill_gaps=[], outreach_pitch="hi"
                    )
                ]
            )

        with patch("app.main.recommend_jobs", side_effect=partial):
            response = self.client.post("/api/recommendations")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["updated"], 1)
        self.assertIn("batch 2 failed", response.json()["message"])
        db = self.session_factory()
        self.assertEqual(db.get(Job, first).match_score, 77)
        self.assertEqual(db.get(Job, second).match_score, 0)
        db.close()


class AgentHousekeepingTests(unittest.TestCase):
    def setUp(self) -> None:
        self.engine = create_engine("sqlite://", poolclass=StaticPool)
        Base.metadata.create_all(self.engine)
        self.db = sessionmaker(bind=self.engine, expire_on_commit=False)()

    def tearDown(self) -> None:
        self.db.close()
        self.engine.dispose()

    def test_interrupted_runs_are_marked_failed(self) -> None:
        from datetime import datetime, timezone

        self.db.add(AgentRun(started_at=datetime.now(timezone.utc), status="running", errors_json="[]"))
        self.db.add(AgentRun(started_at=datetime.now(timezone.utc), status="completed", errors_json="[]"))
        self.db.commit()
        self.assertEqual(recover_interrupted_runs(self.db), 1)
        statuses = sorted(run.status for run in self.db.scalars(select(AgentRun)))
        self.assertEqual(statuses, ["completed", "failed"])

    def test_not_ready_reason_reports_missing_setup(self) -> None:
        configured = SimpleNamespace(brave_search_api_key="b", notion_token="t", notion_database_id="d")
        with (
            patch("app.services.agent.get_settings", return_value=configured),
            patch("app.services.agent.llm_configured", return_value=True),
        ):
            self.assertIn("resume", agent_not_ready_reason(self.db))
        with (
            patch("app.services.agent.get_settings", return_value=configured),
            patch("app.services.agent.llm_configured", return_value=False),
        ):
            self.assertIn("ANTHROPIC_API_KEY", agent_not_ready_reason(self.db))


if __name__ == "__main__":
    unittest.main()
