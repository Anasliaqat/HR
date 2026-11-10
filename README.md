# AI-Powered HR Hiring Automation

A starter project for an HR-reviewed hiring workflow using FastAPI, React, PostgreSQL, OpenAI, LangGraph, and Vapi.

The planned workflow has three AI-assisted stages:

1. PDF/DOCX resume parsing and local semantic job-match scoring.
2. Screening calls and answer summaries.
3. Interview availability and scheduling.

AI output is advisory. HR must review and approve candidates before they advance; the system must not automatically reject candidates.

## Project layout

- `backend/` — FastAPI application, API modules, agents, services, models, and database setup.
- `frontend/` — React application built with Vite.
- `tests/` — backend and frontend tests (to be added).
- `docker-compose.yml` — local PostgreSQL service for development.

## Requirements

- Python 3.10 or newer
- Node.js 20 or newer and npm
- Docker Desktop (optional, for PostgreSQL)
- Resume scoring uses Sentence Transformers locally and downloads
  `all-MiniLM-L6-v2` on first evaluation; no paid LLM API key is required.

## Backend setup

From the project root, create and activate a virtual environment:

```powershell
cd backend
py -3 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
Copy-Item .env.example .env
```

Edit `backend/.env` and set a non-empty `POSTGRES_PASSWORD` and `DATABASE_URL`. Use URL-encoded credentials if the password contains reserved URL characters. Set `DATABASE_URL` using this format, replacing the placeholders:

```text
postgresql+psycopg://<user>:<url-encoded-password>@localhost:5432/<database>
```

For Vapi screening, set `VAPI_API_KEY`, `VAPI_ASSISTANT_ID`,
`VAPI_PHONE_NUMBER_ID`, `VAPI_PUBLIC_PHONE_NUMBER`, `PHONE_DEFAULT_REGION`,
and a long random `VAPI_WEBHOOK_SECRET` in `backend/.env`. These are
server-side settings only; never put the private key or webhook secret in the
React environment.

Start PostgreSQL from the project root, loading the backend environment file for Compose variable substitution:

```powershell
docker compose --env-file backend/.env up -d db
```

Start the API from the `backend/` directory. On startup, SQLAlchemy creates missing tables for all registered models:

```powershell
uvicorn app.main:app --reload
```

The API is available at `http://127.0.0.1:8000`; interactive API documentation is at `http://127.0.0.1:8000/docs`.

Jobs, candidates, applications, resume metadata/evaluations, screenings, interviews, users, email logs, and agent runs are represented by SQLAlchemy models. API records are stored in PostgreSQL; uploaded resume files are saved in `backend/uploads/`. The `memory_store.py` module remains for compatibility but is no longer used by the API. Resume scoring is advisory and requires HR review; it does not automatically reject candidates or approve them.

The local PostgreSQL service must be running before starting the API. From the project root, start it with `docker compose --env-file backend/.env up -d db`, then run `uvicorn app.main:app --reload --host 127.0.0.1 --port 8000` from `backend/`. The backend serves the `/api` prefix and allows the Vite origins `http://localhost:5173` and `http://127.0.0.1:5173`. The frontend API base URL is centralized in `frontend/src/services/api.js` and can be overridden with `VITE_API_BASE_URL` in `frontend/.env`.

## ZETECH email automation

The Email Automation page uses each application's latest CV score and HR review workflow. Scores below `EMAIL_AUTOMATION_REJECT_BELOW_SCORE`, evaluations with configured required skills but no matched skills, and evaluations that explicitly contain no relevant evidence are placed in the separate **Over Agent Review** queue without sending an automatic email. HR's manual approval or rejection in that queue sends the matching selection or rejection email only when candidate consent and provider configuration permit it. Missing evaluation evidence is not treated as proof of irrelevance. Scores through `EMAIL_AUTOMATION_REVIEW_THROUGH_SCORE` stay pending HR review without an email; scores above that and below `EMAIL_AUTOMATION_INTERVIEW_FROM_SCORE` require an HR decision and then send the matching email; scores through `EMAIL_AUTOMATION_INTERVIEW_THROUGH_SCORE` become eligible for interview scheduling and receive an invitation only after a real calendar booking is confirmed. Higher scores follow `EMAIL_AUTOMATION_ABOVE_RANGE_ACTION`, which defaults to `pending_review`. These settings in `backend/.env` let HR configure score boundaries and above-range behavior; keep the thresholds ordered and within 0–100. With defaults, 60% stays in HR review, 61–69% require an HR decision, and 70–90% are eligible for interview scheduling. An HR approval is stored as `approved_by_hr`, distinct from score-based `interview_eligible`.

