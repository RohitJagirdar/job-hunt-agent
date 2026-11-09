# Job Hunter Agent — Test Report

**Test date:** 17 October 2026  
**Scope:** Backend unit tests, Python compilation and dependencies, frontend typecheck/build and npm audit, isolated API smoke test, and live Brave, Gemini, and Notion integration checks.

## Overall result

All checks performed for this report passed. Live checks used the configured credentials without printing or including secret values in output. Tests used fabricated job/resume data. A full autonomous sourcing run was deliberately not started because it could save newly discovered jobs into the user's local tracker and Notion.

## Offline and local checks

| Check | Result | Details |
| --- | --- | --- |
| Backend unit tests | **PASS** | `python -m unittest discover -s tests -v` — 20 tests passed. |
| Python compilation | **PASS** | `python -m compileall -q app tests`. |
| Backend dependency consistency | **PASS** | `python -m pip check` reported no broken requirements. |
| Frontend typecheck and production build | **PASS** | `npm run build` runs `tsc -b` followed by Vite production build; 1,580 modules transformed. |
| Frontend dependency audit | **PASS** | `npm audit --audit-level=moderate` reported 0 vulnerabilities. |
| API smoke test | **PASS** | Started FastAPI on `127.0.0.1:8001` with an isolated temporary SQLite database. Health, agent settings, jobs, agent runs, and OpenAPI endpoints returned successfully. Confirmed the API reported Gemini, Brave, and Notion as configured. The server was stopped and the temporary database removed. |

### Backend unit-test coverage

The 20 tests cover:

- **Agent orchestration and career sources (5):** required Gemini configuration, qualified-job persistence and deduplication, optional-source web discovery, posting-date preservation, RSS normalization, and supported-source URL validation.
- **Notion mapping and upsert behavior (4):** page creation, update by stored Notion page ID, source-URL lookup after an interrupted local write, and a blank date when `Posted At` is unknown.
- **Resume extraction and recommendation logic (5):** PDF/DOCX and text extraction, size/format/readability validation, contact redaction before Gemini, and batched recommendations preserving job IDs.
- **Web discovery (6):** Brave response parsing and invalid-response handling, Schema.org `JobPosting` date extraction, page enrichment, maximum concurrent fetches, and rejection of private-network URLs.

External providers are mocked in these unit tests; live provider checks are recorded separately below.

## Live integration checks

| Integration | Result | What was verified |
| --- | --- | --- |
| Brave Search API | **PASS** | Made a live search request for software engineering jobs in Singapore; received HTTP success and one result. |
| Gemini API | **PASS** | Using fabricated sample data, called the actual app job-description parser and resume recommendation service with `gemini-3.8-flash`. Both returned valid structured results; the recommendation included a valid score and a pitch. |
| Notion database access/schema | **PASS** | Retrieved the `Jobs Data` database and verified the required property names/types and the expected Region and Status options. |
| Notion create/read-back/cleanup | **PASS** | A temporary sample job was created using the app's `sync_job` service. Name, Company, Source URL, and Posted At were read back and verified; the temporary page was then archived. |

The Notion create/read-back/cleanup test was run in the immediately preceding verification step on 17 October 2026. It did not use an actual discovered vacancy or send outreach.

## Notes and limits

- Gemini had returned intermittent `503 UNAVAILABLE` responses during earlier checks. The current live parsing and recommendation requests both succeeded, but model availability can vary.
- The live Gemini tests validate a small parser request and one fabricated recommendation; they do not guarantee that every large or unusual resume/job description will produce valid output.
- The full scheduled/manual agent workflow was not run against live providers, to avoid writing real discovered opportunities into the local tracker and Notion without an explicit request to do that.
- These checks do not validate long-running scheduler behavior over time, all possible provider responses, or the visual layout across browsers and screen sizes.
- `Date Applied`, `Date of Reply`, and Gmail monitoring are not implemented and were not tested.

## Reproduction commands

Run backend checks from `backend/` with the project virtual environment activated:

```powershell
python -m unittest discover -s tests -v
python -m compileall -q app tests
python -m pip check
```

Run frontend checks from `frontend/`:

```powershell
npm run build
npm audit --audit-level=moderate
```
