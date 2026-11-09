from datetime import datetime, timedelta, timezone
import json
import threading
from collections.abc import Mapping
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.database import SessionLocal
from app.models import AgentRun, AgentSettings, AgentSource, CandidateProfile, Job
from app.schemas import JobRecommendation, ResumeProfile
from app.services.career_sources import fetch_sources
from app.services.job_filters import is_tech_title, listing_key
from app.services.llm import LLMNotConfiguredError, llm_configured, recommend_jobs
from app.services.notion_sync import NotionNotConfiguredError, sync_job
from app.services.web_discovery import WebSearchNotConfiguredError, discover_web_jobs


_RUN_LOCK = threading.Lock()
MAX_LISTINGS_SCORED_PER_RUN = 60


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _canonical_source_url(url: str) -> str:
    parsed = urlsplit(url)
    tracking_parameters = {"fbclid", "gclid", "ref", "source", "campaign"}
    query = [
        (key, value)
        for key, value in parse_qsl(parsed.query, keep_blank_values=True)
        if not key.casefold().startswith("utm_") and key.casefold() not in tracking_parameters
    ]
    return urlunsplit((parsed.scheme.lower(), parsed.netloc.lower(), parsed.path, urlencode(query), ""))


def ensure_agent_settings(db: Session) -> AgentSettings:
    settings = db.get(AgentSettings, 1)
    if settings is None:
        settings = AgentSettings(
            id=1,
            interval_minutes=1440,
            minimum_match_score=85,
            next_run_at=_utcnow() + timedelta(days=1),
        )
        db.add(settings)
        db.commit()
        db.refresh(settings)
    return settings


def agent_not_ready_reason(db: Session) -> str | None:
    """Why a scheduled run can't start yet, or None when everything it needs is configured."""
    configured = get_settings()
    if not llm_configured():
        return "Configure ANTHROPIC_API_KEY or GEMINI_API_KEY to enable scheduled runs."
    if not configured.brave_search_api_key:
        return "Configure BRAVE_SEARCH_API_KEY to enable scheduled runs."
    if not configured.notion_token or not configured.notion_database_id:
        return "Configure NOTION_TOKEN and NOTION_DATABASE_ID to enable scheduled runs."
    if db.get(CandidateProfile, 1) is None:
        return "Upload and analyze your resume to enable scheduled runs."
    return None


def recover_interrupted_runs(db: Session) -> int:
    """Mark runs left in 'running' by a crash or restart as failed."""
    stuck = list(db.scalars(select(AgentRun).where(AgentRun.status == "running")))
    for run in stuck:
        run.status = "failed"
        run.completed_at = _utcnow()
        run.errors_json = json.dumps(["The app stopped before this run finished."])
    if stuck:
        db.commit()
    return len(stuck)


