# Job Hunter Agent: Interview Guide

This guide describes the implementation in this repository. Use it to explain the design honestly: this is a local-first personal job-search assistant with bounded web discovery, not a crawler of the entire internet and not an autonomous application-submission bot.

## 1. A concise project introduction

> I built a local-first job-search assistant with a React and TypeScript dashboard and a FastAPI backend. It stores jobs and a structured candidate profile in SQLite, searches Brave's public web index and optional career feeds, then uses Gemini to estimate how well new roles fit the candidate's resume. Roles above a configurable score threshold are saved locally and synced to a Notion database. The user stays in control: the app does not apply for jobs or send outreach.

## 2. The problem and the user

Job seekers often track roles in one place, their resume in another, and outreach notes somewhere else. Repeatedly finding roles, assessing fit, and copying details is tedious. This app brings discovery, matching, and tracking into one local workspace, while using Notion as an optional external copy of qualifying opportunities.

The intended user is one job seeker running the app locally. It is not currently designed as a multi-user hosted service.

## 3. Architecture at a glance

```text
React + TypeScript dashboard (Vite)
      | JSON over HTTP
      v
FastAPI routes and Pydantic validation
      |
      +--> SQLAlchemy --> local SQLite
      |
      +--> Brave Search --> public search results
      |                      --> bounded HTTPS job-page enrichment
      +--> optional Greenhouse / Lever / RSS feeds
      |
      +--> Gemini --> structured resume profile and job recommendations
      |
      +--> Notion API --> one-way create/update of qualifying jobs
```

The Python dependencies are installed in `backend/.venv`; the frontend is built with npm. Credentials are read from `backend/.env`, not committed to source control.

## 4. Explain one agent run, step by step

1. The user presses **Run agent now**, or the in-process scheduler reaches the configured time.
2. The backend takes a process-local lock so two runs in this process cannot overlap.
3. It checks required configuration and loads the structured resume profile and enabled optional sources from SQLite.
4. Brave receives search queries formed from up to four target roles, up to five skills, and each of India, Japan, and Singapore. The implementation requests up to 20 results per market and enriches at most 10 job pages per market.
5. Optional Greenhouse and Lever boards or RSS/Atom feeds are fetched and normalized. One source failure is recorded without discarding successful results from other sources.
6. Job URLs are canonicalized to remove common tracking parameters, then candidates are deduplicated against one another and existing local jobs.
7. Gemini scores the new roles against the structured candidate profile and produces a short rationale, matched skills, skill gaps, and a resume-grounded outreach pitch.
8. Only results at or above the configured threshold (85% by default) are saved in SQLite.
9. Each saved job is synced to Notion. Source URL is used to find/update an existing page, avoiding duplicates on repeat syncs. A Notion failure is recorded; the local job remains saved and can be retried.
10. The run summary and errors are persisted so the dashboard can show what happened.

### How a resume is handled

The backend accepts PDF, DOCX, TXT, and Markdown files up to 5 MB, extracts text, and requires explicit consent before sending contact-redacted text to Gemini. It stores the resulting structured profile, not the original file or raw resume text. During discovery, role names and skills from the profile become Brave query terms; the resume text itself is not sent to Brave.

## 5. Module map

| Module | Responsibility | Interview explanation |
| --- | --- | --- |
| `frontend/src/App.tsx` | Dashboard state, job pipeline views, modals, agent controls, and user actions | The React UI loads API data, keeps interaction state, and delegates HTTP calls to the API client. |
| `frontend/src/api.ts` | Typed HTTP requests to the backend | A small shared request helper centralizes the API base URL and error handling. |
| `frontend/src/types.ts` | Frontend data contracts | These TypeScript types mirror the JSON shapes the UI consumes. |
| `backend/app/main.py` | FastAPI app lifecycle, routes, request-to-service orchestration, scheduler | Routes validate inputs and call service functions; the lifespan initializes the database and starts/stops the scheduler. |
| `backend/app/config.py` | Environment-backed configuration | Pydantic Settings loads credentials and local defaults from environment variables / `.env`. |
| `backend/app/database.py` | SQLAlchemy engine, session dependency, SQLite schema initialization | A request-scoped dependency yields and closes a database session; the startup migration adds columns to existing local databases. |
| `backend/app/models.py` | SQLAlchemy persistence models | Tables represent jobs, the candidate profile, configured sources, agent settings, and run history. |
| `backend/app/schemas.py` | Pydantic API contracts and input validation | Request/response models constrain fields, dates, regions, statuses, and source URLs at the API boundary. |
| `backend/app/services/agent.py` | Main sourcing/matching/saving/sync workflow | This is the orchestration layer: source, deduplicate, recommend, threshold, persist, sync, and report. |
| `backend/app/services/web_discovery.py` | Brave queries and job-page metadata extraction | It searches each market and reads Schema.org `JobPosting` data when available, including the publisher's `datePosted`. |
| `backend/app/services/career_sources.py` | Greenhouse, Lever, and RSS/Atom integrations | Each adapter normalizes provider-specific responses into a common listing shape. Fetching enforces HTTPS/public-address checks, no redirects, and a response-size cap. |
| `backend/app/services/llm.py` | Resume parsing and job recommendations | Prompts request structured JSON; Pydantic validates the returned data before it is used. |
| `backend/app/services/resume_parser.py` | Resume file validation and text extraction | It checks format and size limits, extracts text, and returns a clear error when content is unreadable or too short. |
| `backend/app/services/notion_sync.py` | Mapping a local job to Notion properties and upserting | It maps fields to the required Notion schema and uses the source URL or saved Notion page ID to update rather than duplicate. |
| `backend/app/services/sourcing.py` | Sample listing data | Used by the dashboard's sample-data action and local development. |
| `backend/tests/` | Unit tests for integrations and workflows | External services are mocked so tests cover behavior without API keys or network access. |

