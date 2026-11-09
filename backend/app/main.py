from contextlib import asynccontextmanager
import asyncio
import json
import logging
from datetime import datetime, timedelta, timezone

from fastapi import Depends, FastAPI, File, Form, HTTPException, Query, UploadFile, status
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.database import SessionLocal, get_db, initialize_database
from app.models import AgentRun, AgentSource, CandidateProfile, Job
from app.schemas import (
    AgentRunRead,
    AgentRunResponse,
    AgentSettingsRead,
    AgentSettingsUpdate,
    AgentSourceCreate,
    AgentSourceRead,
    JobCreate,
    JobRead,
    JobStatus,
    JobUpdate,
    ManualLinkedInJob,
    ManualLinkedInResponse,
    ParseRequest,
    ParsedJob,
    RecommendationBatch,
    RecommendationsResponse,
    ResumeProfile,
    SyncResponse,
)
from app.services.llm import (
    LLMError,
    LLMNotConfiguredError,
    llm_configured,
    llm_provider_names,
    parse_description,
    parse_resume,
    recommend_jobs,
)
from app.services.agent import (
    agent_not_ready_reason,
    ensure_agent_settings,
    qualify_manual_listing,
    recover_interrupted_runs,
    run_agent_once,
    update_next_run,
)
from app.services.career_sources import SourceFetchError, _source_identifier
from app.services.notion_sync import NotionNotConfiguredError, sync_job
from app.services.resume_parser import ResumeExtractionError, read_resume_upload
from app.services.sourcing import get_sample_listings
from app.services.web_discovery import BraveSearchError, WebSearchNotConfiguredError

logger = logging.getLogger(__name__)


async def _agent_scheduler() -> None:
    while True:
        db = SessionLocal()
        try:
            settings = ensure_agent_settings(db)
            if (
                settings.interval_minutes > 0
                and settings.next_run_at is not None
                and (
                    settings.next_run_at.replace(tzinfo=timezone.utc)
                    if settings.next_run_at.tzinfo is None
                    else settings.next_run_at
                )
                <= datetime.now(timezone.utc)
            ):
                not_ready = agent_not_ready_reason(db)
                if not_ready:
                    # Don't record a failed run every interval for something the user still has to set up.
                    settings.last_status = "idle"
                    settings.last_message = not_ready
                    settings.next_run_at = datetime.now(timezone.utc) + timedelta(
                        minutes=min(settings.interval_minutes, 60)
                    )
                    db.commit()
                else:
                    db.close()
                    db = None
                    try:
                        await asyncio.to_thread(run_agent_once)
                    except RuntimeError as error:
                        logger.info("Scheduled run skipped: %s", error)
                    except Exception:
                        logger.exception("Scheduled job sourcing run failed.")
            else:
                db.commit()
        except Exception:
            logger.exception("Could not check scheduled job sourcing state.")
            if db is not None:
                db.rollback()
        finally:
            if db is not None:
                db.close()
        await asyncio.sleep(15)


@asynccontextmanager
async def lifespan(_: FastAPI):
    initialize_database()
    db = SessionLocal()
    ensure_agent_settings(db)
    recovered = recover_interrupted_runs(db)
    if recovered:
        logger.warning("Marked %d interrupted agent run(s) as failed.", recovered)
    db.close()
    scheduler = asyncio.create_task(_agent_scheduler())
    try:
        yield
    finally:
        scheduler.cancel()
        try:
            await scheduler
        except asyncio.CancelledError:
            pass


app = FastAPI(title="Job Hunter Agent API", version="1.0.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=get_settings().allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/jobs", response_model=list[JobRead])
def list_jobs(
    region: str | None = Query(default=None),
    job_status: JobStatus | None = Query(default=None, alias="status"),
    db: Session = Depends(get_db),
) -> list[Job]:
    statement = select(Job).order_by(Job.updated_at.desc(), Job.id.desc())
    if region and region != "All regions":
        statement = statement.where(Job.region == region)
    if job_status:
        statement = statement.where(Job.status == job_status)
    return list(db.scalars(statement))