Emails are sent for real through Resend or SMTP; `SCHEDULING_TEST_MODE` does not simulate this email agent. Configure either `RESEND_API_KEY` with `EMAIL_FROM_ADDRESS`, or `SMTP_HOST`, `SMTP_PORT`, and a sender using `SMTP_FROM_EMAIL` or `EMAIL_FROM_ADDRESS`. SMTP authentication uses `SMTP_USER` and `SMTP_PASSWORD` when a user is set. Delivery requires candidate email consent to be explicitly recorded from the candidate profile. The history stores recipient, template type, subject, body, status, timestamps, provider ID, application, and any delivery error. Failed messages can be retried from the Email Automation page; Resend requests use idempotency keys. Deleting application email history from the dashboard hides the records but retains their idempotency data to prevent accidental duplicate delivery.

For interview invitations, use the existing interview scheduler to confirm a calendar slot and provide its actual meeting link or office address. Invitations are not sent for test-mode bookings, incomplete meeting details, or candidates without recorded email consent. Configure the score thresholds, delivery provider, and consent policy before enabling real candidate communications. Existing databases receive the email audit, consent, and interview detail columns when the API initializes; for production, use a managed migration process rather than relying on startup schema changes.

The initializer uses `Base.metadata.create_all()` to create missing tables and adds the new job columns to existing `jobs` tables. It does not migrate other existing schemas. The resume evaluator adds an `evaluation_details` JSON column to `resume_evaluations`; the screening integration adds `job_related_highlights`, `ended_reason`, `consent_confirmed_on_call`, and `consent_obtained_at` to `screenings`. Apply migrations before deploying those other changes to an existing database; for PostgreSQL, the screening changes are equivalent to:

```sql
ALTER TABLE screenings ADD COLUMN job_related_highlights JSONB NOT NULL DEFAULT '[]'::jsonb;
ALTER TABLE screenings ADD COLUMN ended_reason VARCHAR(120);
ALTER TABLE screenings ADD COLUMN consent_confirmed_on_call BOOLEAN;
ALTER TABLE screenings ADD COLUMN consent_obtained_at TIMESTAMPTZ;
```

Also apply the resume migration described above. Interview scheduling adds calendar and notification tracking fields; for PostgreSQL, apply:

```sql
ALTER TABLE interviews ADD COLUMN calendar_event_id VARCHAR(255);
ALTER TABLE interviews ADD COLUMN notifications_status VARCHAR(40) NOT NULL DEFAULT 'not_sent';
ALTER TABLE interviews ADD COLUMN notification_error TEXT;
ALTER TABLE interviews ADD COLUMN test_mode BOOLEAN NOT NULL DEFAULT TRUE;
```

Use a migration tool for schema changes to databases with existing data.

## Vapi screening configuration

This integration reuses the already-published assistant and phone number; it
does not create or update an assistant. Store the private Vapi key, assistant
ID, phone-number ID, and dialable number only in `backend/.env`. Keep the
assistant's questions, prompt, transcriber, and voice configured in Vapi.

1. Set `VAPI_API_KEY`, `VAPI_ASSISTANT_ID`, and `VAPI_PHONE_NUMBER_ID` to the
   existing account values. Set `VAPI_PUBLIC_PHONE_NUMBER` to the dialable
   inbound number in E.164 format, and `PHONE_DEFAULT_REGION` to the ISO
   country code used for locally formatted candidate numbers.
2. Set a random, private `VAPI_WEBHOOK_SECRET`. In the Vapi phone-number
   settings, leave the fixed assistant assignment empty so Vapi sends an
   `assistant-request`; configure the number's server URL as
   `https://<your-public-host>/api/screening/webhook` and add the
   `x-vapi-secret` HTTP header with the same secret. The webhook returns the
   saved assistant ID, which preserves its existing voice and instructions.
   Vapi requires an `assistant-request` response within 7.5 seconds.
