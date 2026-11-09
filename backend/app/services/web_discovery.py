import asyncio
from datetime import date, datetime
from html.parser import HTMLParser
import json
from urllib.parse import urlparse

import httpx

from app.config import get_settings
from app.schemas import ResumeProfile
from app.services.job_filters import is_tech_title
from app.services.career_sources import SourceFetchError, _download, _listing_region, _plain_text


BRAVE_SEARCH_URL = "https://api.search.brave.com/res/v1/web/search"
RESULTS_PER_REGION = 20
DETAIL_PAGES_PER_REGION = 10


class WebSearchNotConfiguredError(RuntimeError):
    pass


class BraveSearchError(RuntimeError):
    pass


class _JobPageParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.json_ld: list[str] = []
        self._in_json_ld = False
        self._script_parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attributes = {key.lower(): value or "" for key, value in attrs}
        if tag == "script" and "ld+json" in attributes.get("type", "").lower():
            self._in_json_ld = True
            self._script_parts = []

    def handle_endtag(self, tag: str) -> None:
        if tag == "script" and self._in_json_ld:
            self.json_ld.append("".join(self._script_parts))
            self._in_json_ld = False
            self._script_parts = []

    def handle_data(self, data: str) -> None:
        if self._in_json_ld:
            self._script_parts.append(data)


def _walk_job_postings(value: object):
    if isinstance(value, list):
        for item in value:
            yield from _walk_job_postings(item)
    elif isinstance(value, dict):
        item_type = value.get("@type", [])
        types = item_type if isinstance(item_type, list) else [item_type]
        if any(str(item).casefold() == "jobposting" for item in types):
            yield value
        graph = value.get("@graph")
        if graph is not None:
            yield from _walk_job_postings(graph)


def _parse_posted_date(value: object) -> date | None:
    if not isinstance(value, str) or not value.strip():
        return None
    normalized = value.strip()
    try:
        return date.fromisoformat(normalized[:10])
    except ValueError:
        try:
            return datetime.fromisoformat(normalized.replace("Z", "+00:00")).date()
        except ValueError:
            return None


def _location_text(value: object) -> str:
    if isinstance(value, list):
        return ", ".join(filter(None, (_location_text(item) for item in value)))
    if not isinstance(value, dict):
        return ""
    address = value.get("address", value)
    if isinstance(address, list):
        return ", ".join(filter(None, (_location_text(item) for item in address)))
    if not isinstance(address, dict):
        return ""
    parts = [
        address.get("addressLocality"),
        address.get("addressRegion"),
        address.get("addressCountry"),
    ]
    return ", ".join(str(part) for part in parts if part)


def _job_posting(page: _JobPageParser) -> dict[str, object] | None:
    for document in page.json_ld:
        try:
            decoded = json.loads(document)
        except json.JSONDecodeError:
            continue
        for posting in _walk_job_postings(decoded):
            organization = posting.get("hiringOrganization", {})
            if isinstance(organization, dict):
                company = organization.get("name", "")
            else:
                company = str(organization)
            location = _location_text(posting.get("jobLocation"))
            if posting.get("jobLocationType") == "TELECOMMUTE" and not location:
                location = "Remote"
            return {
                "role_title": str(posting.get("title") or ""),
                "company": str(company),
                "location": location,
                "description": _plain_text(str(posting.get("description") or "")),
                "posted_at": _parse_posted_date(posting.get("datePosted")),
            }
    return None


def _search_terms(profile: ResumeProfile) -> str:
    roles = list(dict.fromkeys(role.strip() for role in profile.target_roles if role.strip()))[:4]
    if not roles:
        roles = ["software engineer"]
    skills = [skill.strip() for skill in profile.skills if skill.strip()][:5]
    role_query = " OR ".join(f'"{role}"' for role in roles)
    skill_query = " ".join(skills)
    return f"({role_query}) jobs hiring {skill_query}".strip()