def run_agent_once() -> dict:
    if not _RUN_LOCK.acquire(blocking=False):
        raise RuntimeError("The agent is already running.")
    db = SessionLocal()
    started_at = _utcnow()
    run = AgentRun(started_at=started_at, status="running", errors_json="[]")
    db.add(run)
    db.commit()
    db.refresh(run)
    errors: list[str] = []

    try:
        agent_settings = ensure_agent_settings(db)
        configured = get_settings()
        if not llm_configured():
            raise LLMNotConfiguredError("Configure ANTHROPIC_API_KEY or GEMINI_API_KEY before running the sourcing agent.")
        if not configured.brave_search_api_key:
            raise WebSearchNotConfiguredError("Configure BRAVE_SEARCH_API_KEY before running the sourcing agent.")
        if not configured.notion_token or not configured.notion_database_id:
            raise NotionNotConfiguredError("Configure NOTION_TOKEN and NOTION_DATABASE_ID before running the sourcing agent.")
        stored_profile = db.get(CandidateProfile, 1)
        if stored_profile is None:
            raise ValueError("Upload and analyze your resume before running the sourcing agent.")
        profile = ResumeProfile.model_validate_json(stored_profile.profile_json)
        sources = list(
            db.scalars(select(AgentSource).where(AgentSource.enabled.is_(True)).order_by(AgentSource.id))
        )

        pending_sync = list(
            db.scalars(
                select(Job).where(
                    Job.notion_page_id == "",
                    Job.match_score >= agent_settings.minimum_match_score,
                    Job.source_type.in_(["agent", "web", "linkedin_manual"]),
                )
            )
        )
        for job in pending_sync:
            try:
                job.notion_page_id = sync_job(job)
                run.synced_count += 1
            except Exception as error:
                errors.append(f"Notion retry failed for {job.company} — {job.role_title}: {error}")

        candidates: list[Mapping[str, object]] = []
        for region, discovered in discover_web_jobs(profile):
            if isinstance(discovered, Exception):
                errors.append(f"Brave web discovery ({region}): {discovered}")
                continue
            candidates.extend(discovered)

        for source_name, fetched in fetch_sources(sources):
            if isinstance(fetched, Exception):
                errors.append(f"{source_name}: {fetched}")
                continue
            for listing in fetched:
                listing["source_type"] = "agent"
                title = listing["role_title"].strip()
                url = listing["source_url"].strip()
                if not title or not url or not is_tech_title(title):
                    continue
                candidates.append(listing)

        existing_urls: set[str] = set()
        seen_keys: set[str] = set()
        for url, company, title, location in db.execute(
            select(Job.source_url, Job.company, Job.role_title, Job.location)
        ):
            if url:
                existing_urls.add(_canonical_source_url(url))
            seen_keys.add(listing_key(company, title, location))
        fresh_listings: list[dict[str, object]] = []
        seen_urls = set(existing_urls)
        for candidate in candidates:
            listing = dict(candidate)
            url = _canonical_source_url(str(listing["source_url"]))
            listing["source_url"] = url
            key = listing_key(str(listing.get("company", "")), str(listing.get("role_title", "")), str(listing.get("location", "")))
            if url in seen_urls or key in seen_keys:
                continue
            seen_urls.add(url)
            seen_keys.add(key)
            fresh_listings.append(listing)
        if len(fresh_listings) > MAX_LISTINGS_SCORED_PER_RUN:
            errors.append(
                f"Scored the first {MAX_LISTINGS_SCORED_PER_RUN} of {len(fresh_listings)} new listings; "
                "the rest will be picked up on the next run."
            )
            fresh_listings = fresh_listings[:MAX_LISTINGS_SCORED_PER_RUN]
        run.found_count = len(fresh_listings)

        recommendations: list[JobRecommendation] = []
        if fresh_listings:
            transient_jobs = [
                Job(id=-(index + 1), **listing)
                for index, listing in enumerate(fresh_listings)
            ]
            batch = recommend_jobs(profile, transient_jobs, errors)
            recommendations = batch.recommendations
            recommendation_by_id = {item.job_id: item for item in recommendations}
            minimum_score = agent_settings.minimum_match_score
            qualifying = [
                (listing, recommendation_by_id[-(index + 1)])
                for index, listing in enumerate(fresh_listings)
                if -(index + 1) in recommendation_by_id
                and recommendation_by_id[-(index + 1)].match_score >= minimum_score
            ]
            run.qualified_count = len(qualifying)

            for listing, recommendation in qualifying:
                job = Job(
                    **listing,
                    match_score=recommendation.match_score,
                    match_summary=recommendation.match_summary,
                    matched_skills=recommendation.matched_skills,
                    skill_gaps=recommendation.skill_gaps,
                    resume_outreach_pitch=recommendation.outreach_pitch,
                )
                db.add(job)
                db.flush()
                run.saved_count += 1
                db.commit()
                try:
                    job.notion_page_id = sync_job(job)
                    run.synced_count += 1
                    db.commit()
                except Exception as error:
                    errors.append(f"Notion sync failed for {job.company} — {job.role_title}: {error}")

        run.status = "partial" if errors else "completed"
        if errors:
            run_message = (
                f"Found {run.found_count} new roles; {run.qualified_count} met the "
                f"{agent_settings.minimum_match_score}% threshold; saved {run.saved_count}, "
                f"synced {run.synced_count}. Some sources or Notion writes failed."
            )
        else:
            run_message = (
                f"Found {run.found_count} new roles; {run.qualified_count} met the "
                f"{agent_settings.minimum_match_score}% threshold; saved {run.saved_count} "
                f"and synced {run.synced_count} to Notion."
            )
        completed_at = _utcnow()
        agent_settings.last_run_at = completed_at
        agent_settings.last_status = run.status
        agent_settings.last_message = run_message
        agent_settings.next_run_at = (
            completed_at + timedelta(minutes=agent_settings.interval_minutes)
            if agent_settings.interval_minutes > 0
            else None
        )
        run.completed_at = _utcnow()
        run.errors_json = json.dumps(errors)
        db.commit()
        return {
            "run_id": run.id,
            "status": run.status,
            "found_count": run.found_count,
            "qualified_count": run.qualified_count,
            "saved_count": run.saved_count,
            "synced_count": run.synced_count,
            "message": agent_settings.last_message,
            "errors": errors,
        }
    except Exception as error:
        db.rollback()
        run = db.get(AgentRun, run.id)
        if run is None:
            raise RuntimeError("The agent run record disappeared unexpectedly.") from error
        agent_settings = ensure_agent_settings(db)
        message = str(error)
        run.status = "failed"
        completed_at = _utcnow()
        run.completed_at = completed_at
        run.errors_json = json.dumps([message])
        agent_settings.last_run_at = _utcnow()
        agent_settings.last_status = "failed"
        agent_settings.last_message = message
        agent_settings.next_run_at = (
            completed_at + timedelta(minutes=agent_settings.interval_minutes)
            if agent_settings.interval_minutes > 0
            else None
        )
        db.commit()
        raise
    finally:
        db.close()
        _RUN_LOCK.release()