3. Configure the same server URL and header for call status and end-of-call
   reports. The backend associates a call only when the caller's normalized
   number maps to one candidate with exactly one eligible application and a
   sent screening invitation. Calls with missing or duplicate matches still
   use the existing assistant, but receive no candidate or job context and are
   not saved against a candidate.
4. An eligible CV score triggers the existing email delivery pipeline to send
   a screening invitation only when the candidate has explicitly consented to
   email and has a valid phone number. The invitation includes
   `VAPI_PUBLIC_PHONE_NUMBER`; existing email idempotency prevents repeats.
   Candidate numbers are normalized to E.164 with libphonenumber before
   matching. HR can review inbound calls on the Screening page.
5. The call webhook saves the transcript and summarizes answers only after
   explicit consent is found in the transcript. A recording link is saved only
   after that consent is confirmed. This code does not enable recording; if
   recording is enabled in Vapi, ensure Vapi itself does not record before
   consent or disable recording there.
6. For local testing, expose the API through an HTTPS tunnel and configure the
   public URL in Vapi. Do not test with production candidates. Tests use an
   isolated SQLite database and mocked call/email providers; they do not place
   calls or send emails.

See Vapi's official [server events](https://docs.vapi.ai/server-url/events),
[server URL setup](https://docs.vapi.ai/server-url/setting-server-urls), and
[phone-number API](https://docs.vapi.ai/api-reference/phone-numbers/get).
The authenticated webhook processes the documented `assistant-request`,
`status-update`, and `end-of-call-report` events. Existing assistant dynamic
variables are not overwritten; Vapi's documented `assistant-request` response
selects the saved assistant only.

## Interview scheduling setup

Scheduling starts in safe test mode. Leave `SCHEDULING_TEST_MODE=true` to generate visible test calendar event IDs and test notification statuses without contacting Google Calendar or Resend. The test suite also mocks external integrations. No calendar events or emails are sent until an administrator deliberately changes the backend setting to `false`.

For production integration:

1. Set `GOOGLE_CALENDAR_TIME_ZONE` to an IANA time-zone name used for interviewer work hours (for example `America/New_York`), set `SCHEDULING_TEST_MODE=false`, and set `GOOGLE_CALENDAR_CREDENTIALS_FILE` to the server-side service-account JSON file. Never add credential files to source control.
2. Share each interviewer calendar with the service-account email address with permission to make changes. Calendar event records are created on the selected interviewer's calendar. The integration does not add guest attendees; Resend sends separate invitation and interviewer notification emails, avoiding a need for Google Workspace domain-wide delegation.
3. Configure `RESEND_API_KEY` and a verified `EMAIL_FROM_ADDRESS` in the backend environment. These credentials are backend-only and must not be added to the React environment.
4. Restart the API, select an HR-approved candidate and interviewer in the dashboard, find an available slot, review it, check the HR approval control, and click Schedule. The API creates the calendar event before saving the scheduled appointment. Email delivery happens after the database save; delivery failures are visible in the interview's notification status and error field and do not silently appear successful.
5. To reschedule, use the interview's Reschedule action, select a new slot, and approve the change. Cancellation deletes the calendar event before marking the record cancelled. Completed interviews remain stored. Do not use production candidate data to test external integrations.

Availability suggestions are limited to weekdays from 9:00 AM to 5:00 PM in the configured time zone, in 30-minute increments, and are filtered against Google Calendar and local scheduled interviews. HR must explicitly approve each schedule or reschedule; the system does not make hiring decisions.

Official integration references: Google Calendar [FreeBusy query](https://developers.google.com/calendar/api/v3/reference/freebusy/query), [events insert](https://developers.google.com/calendar/api/v3/reference/events/insert), [events update](https://developers.google.com/calendar/api/v3/reference/events/update), and [events delete](https://developers.google.com/calendar/api/v3/reference/events/delete); Resend [send email API](https://resend.com/docs/api-reference/emails/send-email).

## Backend API endpoints

Open `http://127.0.0.1:8000/docs` to try the endpoints interactively:

- `GET /` and `GET /health` — API welcome and health checks.
- `POST /api/jobs`, `GET /api/jobs`, `GET/PUT/DELETE /api/jobs/{job_id}` — create, list, retrieve, update, and delete jobs. Job records include title, department, description, required and preferred skills, experience, education, employment type, location, vacancy count, and draft/open/closed status.
- `POST /api/candidates`, `GET /api/candidates`, `GET/PUT/DELETE /api/candidates/{candidate_id}` — register, list, retrieve, update, and delete candidates. Candidates with uploaded resumes must have those resume records removed first.
- `POST /api/candidates/{candidate_id}/approve` — explicitly record HR approval before screening or interview scheduling.
- `POST /api/applications`, `GET /api/applications`, `GET/PATCH/DELETE /api/applications/{application_id}` — link a candidate with a job and manage its HR-tracked status.
- `GET /api/resumes`, `POST /api/resumes/upload`, `DELETE /api/resumes/{resume_id}` — list resume evaluation records, upload, and remove a PDF, DOCX, or TXT resume as multipart form data with `candidate_id`, selected `job_id`, and `file`. Uploads are limited to 10 MB; scanned/image-only PDFs require OCR before upload.
- `POST /api/resumes/{resume_id}/evaluate`, `GET /api/resumes/{resume_id}/score` — parse a resume, score job-related evidence using the 40/25/20/10/5 rubric, and return a structured result for manual HR review. The selected job is stored on the resume; application-linked resumes must use the application's job. Results, extracted text, status, evidence, and rubric breakdown are stored in PostgreSQL. Scoring and explanations run locally; CV content is not sent to a paid LLM.
- `POST /api/screening/{candidate_id}/start`, `GET /api/screening/{candidate_id}`, `GET /api/screening`, `GET /api/screening/records/{screening_id}` — manually initiate a consent-confirmed screening for an HR-approved candidate and a specific application; list and review inbound or outbound screening records with status, transcript, answers, and HR summary.
- `POST /api/screening/webhook` — authenticated Vapi call-status and end-of-call event receiver. Vapi must send the configured `x-vapi-secret` header.
- `GET /api/interviews/interviewers`, `GET /api/interviews/available-slots`, `POST /api/interviews/schedule`, `GET /api/interviews`, `PUT /api/interviews/{interview_id}/reschedule`, `PATCH/DELETE /api/interviews/{interview_id}` — find calendar slots, create/reschedule/cancel interviews with HR approval, and view calendar/email status.

Validation errors return HTTP 422, missing records return HTTP 404, duplicates/conflicts or unapproved stage transitions return HTTP 409, and unavailable integrations return HTTP 502. AI results are advisory, and this backend does not automatically reject candidates. Candidate text is treated as untrusted data; evaluation excludes obvious instruction lines and protected-trait fields and uses only job-related evidence. Screening transcripts are also untrusted input; summaries are restricted to job-related answers and never evaluate voice, accent, emotion, personality, or protected traits. Authentication and authorization for HR approval are not implemented yet; do not expose this starter API publicly.

Run the backend tests from the `backend/` directory. Tests use an isolated in-memory SQLite database and do not require a running PostgreSQL server:

```powershell
python -m pytest ..\tests
```

## Frontend setup

In another terminal:

```powershell
cd frontend
npm install
Copy-Item .env.example .env
npm run dev
```

Vite prints the local frontend URL when it starts.

The React Router dashboard provides Dashboard, Jobs, Candidates, Resume Evaluation, Screening, Interviews, and Settings sections. All API requests are centralized in `frontend/src/services/api.js`; set `VITE_API_BASE_URL` in `frontend/.env` to the FastAPI API base URL. Resume upload and evaluation use the existing resume API, while the candidates page uses `GET /api/resumes` to display saved match scores. Settings displays only browser-local profile preferences because the backend does not currently have an authenticated user profile or integration-health endpoint.

## Remaining implementation

- Database migrations for future schema changes; startup currently creates missing tables only.
- Authentication and authorization for HR accounts and approval actions. Do
  not expose the dashboard/API publicly until HR authentication is implemented.
- Automated UI tests, operational migrations for remaining legacy schemas, and production deployment configuration.
