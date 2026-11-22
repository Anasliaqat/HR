# AI-Powered HR Hiring Automation

A role-based HR hiring application using FastAPI, React, SQLAlchemy, SQLite/PostgreSQL, resume scoring, email automation, and voice screening.

The application currently supports these workflows:

1. HR registration with email verification and candidate registration/login.
2. Public job browsing, candidate applications, and private application status.
3. PDF/DOCX/TXT resume upload and local job-match scoring.
4. HR review, configured low-score rejection, and consent-gated email delivery.
5. Voice screening through ElevenLabs Conversational AI and interview scheduling.

AI scores are advisory. The current email workflow automatically marks scores at or below the configured rejection threshold (default 50) as rejected and attempts a consent-gated rejection email. Other decisions remain with HR.

## Project layout

- `backend/` — FastAPI application, API modules, agents, services, models, and database setup.
- `frontend/` — React application built with Vite.
- `backend/tests/` and `tests/` — backend regression tests.
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

For browser-based ElevenLabs screening, set `ELEVENLABS_API_KEY`,
`ELEVENLABS_AGENT_ID`, and `ELEVENLABS_WEBHOOK_SECRET` in
`backend/.env`. No phone number, Twilio account, or telephony integration
is required. Keep the API key and webhook secret on the backend only.

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

The Email Automation page uses each application's latest CV score. Scores at or below `EMAIL_AUTOMATION_REJECT_BELOW_SCORE` (default 50) are marked rejected and trigger an attempt to send a rejection email. Cases with missing or contradictory evidence may be placed in the **Over Agent Review** queue for HR review. Scores above the rejection threshold remain subject to the configured HR review and interview eligibility rules. All candidate emails require recorded consent and a working SMTP configuration. Missing evaluation evidence is not treated as proof of irrelevance. Scores through `EMAIL_AUTOMATION_REVIEW_THROUGH_SCORE` stay pending HR review without an email; scores above that and below `EMAIL_AUTOMATION_INTERVIEW_FROM_SCORE` require an HR decision and then send the matching email; scores through `EMAIL_AUTOMATION_INTERVIEW_THROUGH_SCORE` become eligible for interview scheduling and receive an invitation only after a real calendar booking is confirmed. Higher scores follow `EMAIL_AUTOMATION_ABOVE_RANGE_ACTION`, which defaults to `pending_review`. These settings in `backend/.env` let HR configure score boundaries and above-range behavior; keep the thresholds ordered and within 0–100. With defaults, 60% stays in HR review, 61–69% require an HR decision, and 70–90% are eligible for interview scheduling. An HR approval is stored as `approved_by_hr`, distinct from score-based `interview_eligible`.

Recruiting emails are sent through authenticated SMTP; `SCHEDULING_TEST_MODE` does not simulate email delivery. Configure `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASSWORD`, and `SMTP_FROM_EMAIL` in `backend/.env`. Delivery requires candidate email consent to be explicitly recorded from the candidate profile. The history stores recipient, template type, subject, body, status, timestamps, provider ID, application, and any delivery error. Failed messages can be retried from the Email Automation page; Idempotency keys help prevent accidental duplicate sends. Deleting application email history from the dashboard hides the records but retains their idempotency data to prevent accidental duplicate delivery.

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

## ElevenLabs browser screening configuration

Screening runs inside the candidate or HR browser using ElevenLabs WebRTC voice. Candidates can also type messages in the same conversation. No outbound phone call or Twilio number is used.

1. Set `ELEVENLABS_API_KEY`, `ELEVENLABS_AGENT_ID`, and `ELEVENLABS_WEBHOOK_SECRET` in `backend/.env`. The agent must be private/authenticated because FastAPI creates a short-lived conversation token for each authorized session.
2. In the ElevenLabs agent's **Security** settings, enable the **System prompt** and **First message** overrides. Configure the agent to support voice conversations and text input. The React SDK passes the following runtime dynamic variables for every session: `company_name`, `candidate_name`, `job_title`, `job_description`, `required_skills`, `screening_questions`, and `screening_id`. Use these names in your agent prompt.
3. The assistant must identify itself as AI and ask the candidate for clear verbal consent to AI screening, transcription, and AI summarization before asking any screening questions. Audio recording is not enabled. If consent is declined, unclear, or withdrawn, stop the conversation immediately. Ask the seven screening questions one at a time. Do not score, rank, hire, reject, promise an interview, or evaluate protected characteristics.
4. In ElevenLabs **Developers / Webhooks**, create a signed post-call webhook at `https://<your-public-host>/api/screening/webhook`. Enable `post_call_transcription`, copy the webhook secret into `ELEVENLABS_WEBHOOK_SECRET`, and keep the endpoint publicly reachable over HTTPS. The backend validates the ElevenLabs signature and only stores the transcript and generates a summary after affirmative consent is found in the transcript.
5. HR creates a screening record from the Screening page. The candidate signs in to the Candidate Portal and clicks **Open screening session**. HR can also start a test session from the Screening page. Both use the same authenticated backend token flow. The authenticated browser endpoint associates the conversation ID with the existing screening database record; the post-call webhook then saves status, transcript, summary, answers, and interview availability.
6. Browser voice requires microphone permission and a secure context (HTTPS in production; localhost is suitable for development). Text messages can be sent in the active voice conversation as an alternative when speaking is inconvenient. ElevenLabs usage still consumes the account's applicable plan credits; avoiding Twilio does not make ElevenLabs processing unlimited or free.