@app.get("/api/agent/settings", response_model=AgentSettingsRead)
def get_agent_settings(db: Session = Depends(get_db)) -> AgentSettingsRead:
    settings = ensure_agent_settings(db)
    integrations = get_settings()
    return AgentSettingsRead(
        interval_minutes=settings.interval_minutes,
        minimum_match_score=settings.minimum_match_score,
        last_run_at=settings.last_run_at,
        next_run_at=settings.next_run_at,
        last_status=settings.last_status,
        last_message=settings.last_message,
        llm_configured=llm_configured(),
        llm_providers=llm_provider_names(),
        notion_configured=bool(integrations.notion_token and integrations.notion_database_id),
        brave_configured=bool(integrations.brave_search_api_key),
    )


@app.put("/api/agent/settings", response_model=AgentSettingsRead)
def save_agent_settings(payload: AgentSettingsUpdate, db: Session = Depends(get_db)) -> AgentSettingsRead:
    settings = ensure_agent_settings(db)
    settings.interval_minutes = payload.interval_minutes
    settings.minimum_match_score = payload.minimum_match_score
    update_next_run(settings)
    db.commit()
    db.refresh(settings)
    return get_agent_settings(db)


@app.get("/api/agent/sources", response_model=list[AgentSourceRead])
def list_agent_sources(db: Session = Depends(get_db)) -> list[AgentSource]:
    return list(db.scalars(select(AgentSource).order_by(AgentSource.created_at.desc())))


@app.post("/api/agent/sources", response_model=AgentSourceRead, status_code=status.HTTP_201_CREATED)
def create_agent_source(payload: AgentSourceCreate, db: Session = Depends(get_db)) -> AgentSource:
    if payload.source_type != "rss":
        try:
            _source_identifier(payload.url, payload.source_type)
        except SourceFetchError as error:
            raise HTTPException(status_code=422, detail=str(error)) from error
    if db.scalar(select(AgentSource.id).where(AgentSource.url == payload.url)):
        raise HTTPException(status_code=409, detail="That source URL is already configured.")
    source = AgentSource(**payload.model_dump())
    db.add(source)
    settings = ensure_agent_settings(db)
    if settings.last_run_at is None:
        settings.next_run_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(source)
    return source