## 6. Notion database structure and setup

The integration writes a local job to a Notion page using the following exact property names and compatible types. The database title column should be renamed to `Name`.

| Property | Notion type | Values / mapping |
| --- | --- | --- |
| `Name` | Title | Job role title. |
| `Company` | Text (rich text) | Company name. |
| `Region` | Select | `India`, `Japan`, or `Singapore`. |
| `Status` | Select | `Wishlist`, `Applied`, `Interviewing`, or `Archived`. |
| `Match Score` | Number | Estimated match score, 0–100. |
| `Location` | Text (rich text) | Job location. |
| `Outreach Pitch` | Text (rich text) | Resume-tailored pitch if present, otherwise the manual pitch. |
| `Hiring Manager Hints` | Text (rich text) | Hints associated with the opportunity. |
| `Source URL` | URL | Job listing URL; used to find and update an existing page. |
| `Posted At` | Date | Publisher's `datePosted` when extracted, or blank when unknown. |

To connect it, create a Notion integration, share the table database with that integration, and put its token and the database ID in `backend/.env` as `NOTION_TOKEN` and `NOTION_DATABASE_ID`. Restart the backend after changing `.env`. The sync is one-way from the app to Notion and occurs for qualifying agent-discovered jobs, qualifying manual LinkedIn imports, or when the user explicitly chooses **Sync to Notion**.

`Date Applied` and `Date of Reply` are not currently written or updated by this app. You may add those properties for your own manual tracking, but the application does not yet manage them or monitor email.

## 7. Design choices and trade-offs

### Local-first storage

SQLite keeps the job tracker usable without a hosted database and makes setup simple. The structured profile and jobs remain on the user's machine. Gemini, Brave, and Notion still receive the specific information needed for their features when those features run.

**Trade-off:** SQLite and an in-process scheduler are appropriate for a single-user local app, but are not a production multi-user deployment strategy.

### Search index instead of crawling the whole web

Brave provides the discovery index. The app asks targeted queries and inspects a bounded number of candidate pages; it does not search "millions of sources" directly or guarantee complete coverage.

**Trade-off:** results depend on search indexing, query quality, and what metadata each job page publishes.

### Match threshold before saving

Gemini returns a resume-specific estimated match score, and a configurable threshold (85 by default) controls which discovered roles enter the tracker and Notion.

**Trade-off:** an LLM score is a heuristic, not a calibrated probability of getting hired. The explanation and score should be reviewed by the user.

### Structured extraction with graceful source errors

Provider-specific data is normalized into a common job listing format. If one provider fails, other provider results can still be processed and the error is shown in run history.

**Trade-off:** public pages are inconsistent. Some listings only yield the search result's title/snippet, and posting dates remain unknown unless the page provides `datePosted`.

### Notion as a one-way sync target

The local database remains the working source for this application. The app creates or updates Notion pages when a sync is requested or the agent saves a qualifying role. It does not continuously import Notion edits back into SQLite.

**Trade-off:** editing a job status in the dashboard does not automatically push that change unless the user chooses **Sync to Notion**.

### User approval and privacy boundaries

The system does not send applications or emails. Resume consent is explicit, contact data is redacted before Gemini receives resume text, and only the structured profile is stored. LinkedIn pages are not scraped; the user may manually paste listing details.

## 8. Security and reliability discussion

- API keys are read from `.env`; `backend/.env` is gitignored. They must never be committed or pasted into source.
- Uploaded resumes have file type, byte-size, and minimum extracted-text checks.
- Public source-page fetching requires HTTPS, resolves and rejects non-public addresses, disables redirects, and caps response size. The same constrained download path is reused for web-result enrichment.
- Input schemas validate allowed regions/statuses and validate user-configured feed/board URLs.
- Provider exceptions are reported as run errors rather than silently treated as successful results.
- The run lock prevents concurrent runs only within one Python process. It is not a distributed lock.
- The Notion database property names and types must agree with the configured mapping. Missing or mismatched properties cause sync errors.
- AI output is untrusted external data: JSON parsing and Pydantic validation are used before applying recommendations.

