# Job Hunter Agent

A local-first job search workspace with a FastAPI + SQLite backend and a React dashboard. Your opportunities and structured resume profile stay in a local SQLite database; AI analysis (Claude, with Gemini as a fallback) and Notion sync are optional actions that only run when you configure credentials.

## Requirements

- Python 3.11 or newer
- Node.js 20 or newer and npm

Use a Python `venv` for the backend environment. The frontend uses npm because Vite is a Node.js application.

## Run locally

### 1. Start the API

From the project root, create and activate a virtual environment:

```powershell
cd backend
py -3 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
Copy-Item .env.example .env
```

Edit `backend/.env` and add integration credentials if desired. Then run the API:

```powershell
python -m uvicorn app.main:app --reload
```

The API is available at `http://localhost:8000`; interactive docs are at `http://localhost:8000/docs`. On first launch, SQLite creates `backend/job_hunter.db`.

### 2. Start the dashboard

In a second PowerShell window, from the project root:

```powershell
cd frontend
npm install
npm run dev
```

Open `http://localhost:5173`. The dashboard expects the API at `http://localhost:8000/api`. To use a different API address, set `VITE_API_URL` before starting Vite (for example, `$env:VITE_API_URL="http://localhost:8001/api"`).

The scheduler runs inside the FastAPI process, so keep that terminal/process running for scheduled checks. Use one Uvicorn worker for this local app; the scheduler is intentionally local and process-based.

## Integrations

Copy `backend/.env.example` to `backend/.env`:

| Variable | Purpose |
| --- | --- |
| `ANTHROPIC_API_KEY` | Claude key. Claude is tried first for job-description parsing, resume profiling, and personalized recommendations. |
| `GEMINI_API_KEY` | Gemini key, used as the fallback when a Claude request fails or is declined (or on its own if no Claude key is set). At least one of the two AI keys is required for agent runs. |
| `LLM_PROVIDER` | `auto` (default: Claude, then Gemini), `anthropic`, or `gemini`. |
| `ANTHROPIC_PROFILE_MODEL` / `ANTHROPIC_SCORING_MODEL` | Claude models for resume profiling (default `claude-sonnet-5-5`) and bulk job scoring (default `claude-haiku-5-5`). |
| `GEMINI_MODEL` | Gemini model used for fallback requests. |
| `BRAVE_SEARCH_API_KEY` | Enables open-web job discovery across India, Japan, and Singapore. Required for agent runs; obtain an API token from Brave Search. |
| `NOTION_TOKEN` | Notion integration token. Required for agent runs and manual job sync. |
| `NOTION_DATABASE_ID` | Target Notion database ID. Required for agent runs and manual job sync. |
| `DATABASE_URL` | SQLAlchemy database URL; defaults to local SQLite at `backend/job_hunter.db`. |
| `CORS_ORIGINS` | Comma-separated allowed browser origins; defaults to `http://localhost:5173,http://127.0.0.1:5173`. |

### Create the Notion database

1. In Notion, create a new **Table database** (or choose the existing jobs table you want to use).
2. Rename its title column to `Name`. Add the following properties with these exact names and types:

   | Property | Notion type | Options / purpose |
   | --- | --- | --- |
   | `Name` | Title | Job role title; rename the default title property. |
   | `Company` | Text | Company name. |
   | `Region` | Select | Add `India`, `Japan`, and `Singapore`. |
   | `Status` | Select | Add `Wishlist`, `Applied`, `Interviewing`, and `Archived`. |
   | `Match Score` | Number | Resume-based match estimate from 0 to 100. |
   | `Location` | Text | City, country, or remote location. |
   | `Outreach Pitch` | Text | Resume-tailored pitch for you to review and use. |
   | `Hiring Manager Hints` | Text | Hints saved with the listing. |
   | `Source URL` | URL | Used to update an existing job page instead of duplicating it. |
   | `Posted At` | Date | Original listing date when known; blank if unavailable. |

3. Create a Notion integration, then share the database with that integration (database menu → **Connections** / **Add connections**).
4. Copy the integration token and database ID into `backend/.env` as `NOTION_TOKEN` and `NOTION_DATABASE_ID`, then restart the backend.

The app requires these exact property names and compatible types for sync. `Date Applied` and `Date of Reply` are not currently managed by the app; adding those properties is fine, but the app will not populate them. The agent upserts by Source URL so reruns do not create duplicate Notion pages. Manual job entry stays local-first; autonomous sourcing requires Gemini, Brave Search, and Notion credentials.

