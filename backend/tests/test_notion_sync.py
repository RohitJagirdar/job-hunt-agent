from types import SimpleNamespace
from datetime import date
import unittest
from unittest.mock import Mock, patch

from app.models import Job
from app.services.notion_sync import sync_job


def make_job(page_id: str = "") -> Job:
    return Job(
        id=1,
        role_title="Frontend Engineer",
        company="Example Co",
        region="India",
        location="Bengaluru",
        status="Wishlist",
        match_score=91,
        resume_outreach_pitch="Resume-specific pitch.",
        outreach_pitch="Manually written pitch.",
        hiring_manager_hints="Find the web platform engineering lead.",
        source_url="https://example.com/jobs/123",
        posted_at=date(2025, 4, 9),
        notion_page_id=page_id,
    )


class NotionSyncTests(unittest.TestCase):
    def setUp(self) -> None:
        self.query = Mock(return_value={"results": []})
        self.update = Mock()
        self.create = Mock(return_value={"id": "created-page-id"})
        self.client = SimpleNamespace(
            databases=SimpleNamespace(query=self.query),
            pages=SimpleNamespace(update=self.update, create=self.create),
        )
        self.settings_patch = patch(
            "app.services.notion_sync.get_settings",
            return_value=SimpleNamespace(notion_token="secret", notion_database_id="database-id"),
        )
        self.client_patch = patch("app.services.notion_sync.Client", return_value=self.client)
        self.settings_patch.start()
        self.client_patch.start()

    def tearDown(self) -> None:
        self.client_patch.stop()
        self.settings_patch.stop()

    def test_new_jobs_create_a_notion_page_with_personalized_pitch(self) -> None:
        page_id = sync_job(make_job())

        self.assertEqual(page_id, "created-page-id")
        self.query.assert_called_once()
        self.create.assert_called_once()
        properties = self.create.call_args.kwargs["properties"]
        self.assertEqual(
            properties["Outreach Pitch"]["rich_text"][0]["text"]["content"],
            "Resume-specific pitch.",
        )
        self.assertEqual(properties["Posted At"]["date"]["start"], "2025-04-09")

    def test_known_notion_page_is_updated_without_creating_duplicates(self) -> None:
        page = make_job("existing-page-id")
        self.assertEqual(sync_job(page), "existing-page-id")

        self.update.assert_called_once()
        self.query.assert_not_called()
        self.create.assert_not_called()

    def test_unknown_posted_date_is_written_as_an_empty_notion_date(self) -> None:
        job = make_job()
        job.posted_at = None

        sync_job(job)

        properties = self.create.call_args.kwargs["properties"]
        self.assertIsNone(properties["Posted At"]["date"])

    def test_source_url_query_upserts_a_page_after_a_local_write_interruption(self) -> None:
        self.query.return_value = {"results": [{"id": "existing-source-url-page"}]}
        self.assertEqual(sync_job(make_job()), "existing-source-url-page")

        self.update.assert_called_once()
        self.create.assert_not_called()


if __name__ == "__main__":
    unittest.main()