If asked what would be needed before exposing it publicly: add user authentication/authorization, encrypted secret storage, a durable distributed job queue and lock, database migrations (for example Alembic), stronger monitoring/retries, provider rate-limit policies, privacy/retention controls, and deployment-specific network protections.

## 9. Limitations to state clearly

- No automatic Gmail/Outlook monitoring, date-applied automation, or reply tracking exists.
- No automatic application submission or email sending exists.
- Notion sync is one-way; Notion edits are not pulled into the app.
- The app queries a search provider's public index with bounded result counts; it does not crawl the entire web.
- Posting date is unknown unless supplied manually or published as structured job metadata.
- The scheduler runs in the FastAPI process. Keep one Uvicorn worker running for scheduled checks; it is not a durable scheduler if the process is stopped.
- Live Brave, Gemini, and Notion calls require the user's own configured credentials and were not needed for the offline unit tests.

## 10. Common interview questions and answer outlines

### "Why did you choose FastAPI?"

FastAPI gives a straightforward way to define HTTP routes, validate inputs and outputs with Pydantic, and expose interactive API documentation. It also fits a small Python service where the resume and job-processing libraries are available.

### "Why SQLite instead of PostgreSQL?"

The target is a local-first, single-user app. SQLite removes the need to run a database server and keeps setup approachable. For multiple concurrent users or a hosted service, I would move to PostgreSQL and add managed migrations and deployment infrastructure.

### "What makes this an agent?"

It can run a bounded workflow on a schedule or on demand: discover roles, evaluate them against the user's profile, apply a user-configured threshold, save qualifying matches, and sync them to Notion. It is not an unrestricted autonomous agent: it has a narrow goal, explicit limits, and does not take consequential actions such as applying or contacting employers.

### "How do you avoid duplicate jobs?"

Before scoring, candidate URLs are normalized to remove common tracking parameters and compared both with existing database URLs and URLs already seen in that run. Notion sync then uses the source URL or previously stored Notion page ID to update the matching page.

### "How do you handle a failed integration?"

Configuration errors fail clearly. During a run, source and Notion failures are recorded in its error list. A failed Notion write does not discard the already committed local job; a later run retries qualifying, unsynced agent jobs.

### "How do you know a job's posting date?"

For discovered jobs, the extractor reads Schema.org `JobPosting.datePosted`. It deliberately does not mistake a search engine's crawl date for a posting date. When that field is missing or invalid, the date stays null; a user can enter it for a manually added job.

### "What does the match score mean?"

It is a model-generated estimate based on the structured candidate profile and job description. The app also stores a rationale, skills in common, and areas to verify. It is not a hiring probability, so I would present it as decision support, not a guarantee.

### "What happens to the resume?"

The app extracts text in memory, checks file type/size/readability, and requires explicit consent before sending contact-redacted text to Gemini. It stores the structured profile rather than the original file or raw extracted text. Brave receives role/skill search terms, not the resume document.

### "How is the scheduled task implemented?"

FastAPI starts a background asyncio loop in its lifespan. It checks persisted settings and runs the synchronous workflow in a worker thread when due. The implementation is intentionally simple for a local single-process application; a deployed multi-worker app should use a durable scheduler/queue and distributed coordination.

### "How would you test this without real API keys?"

The unit tests mock external providers and assert the local behavior: normalization, deduplication, score threshold handling, persistence, date extraction, Notion property payload, and error cases. This makes the tests deterministic and avoids network calls and credential requirements.

### "What would you improve next?"

I would prioritize integration contract tests with recorded provider fixtures, explicit retry/backoff and provider rate-limit behavior, schema migrations through Alembic, splitting the large React app component into focused components, and better observability. Gmail tracking would be a separate opt-in OAuth feature requiring careful permission and privacy choices.

## 11. A short demo script

1. Show the local dashboard and explain that SQLite is the app's working store.
2. Upload a resume and explain consent, redaction, and structured-profile storage.
3. Show the configured search schedule, Brave readiness, threshold, and optional career sources.
4. Run the agent and explain discovery → normalization → deduplication → Gemini match → threshold → local save → Notion upsert.
5. Open a saved job and show its evidence, pitch, source link, and posted-date behavior.
6. Explain that outreach is a draft only, email is not monitored, and the user chooses when to sync manual edits.

## 12. Suggested preparation before an interview

- Be ready to point from the API route in `backend/app/main.py` to the orchestrator in `backend/app/services/agent.py`.
- Practice drawing the data flow in section 3 from memory.
- Run `python -m unittest discover -s tests` from `backend/`.
- Run `npm run build` from `frontend/`.
- Be able to explain one failure path (for example: Notion fails, local save succeeds, later retry) and one privacy decision (resume text is not stored).
- Do not claim that this searches every site, verifies match scores objectively, monitors email, or syncs Notion bidirectionally.