async def _brave_search(client: httpx.AsyncClient, query: str) -> list[dict[str, object]]:
    try:
        response = await client.get(
            BRAVE_SEARCH_URL,
            params={"q": query, "count": RESULTS_PER_REGION, "safesearch": "moderate"},
        )
        if response.status_code == 429:
            raise BraveSearchError("Brave Search rate limit reached. Try again later.")
        response.raise_for_status()
        payload = response.json()
    except BraveSearchError:
        raise
    except (httpx.HTTPError, ValueError) as error:
        raise BraveSearchError(f"Brave Search request failed: {error}") from error
    if not isinstance(payload, dict):
        raise BraveSearchError("Brave Search returned an invalid response.")
    web_results = payload.get("web")
    results = web_results.get("results", []) if isinstance(web_results, dict) else []
    if not isinstance(results, list):
        raise BraveSearchError("Brave Search returned results in an unexpected format.")
    return results


async def _enrich_search_result(
    item: dict[str, object],
    search_region: str,
) -> dict[str, object] | None:
    title = str(item.get("title") or "").strip()
    source_url = str(item.get("url") or "").strip()
    parsed_url = urlparse(source_url)
    if (
        not title
        or parsed_url.scheme != "https"
        or not parsed_url.hostname
        or parsed_url.username
        or parsed_url.password
    ):
        return None
    if not is_tech_title(title):
        return None
    result: dict[str, object] = {
        "role_title": title[:200],
        "company": parsed_url.hostname.removeprefix("www."),
        "region": search_region,
        "location": search_region,
        "description": _plain_text(str(item.get("description") or "")),
        "source_url": source_url[:1000],
        "posted_at": None,
        "source_type": "web",
    }
    try:
        page_content = await _download(source_url)
        parser = _JobPageParser()
        parser.feed(page_content.decode("utf-8", errors="replace"))
        posting = _job_posting(parser)
    except (httpx.HTTPError, SourceFetchError, ValueError):
        return result
    if posting:
        result["role_title"] = str(posting.get("role_title") or result["role_title"])[:200]
        result["company"] = str(posting.get("company") or result["company"])[:200]
        result["location"] = str(posting.get("location") or result["location"])[:200]
        result["description"] = str(posting.get("description") or result["description"])[:20000]
        result["region"] = _listing_region(str(result["location"]), search_region)
        result["posted_at"] = posting.get("posted_at")
    return result


async def _discover_region(
    client: httpx.AsyncClient,
    profile: ResumeProfile,
    region: str,
) -> tuple[str, list[dict[str, object]]]:
    query = f"{_search_terms(profile)} jobs {region}"
    results = await _brave_search(client, query)
    selected = [
        item
        for item in results
        if isinstance(item, dict)
        and is_tech_title(str(item.get("title") or ""))
    ][:DETAIL_PAGES_PER_REGION]
    semaphore = asyncio.Semaphore(6)

    async def enrich(item: dict[str, object]) -> dict[str, object] | None:
        async with semaphore:
            return await _enrich_search_result(item, region)

    listings = await asyncio.gather(*(enrich(item) for item in selected))
    return region, [listing for listing in listings if listing is not None]


async def _discover_all(profile: ResumeProfile) -> list[tuple[str, list[dict[str, object]] | Exception]]:
    settings = get_settings()
    if not settings.brave_search_api_key:
        raise WebSearchNotConfiguredError(
            "Set BRAVE_SEARCH_API_KEY in backend/.env to enable open-web job discovery."
        )
    async with httpx.AsyncClient(
        timeout=httpx.Timeout(20.0),
        headers={
            "X-Subscription-Token": settings.brave_search_api_key,
            "Accept": "application/json",
            "User-Agent": "LocalJobHunter/1.0",
        },
        follow_redirects=False,
    ) as client:
        results = await asyncio.gather(
            *(_discover_region(client, profile, region) for region in ("India", "Japan", "Singapore")),
            return_exceptions=True,
        )
    discovered: list[tuple[str, list[dict[str, object]] | Exception]] = []
    for region, result in zip(("India", "Japan", "Singapore"), results):
        if isinstance(result, Exception):
            discovered.append((region, result))
        elif isinstance(result, BaseException):
            raise result
        else:
            discovered.append(result)
    return discovered


def discover_web_jobs(profile: ResumeProfile) -> list[tuple[str, list[dict[str, object]] | Exception]]:
    return asyncio.run(_discover_all(profile))
