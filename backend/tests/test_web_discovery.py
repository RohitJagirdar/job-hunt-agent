import asyncio
from datetime import date
import json
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, Mock, patch

from app.schemas import ResumeProfile
from app.services.career_sources import SourceFetchError, _download
from app.services.web_discovery import (
    BraveSearchError,
    _JobPageParser,
    _brave_search,
    _discover_region,
    _enrich_search_result,
    _job_posting,
    _parse_posted_date,
)


class WebDiscoveryTests(unittest.TestCase):
    def test_brave_response_results_are_read_from_web_results_contract(self) -> None:
        response = SimpleNamespace(
            status_code=200,
            raise_for_status=Mock(),
            json=Mock(return_value={"web": {"results": [{"title": "Software Engineer"}]}}),
        )
        client = SimpleNamespace(get=AsyncMock(return_value=response))

        results = asyncio.run(_brave_search(client, "frontend jobs Japan"))

        self.assertEqual(results, [{"title": "Software Engineer"}])
        client.get.assert_awaited_once()
        self.assertEqual(client.get.await_args.kwargs["params"]["count"], 20)

    def test_invalid_brave_response_is_reported(self) -> None:
        response = SimpleNamespace(status_code=200, raise_for_status=Mock(), json=Mock(return_value=[]))
        client = SimpleNamespace(get=AsyncMock(return_value=response))

        with self.assertRaises(BraveSearchError):
            asyncio.run(_brave_search(client, "engineering jobs India"))

    def test_json_ld_job_posting_supplies_only_publisher_posted_date(self) -> None:
        job = {
            "@type": "JobPosting",
            "title": "Frontend Engineer",
            "datePosted": "2025-04-09T08:30:00+09:00",
            "hiringOrganization": {"name": "Example Japan"},
            "jobLocation": {"address": {"addressLocality": "Tokyo", "addressCountry": "Japan"}},
            "description": "<p>Build React products.</p>",
        }
        parser = _JobPageParser()
        parser.feed(f'<script type="application/ld+json">{json.dumps(job)}</script>')

        posting = _job_posting(parser)

        self.assertEqual(posting["posted_at"], date(2025, 4, 9))
        self.assertEqual(posting["location"], "Tokyo, Japan")
        self.assertEqual(_parse_posted_date("invalid"), None)

    def test_discovered_page_enrichment_preserves_json_ld_posting_date(self) -> None:
        job = {
            "@type": "JobPosting",
            "title": "Frontend Engineer",
            "datePosted": "2025-04-09",
            "hiringOrganization": {"name": "Example Japan"},
            "jobLocation": {"address": {"addressLocality": "Tokyo", "addressCountry": "Japan"}},
            "description": "Build React products.",
        }
        html = f'<script type="application/ld+json">{json.dumps(job)}</script>'.encode()
        with patch("app.services.web_discovery._download", new=AsyncMock(return_value=html)):
            result = asyncio.run(
                _enrich_search_result(
                    {"title": "Frontend Engineer jobs", "url": "https://jobs.example.com/frontend"},
                    "India",
                )
            )

        self.assertEqual(result["posted_at"], date(2025, 4, 9))
        self.assertEqual(result["region"], "Japan")
        self.assertEqual(result["company"], "Example Japan")

    def test_result_page_fetches_are_limited_to_six_concurrent_requests(self) -> None:
        profile = ResumeProfile(
            profile_summary="Frontend engineer",
            skills=["React"],
            seniority="Early career",
            target_roles=["Frontend Engineer"],
            achievement_highlights=[],
        )
        active = 0
        peak = 0

        async def enrich(item: dict[str, object], region: str) -> dict[str, object]:
            nonlocal active, peak
            active += 1
            peak = max(peak, active)
            await asyncio.sleep(0)
            active -= 1
            return {"source_url": item["url"], "region": region}

        results = [
            {"title": "Frontend Engineer", "url": f"https://jobs.example.com/{index}"}
            for index in range(10)
        ]
        with (
            patch("app.services.web_discovery._brave_search", new=AsyncMock(return_value=results)),
            patch("app.services.web_discovery._enrich_search_result", side_effect=enrich),
        ):
            _, listings = asyncio.run(_discover_region(object(), profile, "India"))

        self.assertEqual(len(listings), 10)
        self.assertLessEqual(peak, 6)

    def test_private_ip_source_is_rejected_before_request(self) -> None:
        with self.assertRaises(SourceFetchError):
            asyncio.run(_download("https://127.0.0.1/job"))


if __name__ == "__main__":
    unittest.main()