def update_next_run(settings: AgentSettings) -> None:
    settings.next_run_at = (
        _utcnow() + timedelta(minutes=settings.interval_minutes)
        if settings.interval_minutes > 0
        else None
    )


def qualify_manual_listing(
    db: Session,
    listing: dict[str, object],
) -> tuple[JobRecommendation, Job | None, str]:
    profile_row = db.get(CandidateProfile, 1)
    if profile_row is None:
        raise ValueError("Upload and analyze your resume before adding an AI-qualified LinkedIn role.")
    settings = ensure_agent_settings(db)
    profile = ResumeProfile.model_validate_json(profile_row.profile_json)
    temporary_job = Job(id=-1, **listing)
    batch = recommend_jobs(profile, [temporary_job])
    if len(batch.recommendations) != 1:
        raise ValueError("The AI did not return exactly one recommendation for the supplied LinkedIn role.")
    recommendation = batch.recommendations[0]
    if recommendation.match_score < settings.minimum_match_score:
        return recommendation, None, (
            f"Not saved: match score {recommendation.match_score}% is below your "
            f"{settings.minimum_match_score}% threshold."
        )

    job = db.scalar(select(Job).where(Job.source_url == listing["source_url"]))
    if job is None:
        job = Job(**{**listing, "source_type": "linkedin_manual"})
        db.add(job)
    if job.baseline_match_score is None:
        job.baseline_match_score = job.match_score
    job.match_score = recommendation.match_score
    job.match_summary = recommendation.match_summary
    job.matched_skills = recommendation.matched_skills
    job.skill_gaps = recommendation.skill_gaps
    job.resume_outreach_pitch = recommendation.outreach_pitch
    db.flush()
    db.commit()
    try:
        job.notion_page_id = sync_job(job)
    except Exception as error:
        return recommendation, job, f"Saved locally; Notion sync failed and can be retried: {error}"
    db.commit()
    db.refresh(job)
    return recommendation, job, "Saved to your local tracker and Notion."
