import asyncio
from html.parser import HTMLParser
import ipaddress
import json
import socket
from urllib.parse import urljoin, urlparse
import xml.etree.ElementTree as ET

import httpx
from defusedxml import DefusedXmlException
from defusedxml import ElementTree as SafeET

from app.models import AgentSource


MAX_RESPONSE_BYTES = 2 * 1024 * 1024
USER_AGENT = "LocalJobHunter/1.0 (user-configured career source reader)"


class SourceFetchError(RuntimeError):
    pass


class _TextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self.skip_depth = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in {"script", "style", "noscript"}:
            self.skip_depth += 1

    def handle_endtag(self, tag: str) -> None:
        if tag in {"script", "style", "noscript"} and self.skip_depth:
            self.skip_depth -= 1
        elif tag in {"p", "br", "li", "div"}:
            self.parts.append("\n")

    def handle_data(self, data: str) -> None:
        if not self.skip_depth:
            self.parts.append(data)


def _plain_text(value: str | None) -> str:
    parser = _TextExtractor()
    parser.feed(value or "")
    return " ".join(" ".join(parser.parts).split())[:20000]


def _listing_region(location: str, fallback: str) -> str:
    normalized = location.casefold()
    indicators = {
        "India": ("india", "bengaluru", "bangalore", "mumbai", "hyderabad", "pune", "gurugram", "gurgaon", "chennai", "new delhi"),
        "Japan": ("japan", "tokyo", "osaka", "kyoto", "yokohama", "nagoya", "fukuoka"),
        "Singapore": ("singapore",),
    }
    for region, terms in indicators.items():
        if any(term in normalized for term in terms):
            return region
    return fallback


async def _download(url: str) -> bytes:
    parsed = urlparse(url)
    if parsed.scheme != "https" or not parsed.hostname:
        raise SourceFetchError("Only public HTTPS source URLs are supported.")
    if parsed.hostname.lower() in {"localhost", "localhost.localdomain"} or parsed.hostname.lower().endswith(".local"):
        raise SourceFetchError("Local network source URLs are not allowed.")
    try:
        address = ipaddress.ip_address(parsed.hostname)
    except ValueError:
        try:
            resolved_results = await asyncio.to_thread(
                socket.getaddrinfo, parsed.hostname, None, 0, socket.SOCK_STREAM
            )
            resolved_addresses = {
                ipaddress.ip_address(result[4][0])
                for result in resolved_results
            }
        except OSError as error:
            raise SourceFetchError(f"Could not resolve source host: {error}") from error
    else:
        resolved_addresses = {address}
    if not resolved_addresses or any(not address.is_global for address in resolved_addresses):
        raise SourceFetchError("Source host must resolve only to public internet addresses.")
    try:
        async with httpx.AsyncClient(
            timeout=httpx.Timeout(20.0),
            follow_redirects=False,
            headers={
                "User-Agent": USER_AGENT,
                "Accept": "application/json, application/xml, text/xml, application/rss+xml, text/html",
            },
        ) as client:
            async with client.stream("GET", url) as response:
                if response.is_redirect:
                    raise SourceFetchError("Career source redirected. Add its final HTTPS URL directly.")
                response.raise_for_status()
                # Re-check the address actually connected to, so DNS rebinding after the lookup above fails.
                network_stream = response.extensions.get("network_stream")
                server_address = network_stream.get_extra_info("server_addr") if network_stream else None
                if server_address and not ipaddress.ip_address(server_address[0]).is_global:
                    raise SourceFetchError("Source host must resolve only to public internet addresses.")
                body = bytearray()
                async for chunk in response.aiter_bytes():
                    body.extend(chunk)
                    if len(body) > MAX_RESPONSE_BYTES:
                        raise SourceFetchError("Career source response exceeded the 2 MB limit.")
                return bytes(body)
    except SourceFetchError:
        raise
    except httpx.HTTPError as error:
        raise SourceFetchError(f"Could not fetch source: {error}") from error