## Use the app

- **Load sample roles** adds representative engineering roles in India, Japan, and Singapore. Seeding is idempotent by source URL.
- **Add opportunity** saves a role locally. Paste a description and use AI to prefill structured fields, or enter them manually.
- **Add your resume** accepts PDF, DOCX, TXT, or Markdown files up to 5 MB. The original file is handled for the upload request only and is not retained in the app or database. After you explicitly consent, contact-redacted text (emails, phone numbers, GitHub/LinkedIn links and a leading name line are removed on a best-effort basis; other details such as addresses are only excluded by instruction) is sent to Claude, or to Gemini if Claude is unavailable, to create a skills-and-experience profile. When the agent runs, target-role names and skills from that profile are sent to Brave Search as query terms; the resume text itself is not sent to Brave. Raw extracted text is not stored; only the structured profile is saved locally.
- **Refresh matches** compares your profile with all saved roles to produce an estimated match score, evidence-based skills in common, areas to check, and a tailored outreach pitch. Recommendations are AI estimates rather than hiring guarantees. Replacing or removing your resume updates/deletes the local profile; removing it also clears resume-based scores, explanations, and pitches.
- **Job search agent** uses Brave Search to discover public job pages across India, Japan, and Singapore on your chosen schedule (daily, every six hours, manual, or a custom number of hours). Each run requests up to 20 search results per market and enriches up to 10 job pages per market; it searches Brave's public index rather than crawling the entire internet. Posting dates are read only from a listing's structured `datePosted` metadata; search-engine crawl dates are not used as posting dates. Optional Greenhouse/Lever boards and RSS/Atom feeds add more coverage. LinkedIn does not permit this app to scrape job pages: use **Add a LinkedIn role**, paste the URL and listing details, and optionally provide its posted date. New jobs below your configured match threshold are not saved; the default threshold is 85%. Qualifying jobs are saved locally and upserted to Notion, including `Posted At` (blank when unknown). The agent never submits applications or sends outreach.
- **Board / table** switches the pipeline presentation. Use the region and status filters or search by role, company, and location.
- **Opportunity details** shows the posting date (or `Unknown` when the listing does not disclose one), match score, resume-match explanation, overlapping skills, areas to check, hiring-manager hints, role description, and outreach pitch. Copy the pitch, change status, sync to Notion, or delete the listing.

The supported workflow statuses are Wishlist, Applied, Interviewing, and Archived.

## API overview

| Method | Route | Description |
| --- | --- | --- |
| `GET` | `/api/health` | Health check |
| `GET` | `/api/jobs` | List jobs; optional `region` and `status` filters |
| `POST` | `/api/jobs` | Create a local job |
| `PATCH` | `/api/jobs/{id}` | Update job fields/status |
| `DELETE` | `/api/jobs/{id}` | Delete a job |
| `POST` | `/api/jobs/seed` | Add sample listings |
| `POST` | `/api/parse` | Parse raw description with AI |
| `GET` | `/api/profile` | Read the saved structured resume profile |
| `POST` | `/api/profile/resume` | Extract and analyze an uploaded resume (requires explicit AI-provider consent) |
| `DELETE` | `/api/profile` | Delete the profile and its generated recommendations |
| `POST` | `/api/recommendations` | Generate personalized recommendations for saved jobs |
| `POST` | `/api/jobs/{id}/sync` | Create a page in the configured Notion database |
| `GET` / `PUT` | `/api/agent/settings` | Read or update the run interval and minimum score |
| `GET` / `POST` | `/api/agent/sources` | List or add company career/feed sources |
| `DELETE` | `/api/agent/sources/{id}` | Remove a configured source |
| `POST` | `/api/agent/run` | Run sourcing, matching, and Notion sync immediately |
| `GET` | `/api/agent/runs` | Read recent run history |
| `POST` | `/api/agent/linkedin` | Score a manually supplied LinkedIn job |

AI and Notion endpoints return an explicit `503` with setup guidance when credentials are missing. The local tracker remains usable without either integration.

## Backend tests

From `backend/` with the virtual environment activated:

```powershell
python -m unittest discover -s tests
```

## Behaviour notes

- Each agent run scores at most 60 new listings; the rest are picked up on the next run. Scoring failures for one batch do not discard the other batches.
- Scheduled runs are skipped (without recording a failed run) until the AI key, Brave key, Notion credentials and a resume profile are all in place. A run left in `running` by a crash is marked failed on the next start.
- Sample roles are stored with source type `sample` so they can be told apart from real listings.