@app.delete("/api/agent/sources/{source_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_agent_source(source_id: int, db: Session = Depends(get_db)) -> None:
    source = db.get(AgentSource, source_id)
    if source is None:
        raise HTTPException(status_code=404, detail="Agent source not found.")
    db.delete(source)
    db.commit()


@app.post("/api/agent/run", response_model=AgentRunResponse)
def run_agent() -> AgentRunResponse:
    try:
        return AgentRunResponse(**run_agent_once())
    except (LLMNotConfiguredError, NotionNotConfiguredError, WebSearchNotConfiguredError) as error:
        raise HTTPException(status_code=503, detail=str(error)) from error
    except (BraveSearchError, LLMError) as error:
        raise HTTPException(status_code=502, detail=str(error)) from error
    except RuntimeError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    except Exception as error:
        raise HTTPException(status_code=502, detail=f"Agent run failed: {error}") from error


@app.get("/api/agent/runs", response_model=list[AgentRunRead])
def get_agent_runs(limit: int = Query(default=10, ge=1, le=50), db: Session = Depends(get_db)) -> list[AgentRunRead]:
    runs = db.scalars(select(AgentRun).order_by(AgentRun.started_at.desc()).limit(limit))
    return [
        AgentRunRead(
            id=run.id,
            started_at=run.started_at,
            completed_at=run.completed_at,
            status=run.status,
            found_count=run.found_count,
            qualified_count=run.qualified_count,
            saved_count=run.saved_count,
            synced_count=run.synced_count,
            errors=json.loads(run.errors_json),
        )
        for run in runs
    ]


@app.post("/api/agent/linkedin", response_model=ManualLinkedInResponse)
def add_manual_linkedin_job(payload: ManualLinkedInJob, db: Session = Depends(get_db)) -> ManualLinkedInResponse:
    integrations = get_settings()
    if not integrations.notion_token or not integrations.notion_database_id:
        raise HTTPException(
            status_code=503,
            detail="Configure NOTION_TOKEN and NOTION_DATABASE_ID before importing a LinkedIn job.",
        )
    existing = db.scalar(select(Job).where(Job.source_url == payload.source_url))
    if existing is not None:
        minimum_score = ensure_agent_settings(db).minimum_match_score
        qualified = existing.match_score >= minimum_score
        return ManualLinkedInResponse(
            qualified=qualified,
            job=JobRead.model_validate(existing),
            match_score=existing.match_score,
            message=(
                "This LinkedIn role is already in your tracker."
                if qualified
                else f"This LinkedIn role is already saved below your {minimum_score}% match threshold."
            ),
        )
    listing = {
        **payload.model_dump(),
        "status": "Wishlist",
        "match_score": 0,
        "hiring_manager_hints": "",
        "outreach_pitch": "",
        "source_type": "linkedin_manual",
    }
    try:
        recommendation, job, message = qualify_manual_listing(db, listing)
    except (LLMNotConfiguredError, NotionNotConfiguredError) as error:
        raise HTTPException(status_code=503, detail=str(error)) from error
    except LLMError as error:
        raise HTTPException(status_code=502, detail=str(error)) from error
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    return ManualLinkedInResponse(
        qualified=job is not None,
        job=JobRead.model_validate(job) if job else None,
        match_score=recommendation.match_score,
        message=message if job else (
            f"Not saved: match score {recommendation.match_score}% is below your "
            f"{ensure_agent_settings(db).minimum_match_score}% threshold."
        ),
    )


@app.post("/api/jobs", response_model=JobRead, status_code=status.HTTP_201_CREATED)
def create_job(payload: JobCreate, db: Session = Depends(get_db)) -> Job:
    job = Job(**payload.model_dump())
    db.add(job)
    db.commit()
    db.refresh(job)
    return job


@app.patch("/api/jobs/{job_id}", response_model=JobRead)
def update_job(job_id: int, payload: JobUpdate, db: Session = Depends(get_db)) -> Job:
    job = db.get(Job, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found.")
    for field, value in payload.model_dump(exclude_unset=True, exclude_none=True).items():
        setattr(job, field, value)
    db.commit()
    db.refresh(job)
    return job


@app.delete("/api/jobs/{job_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_job(job_id: int, db: Session = Depends(get_db)) -> None:
    job = db.get(Job, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found.")
    db.delete(job)
    db.commit()


@app.post("/api/jobs/seed", response_model=list[JobRead])
def seed_jobs(db: Session = Depends(get_db)) -> list[Job]:
    existing = set(db.scalars(select(Job.source_url)).all())
    created: list[Job] = []
    for listing in get_sample_listings():
        if listing.source_url in existing:
            continue
        job = Job(**listing.model_dump(), source_type="sample")
        db.add(job)
        created.append(job)
    db.commit()
    for job in created:
        db.refresh(job)
    return created


@app.post("/api/parse", response_model=ParsedJob)
def parse_job(payload: ParseRequest, db: Session = Depends(get_db)) -> ParsedJob:
    stored_profile = db.get(CandidateProfile, 1)
    profile = ResumeProfile.model_validate_json(stored_profile.profile_json) if stored_profile else None
    try:
        return parse_description(payload.description, profile)
    except LLMNotConfiguredError as error:
        raise HTTPException(status_code=503, detail=str(error)) from error
    except ValueError as error:
        raise HTTPException(status_code=502, detail=f"Could not parse the AI response: {error}") from error


@app.get("/api/profile", response_model=ResumeProfile | None)
def get_candidate_profile(db: Session = Depends(get_db)) -> ResumeProfile | None:
    profile = db.get(CandidateProfile, 1)
    return ResumeProfile.model_validate_json(profile.profile_json) if profile else None


@app.post("/api/profile/resume", response_model=ResumeProfile)
def upload_resume(
    file: UploadFile = File(...),
    consent_to_ai: bool = Form(...),
    db: Session = Depends(get_db),
) -> ResumeProfile:
    if not consent_to_ai:
        raise HTTPException(status_code=400, detail="Consent is required before resume text is sent to the AI provider.")
    try:
        resume_text = read_resume_upload(file)
    except ResumeExtractionError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    try:
        profile = parse_resume(resume_text)
    except LLMNotConfiguredError as error:
        raise HTTPException(status_code=503, detail=str(error)) from error
    except ValueError as error:
        raise HTTPException(status_code=502, detail=f"Could not analyze resume: {error}") from error

    stored_profile = db.get(CandidateProfile, 1)
    if stored_profile is None:
        stored_profile = CandidateProfile(id=1, profile_json=profile.model_dump_json())
        db.add(stored_profile)
    else:
        stored_profile.profile_json = profile.model_dump_json()
    agent_settings = ensure_agent_settings(db)
    integrations = get_settings()
    if (
        agent_settings.interval_minutes > 0
        and llm_configured()
        and integrations.notion_token
        and integrations.notion_database_id
        and integrations.brave_search_api_key
    ):
        agent_settings.next_run_at = datetime.now(timezone.utc)
    db.commit()
    return profile


@app.delete("/api/profile", status_code=status.HTTP_204_NO_CONTENT)
def delete_candidate_profile(db: Session = Depends(get_db)) -> None:
    profile = db.get(CandidateProfile, 1)
    if profile is None:
        return
    db.delete(profile)
    for job in db.scalars(select(Job)):
        if job.baseline_match_score is not None:
            job.match_score = job.baseline_match_score
        job.baseline_match_score = None
        job.match_summary = ""
        job.matched_skills = []
        job.skill_gaps = []
        job.resume_outreach_pitch = ""
    db.commit()


@app.post("/api/recommendations", response_model=RecommendationsResponse)
def update_recommendations(db: Session = Depends(get_db)) -> RecommendationsResponse:
    stored_profile = db.get(CandidateProfile, 1)
    if stored_profile is None:
        raise HTTPException(status_code=404, detail="Upload and analyze a resume before generating recommendations.")
    profile = ResumeProfile.model_validate_json(stored_profile.profile_json)
    jobs = list(db.scalars(select(Job).order_by(Job.id)))
    if not jobs:
        return RecommendationsResponse(updated=0, message="Add jobs before generating recommendations.")
    failures: list[str] = []
    try:
        batch: RecommendationBatch = recommend_jobs(profile, jobs, failures)
    except LLMNotConfiguredError as error:
        raise HTTPException(status_code=503, detail=str(error)) from error
    if not batch.recommendations and failures:
        raise HTTPException(status_code=502, detail=f"Could not generate recommendations: {failures[0]}")

    jobs_by_id = {job.id: job for job in jobs}
    for recommendation in batch.recommendations:
        job = jobs_by_id[recommendation.job_id]
        if job.baseline_match_score is None:
            job.baseline_match_score = job.match_score
        job.match_score = recommendation.match_score
        job.match_summary = recommendation.match_summary
        job.matched_skills = recommendation.matched_skills
        job.skill_gaps = recommendation.skill_gaps
        job.resume_outreach_pitch = recommendation.outreach_pitch
    db.commit()
    return RecommendationsResponse(
        updated=len(batch.recommendations),
        message=(
            f"Personalized recommendations updated for {len(batch.recommendations)} of {len(jobs)} roles."
            + (f" Some batches failed: {failures[0]}" if failures else "")
        ),
    )


@app.post("/api/jobs/{job_id}/sync", response_model=SyncResponse)
def sync_job_to_notion(job_id: int, db: Session = Depends(get_db)) -> SyncResponse:
    job = db.get(Job, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found.")
    try:
        job.notion_page_id = sync_job(job)
    except NotionNotConfiguredError as error:
        raise HTTPException(status_code=503, detail=str(error)) from error
    except Exception as error:
        logger.exception("Notion sync failed for job %s", job_id)
        raise HTTPException(status_code=502, detail=f"Notion sync failed: {error}") from error
    db.commit()
    return SyncResponse(synced=1, message="Job synced to Notion.")