def _source_identifier(url: str, source_type: str) -> str:
    parsed = urlparse(url)
    path_parts = [part for part in parsed.path.split("/") if part]
    if source_type == "greenhouse":
        if len(path_parts) >= 3 and path_parts[0] == "v1" and path_parts[1] == "boards":
            return path_parts[2]
        if path_parts and path_parts[0] == "boards":
            path_parts = path_parts[1:]
        if path_parts:
            return path_parts[0]
    elif source_type == "lever":
        if len(path_parts) >= 3 and path_parts[0] == "v0" and path_parts[1] == "postings":
            return path_parts[2]
        if path_parts and path_parts[0] == "postings":
            path_parts = path_parts[1:]
        if path_parts:
            return path_parts[0]
    raise SourceFetchError(f"Could not determine the {source_type} board identifier from this URL.")


async def _fetch_greenhouse(source: AgentSource) -> list[dict[str, str]]:
    board = _source_identifier(source.url, "greenhouse")
    payload = json.loads(await _download(f"https://boards-api.greenhouse.io/v1/boards/{board}/jobs?content=true"))
    return [
        {
            "role_title": item.get("title", ""),
            "company": source.name,
            "location": (item.get("location") or {}).get("name", ""),
            "description": _plain_text(item.get("content", "")),
            "source_url": item.get("absolute_url", ""),
            "region": _listing_region((item.get("location") or {}).get("name", ""), source.region),
        }
        for item in payload.get("jobs", [])
    ]


async def _fetch_lever(source: AgentSource) -> list[dict[str, str]]:
    company = _source_identifier(source.url, "lever")
    payload = json.loads(await _download(f"https://api.lever.co/v0/postings/{company}?mode=json"))
    return [
        {
            "role_title": item.get("text", ""),
            "company": source.name,
            "location": (item.get("categories") or {}).get("location", ""),
            "description": _plain_text(item.get("descriptionPlain") or item.get("description", "")),
            "source_url": item.get("hostedUrl", ""),
            "region": _listing_region((item.get("categories") or {}).get("location", ""), source.region),
        }
        for item in payload
    ]


def _xml_text(element: ET.Element | None) -> str:
    if element is None:
        return ""
    return "".join(element.itertext()).strip()


def _xml_link(item: ET.Element) -> str:
    for child in item:
        if child.tag.rsplit("}", 1)[-1] == "link":
            href = child.attrib.get("href")
            if href:
                return href
            if child.text:
                return child.text.strip()
    return ""


async def _fetch_feed(source: AgentSource) -> list[dict[str, str]]:
    payload = await _download(source.url)
    try:
        root = SafeET.fromstring(payload)
    except (ET.ParseError, DefusedXmlException) as error:
        raise SourceFetchError(f"Feed is not valid RSS or Atom XML: {error}") from error

    entries = [element for element in root.iter() if element.tag.rsplit("}", 1)[-1] in {"item", "entry"}]
    listings = []
    for entry in entries:
        fields = {child.tag.rsplit("}", 1)[-1]: _xml_text(child) for child in entry}
        link = _xml_link(entry)
        link = urljoin(source.url, link)
        description = fields.get("description") or fields.get("summary") or fields.get("content", "")
        title = fields.get("title", "")
        if not title or not link:
            continue
        listings.append(
            {
                "role_title": title[:200],
                "company": fields.get("company") or source.name,
                "location": fields.get("location", ""),
                "description": _plain_text(description),
                "source_url": link[:1000],
                "region": _listing_region(fields.get("location", ""), source.region),
            }
        )
    return listings


async def fetch_source(source: AgentSource) -> list[dict[str, str]]:
    if source.source_type == "greenhouse":
        return await _fetch_greenhouse(source)
    if source.source_type == "lever":
        return await _fetch_lever(source)
    if source.source_type == "rss":
        return await _fetch_feed(source)
    raise SourceFetchError(f"Unsupported source type: {source.source_type}")


def fetch_sources(sources: list[AgentSource]) -> list[tuple[str, list[dict[str, str]] | Exception]]:
    async def gather() -> list[tuple[str, list[dict[str, str]] | Exception]]:
        async def fetch_one(source: AgentSource) -> tuple[str, list[dict[str, str]] | Exception]:
            try:
                return source.name, await fetch_source(source)
            except Exception as error:
                return source.name, error

        return await asyncio.gather(*(fetch_one(source) for source in sources))

    return asyncio.run(gather())