For local webhook testing, expose the backend through an HTTPS tunnel and configure that public URL in ElevenLabs. Never put the ElevenLabs API key in React environment variables or commit secrets.

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
- `POST /api/auth/hr/register`, `POST /api/auth/hr/verify`, `POST /api/auth/candidate/register`, `POST /api/auth/login` — HR verification, candidate registration, and role-based login.
- `GET /api/portal/jobs`, `POST /api/portal/applications`, `GET /api/portal/applications`, `POST /api/portal/applications/{application_id}/resume` — public open jobs and authenticated candidate-owned applications/CV uploads.

- `GET /` and `GET /health` — API welcome and health checks.
- `POST /api/jobs`, `GET /api/jobs`, `GET/PUT/DELETE /api/jobs/{job_id}` — create, list, retrieve, update, and delete jobs. Job records include title, department, description, required and preferred skills, experience, education, employment type, location, vacancy count, and draft/open/closed status.
- `POST /api/candidates`, `GET /api/candidates`, `GET/PUT/DELETE /api/candidates/{candidate_id}` — register, list, retrieve, update, and delete candidates. Candidates with uploaded resumes must have those resume records removed first.
- `POST /api/candidates/{candidate_id}/approve` — explicitly record HR approval before screening or interview scheduling.
- `POST /api/applications`, `GET /api/applications`, `GET/PATCH/DELETE /api/applications/{application_id}` — link a candidate with a job and manage its HR-tracked status.
- `GET /api/resumes`, `POST /api/resumes/upload`, `DELETE /api/resumes/{resume_id}` — list resume evaluation records, upload, and remove a PDF, DOCX, or TXT resume as multipart form data with `candidate_id`, selected `job_id`, and `file`. Uploads are limited to 10 MB; scanned/image-only PDFs require OCR before upload.
- `POST /api/resumes/{resume_id}/evaluate`, `GET /api/resumes/{resume_id}/score` — parse a resume, score job-related evidence using the 40/25/20/10/5 rubric, and return a structured result for manual HR review. The selected job is stored on the resume; application-linked resumes must use the application's job. Results, extracted text, status, evidence, and rubric breakdown are stored in PostgreSQL. Scoring and explanations run locally; CV content is not sent to a paid LLM.
- `POST /api/screening/{candidate_id}/start`, `POST /api/screening/{screening_id}/session`, `POST /api/screening/{screening_id}/conversation`, `GET /api/screening`, `GET /api/screening/records/{screening_id}` — HR prepares and tests browser screening sessions for approved candidates; list and review transcripts, answers, and summaries.\n- `GET /api/screening/candidate/my`, `POST /api/screening/candidate/{screening_id}/session`, `POST /api/screening/candidate/{screening_id}/conversation` — candidate-owned screening sessions, protected by candidate login.
- `POST /api/screening/webhook` — public endpoint protected by ElevenLabs HMAC signature verification; receives post-call transcripts and persists consent-gated results.
- `GET /api/interviews/interviewers`, `GET /api/interviews/available-slots`, `POST /api/interviews/schedule`, `GET /api/interviews`, `PUT /api/interviews/{interview_id}/reschedule`, `PATCH/DELETE /api/interviews/{interview_id}` — find calendar slots, create/reschedule/cancel interviews with HR approval, and view calendar/email status.

Validation errors return HTTP 422, missing records return HTTP 404, duplicates/conflicts or unapproved stage transitions return HTTP 409, and unavailable integrations return HTTP 502. AI results are advisory; the configured low-score rule can automatically mark applications rejected and attempt a consent-gated email. Candidate text is treated as untrusted data; evaluation excludes obvious instruction lines and protected-trait fields and uses only job-related evidence. Screening transcripts are also untrusted input; summaries are restricted to job-related answers and never evaluate voice, accent, emotion, personality, or protected traits. HR and candidate authentication are implemented with password hashing, signed expiring bearer tokens, role-based API guards, candidate-owned application queries, and email verification for the configured HR address.

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

The React application provides separate HR and candidate portals. HR pages include Dashboard, Jobs, Candidates, Resume Evaluation, Screening, Interviews, Email Automation, and Settings. Candidates can browse open jobs, apply, upload a CV, and view only their own application statuses. All API requests are centralized in `frontend/src/services/api.js`; set `VITE_API_BASE_URL` in `frontend/.env` to the FastAPI API base URL. Resume upload and evaluation use the existing resume API, while the candidates page uses `GET /api/resumes` to display saved match scores. Settings displays only browser-local profile preferences because the backend does not currently have an authenticated user profile or integration-health endpoint.

## Remaining implementation

- Database migrations for future schema changes; startup currently creates missing tables only.
- Add automated frontend and browser end-to-end tests for HR and candidate journeys.
- Add request rate limiting and stronger operational security controls before public deployment.
- Configure the private ElevenLabs agent, enable System Prompt and First Message overrides, and configure its signed post-call transcription webhook before testing. No phone number is needed.
- Automated UI tests, operational migrations for remaining legacy schemas, and production deployment configuration.
