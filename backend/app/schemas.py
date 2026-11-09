from datetime import date, datetime
import ipaddress
from typing import Literal
from urllib.parse import urlparse

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


Region = Literal["India", "Japan", "Singapore"]
JobStatus = Literal["Wishlist", "Applied", "Interviewing", "Archived"]
SourceType = Literal["greenhouse", "lever", "rss"]


class JobCreate(BaseModel):
    role_title: str = Field(min_length=1, max_length=200)
    company: str = Field(min_length=1, max_length=200)
    region: Region
    location: str = Field(default="", max_length=200)
    status: JobStatus = "Wishlist"
    match_score: int = Field(default=0, ge=0, le=100)
    match_summary: str = ""
    matched_skills: list[str] = Field(default_factory=list)
    skill_gaps: list[str] = Field(default_factory=list)
    hiring_manager_hints: str = ""
    outreach_pitch: str = ""
    description: str = ""
    source_url: str = ""
    posted_at: date | None = None


class JobUpdate(BaseModel):
    role_title: str | None = Field(default=None, min_length=1, max_length=200)
    company: str | None = Field(default=None, min_length=1, max_length=200)
    region: Region | None = None
    location: str | None = Field(default=None, max_length=200)
    status: JobStatus | None = None
    match_score: int | None = Field(default=None, ge=0, le=100)
    match_summary: str | None = None
    matched_skills: list[str] | None = None
    skill_gaps: list[str] | None = None
    hiring_manager_hints: str | None = None
    outreach_pitch: str | None = None
    description: str | None = None
    source_url: str | None = None


class JobRead(JobCreate):
    id: int
    created_at: datetime
    updated_at: datetime
    source_type: str = "manual"
    notion_page_id: str = ""
    resume_outreach_pitch: str = ""

    model_config = ConfigDict(from_attributes=True)


class ParseRequest(BaseModel):
    description: str = Field(min_length=40)


class ResumeProfile(BaseModel):
    profile_summary: str
    skills: list[str]
    years_experience: float | None = Field(default=None, ge=0, le=60)
    seniority: str
    target_roles: list[str]
    achievement_highlights: list[str]


class ParsedJob(BaseModel):
    role_title: str
    company: str
    region: Region
    match_score: int = Field(ge=0, le=100)
    hiring_manager_hints: str
    outreach_pitch: str


class SyncResponse(BaseModel):
    synced: int
    message: str


class JobRecommendation(BaseModel):
    job_id: int
    match_score: int = Field(ge=0, le=100)
    match_summary: str
    matched_skills: list[str]
    skill_gaps: list[str]
    outreach_pitch: str


class RecommendationBatch(BaseModel):
    recommendations: list[JobRecommendation]


class RecommendationsResponse(BaseModel):
    updated: int
    message: str


class AgentSourceCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    source_type: SourceType
    url: str = Field(min_length=8, max_length=1000)
    region: Region

    @field_validator("url")
    @classmethod
    def validate_url(cls, value: str) -> str:
        parsed = urlparse(value)
        if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
            raise ValueError("Sources must use a public HTTPS URL without embedded credentials.")
        hostname = parsed.hostname.lower()
        if hostname in {"localhost", "localhost.localdomain"} or hostname.endswith(".local"):
            raise ValueError("Local network sources are not allowed.")
        try:
            address = ipaddress.ip_address(hostname)
        except ValueError:
            pass
        else:
            if not address.is_global:
                raise ValueError("Local or private IP source URLs are not allowed.")
        return value

    @model_validator(mode="after")
    def validate_source_host(self) -> "AgentSourceCreate":
        hostname = urlparse(self.url).hostname or ""
        allowed_hosts = {
            "greenhouse": {"boards.greenhouse.io", "job-boards.greenhouse.io", "boards-api.greenhouse.io"},
            "lever": {"jobs.lever.co", "jobs.eu.lever.co", "api.lever.co"},
            "rss": None,
        }[self.source_type]
        if allowed_hosts is not None and hostname not in allowed_hosts:
            raise ValueError(f"Use an official {self.source_type.title()} company board URL.")
        return self


class AgentSourceRead(BaseModel):
    id: int
    name: str
    source_type: SourceType
    url: str
    region: Region
    enabled: bool

    model_config = ConfigDict(from_attributes=True)


class AgentSettingsUpdate(BaseModel):
    interval_minutes: int = Field(ge=0, le=525600)
    minimum_match_score: int = Field(default=85, ge=0, le=100)


class AgentSettingsRead(BaseModel):
    interval_minutes: int
    minimum_match_score: int
    last_run_at: datetime | None
    next_run_at: datetime | None
    last_status: str
    last_message: str
    llm_configured: bool
    llm_providers: list[str]
    notion_configured: bool
    brave_configured: bool


class AgentRunRead(BaseModel):
    id: int
    started_at: datetime
    completed_at: datetime | None
    status: str
    found_count: int
    qualified_count: int
    saved_count: int
    synced_count: int
    errors: list[str]


class AgentRunResponse(BaseModel):
    run_id: int
    status: str
    found_count: int
    qualified_count: int
    saved_count: int
    synced_count: int
    message: str
    errors: list[str]


class ManualLinkedInJob(BaseModel):
    role_title: str = Field(min_length=1, max_length=200)
    company: str = Field(min_length=1, max_length=200)
    region: Region
    location: str = Field(default="", max_length=200)
    description: str = Field(min_length=40, max_length=20000)
    source_url: str = Field(min_length=10, max_length=1000)
    posted_at: date | None = None

    @field_validator("source_url")
    @classmethod
    def validate_linkedin_url(cls, value: str) -> str:
        parsed = urlparse(value)
        if parsed.scheme != "https" or parsed.hostname not in {"linkedin.com", "www.linkedin.com"}:
            raise ValueError("Paste a public HTTPS LinkedIn job URL.")
        return value


class ManualLinkedInResponse(BaseModel):
    qualified: bool
    job: JobRead | None
    match_score: int
    message: str
