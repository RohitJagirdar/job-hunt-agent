from notion_client import Client

from app.config import get_settings
from app.models import Job


class NotionNotConfiguredError(RuntimeError):
    pass


def sync_job(job: Job) -> str:
    settings = get_settings()
    if not settings.notion_token or not settings.notion_database_id:
        raise NotionNotConfiguredError(
            "Set NOTION_TOKEN and NOTION_DATABASE_ID in backend/.env to enable Notion sync."
        )

    client = Client(auth=settings.notion_token)
    properties = {
        "Name": {"title": [{"text": {"content": job.role_title}}]},
        "Company": {"rich_text": [{"text": {"content": job.company}}]},
        "Region": {"select": {"name": job.region}},
        "Status": {"select": {"name": job.status}},
        "Match Score": {"number": job.match_score},
        "Location": {"rich_text": [{"text": {"content": job.location}}]},
        "Outreach Pitch": {
            "rich_text": [{"text": {"content": (job.resume_outreach_pitch or job.outreach_pitch)[:2000]}}]
        },
        "Hiring Manager Hints": {
            "rich_text": [{"text": {"content": job.hiring_manager_hints[:2000]}}]
        },
        "Source URL": {"url": job.source_url or None},
        "Posted At": {"date": {"start": job.posted_at.isoformat()} if job.posted_at else None},
    }
    if job.notion_page_id:
        client.pages.update(page_id=job.notion_page_id, properties=properties)
        return job.notion_page_id
    if job.source_url:
        existing_pages = client.databases.query(
            database_id=settings.notion_database_id,
            filter={"property": "Source URL", "url": {"equals": job.source_url}},
            page_size=1,
        ).get("results", [])
        if existing_pages:
            page_id = existing_pages[0]["id"]
            client.pages.update(page_id=page_id, properties=properties)
            return page_id
    page = client.pages.create(
        parent={"database_id": settings.notion_database_id},
        properties=properties,
    )
    return page["id"]
