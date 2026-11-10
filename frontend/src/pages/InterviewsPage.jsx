import { useEffect, useMemo, useState } from "react";
import {
  CalendarClock,
  CalendarPlus,
  ChevronLeft,
  ChevronRight,
  RefreshCw,
} from "lucide-react";
import { api } from "../services/api";
import Panel from "../components/Panel";
import {
  EmptyState,
  ErrorMessage,
  LoadingState,
  PageHeading,
  StatusBadge,
} from "../components/Feedback";

function initialDateTime(daysFromNow, hour) {
  const date = new Date();
  date.setDate(date.getDate() + daysFromNow);
  date.setHours(hour, 0, 0, 0);
  const adjusted = new Date(date.getTime() - date.getTimezoneOffset() * 60000);
  return adjusted.toISOString().slice(0, 16);
}

function localDateTimeToIso(value) {
  return new Date(value).toISOString();
}

function dateKey(value) {
  const date = new Date(value);
  return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, "0")}-${String(date.getDate()).padStart(2, "0")}`;
}

export default function InterviewsPage() {
  const [candidates, setCandidates] = useState([]);
  const [applications, setApplications] = useState([]);
  const [jobs, setJobs] = useState([]);
  const [interviews, setInterviews] = useState([]);
  const [interviewers, setInterviewers] = useState([]);
  const [applicationId, setApplicationId] = useState("");
  const [interviewerEmail, setInterviewerEmail] = useState("");
  const [rangeStart, setRangeStart] = useState(() => initialDateTime(1, 9));
  const [rangeEnd, setRangeEnd] = useState(() => initialDateTime(14, 17));
  const [duration, setDuration] = useState(30);
  const [slots, setSlots] = useState([]);
  const [selectedSlot, setSelectedSlot] = useState("");
  const [reschedulingId, setReschedulingId] = useState("");
  const [testMode, setTestMode] = useState(null);
  const [calendarMonth, setCalendarMonth] = useState(
    () => new Date(new Date().getFullYear(), new Date().getMonth(), 1),
  );
  const [selectedCalendarDate, setSelectedCalendarDate] = useState("");
  const [hrApproved, setHrApproved] = useState(false);
  const [interviewMode, setInterviewMode] = useState("online");
  const [meetingDetails, setMeetingDetails] = useState("");
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");

  async function loadData() {
    setLoading(true);
    setError("");
    try {
      const [
        candidateRows,
        applicationRows,
        jobRows,
        interviewRows,
        interviewerRows,
      ] = await Promise.all([
        api.getCandidates(),
        api.getApplications(),
        api.getJobs(),
        api.getInterviews(),
        api.getInterviewers(),
      ]);
      setCandidates(candidateRows);
      setApplications(applicationRows);
      setJobs(jobRows);
      setInterviews(interviewRows);
      setInterviewers(interviewerRows);
    } catch (requestError) {
      setError(requestError.message);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    loadData();
  }, []);

  const candidateById = useMemo(
    () => new Map(candidates.map((candidate) => [candidate.id, candidate])),
    [candidates],
  );
  const jobById = useMemo(
    () => new Map(jobs.map((job) => [job.id, job])),
    [jobs],
  );
  const approvedApplications = applications.filter(
    (application) =>
      candidateById.get(application.candidate_id)?.hr_approved ||
      ["interview_eligible", "approved_by_hr"].includes(application.status),
  );
  const selectedApplication = approvedApplications.find(
    (application) => application.id === applicationId,
  );

  function resetEditor() {
    setReschedulingId("");
    setSlots([]);
    setSelectedSlot("");
    setHrApproved(false);
    setInterviewMode("online");
    setMeetingDetails("");
    setNotice("");
  }

  async function findSlots() {
    if (!selectedApplication || !interviewerEmail || !rangeStart || !rangeEnd) {
      return;
    }
    setError("");
    setNotice("");
    setSlots([]);
    setSelectedSlot("");
    try {
      const result = await api.getAvailableSlots({
        interviewer_email: interviewerEmail,
        time_min: localDateTimeToIso(rangeStart),
        time_max: localDateTimeToIso(rangeEnd),
        duration_minutes: duration,
        candidate_id: selectedApplication.candidate_id,
        ...(reschedulingId ? { interview_id: reschedulingId } : {}),
      });
      setSlots(result.available_slots);
      setTestMode(result.test_mode);
      if (result.available_slots.length === 0) setNotice(result.message);
    } catch (requestError) {
      setError(requestError.message);
    }
  }

  async function submitSchedule() {
    if (!selectedApplication || !selectedSlot || !hrApproved) return;
    setBusy(true);
    setError("");
    setNotice("");
    try {
      if (reschedulingId) {
        await api.rescheduleInterview(reschedulingId, {
          start_at: selectedSlot,
          duration_minutes: Number(duration),
          hr_approved: true,
        });
      } else {
        await api.scheduleInterview({
          candidate_id: selectedApplication.candidate_id,
          job_id: selectedApplication.job_id,
          interviewer_email: interviewerEmail,
          start_at: selectedSlot,
          duration_minutes: Number(duration),
          interview_mode: interviewMode,
          meeting_details: meetingDetails,
          hr_approved: true,
        });
      }
      const completionNotice = reschedulingId
        ? "Interview rescheduled. Review the notification status below."
        : "Interview scheduled. Review the notification status below.";
      await loadData();
      resetEditor();
      setNotice(completionNotice);
    } catch (requestError) {
      setError(requestError.message);
    } finally {
      setBusy(false);
    }
  }

  async function startReschedule(interview) {
    const application = applications.find(
      (item) =>
        item.candidate_id === interview.candidate_id &&
        item.job_id === interview.job_id,
    );
    if (!application) {
      setError("The related application could not be found.");
      return;
    }
    setError("");
    setNotice("");
    setApplicationId(application.id);
    setInterviewerEmail(interview.interviewer_email);
    setReschedulingId(interview.id);
    setSlots([]);
    setSelectedSlot("");
    setHrApproved(false);
    window.scrollTo({ top: 0, behavior: "smooth" });
  }

  async function updateInterviewStatus(interview, status) {
    if (
      status === "cancelled" &&
      !window.confirm("Cancel this interview and remove its calendar event?")
    ) {
      return;
    }
    setError("");
    setNotice("");
    try {
      await api.updateInterview(interview.id, { status });
      await loadData();
      setNotice(status === "cancelled" ? "Interview cancelled." : "Interview marked completed.");
    } catch (requestError) {
      setError(requestError.message);
    }
  }

  const sortedInterviews = [...interviews].sort(
    (left, right) =>
      new Date(left.start_at).getTime() - new Date(right.start_at).getTime(),
  );
  const scheduledByDate = useMemo(() => {
    const grouped = new Map();
    for (const interview of interviews) {
      if (interview.status !== "scheduled") continue;
      const key = dateKey(interview.start_at);
      grouped.set(key, (grouped.get(key) ?? 0) + 1);
    }
    return grouped;
  }, [interviews]);
  const calendarDays = useMemo(() => {
    const firstOfMonth = new Date(
      calendarMonth.getFullYear(),
      calendarMonth.getMonth(),
      1,
    );
    const start = new Date(firstOfMonth);
    start.setDate(start.getDate() - ((start.getDay() + 6) % 7));
    return Array.from({ length: 42 }, (_, index) => {
      const date = new Date(start);
      date.setDate(start.getDate() + index);
      return date;
    });
  }, [calendarMonth]);
  const visibleInterviews = selectedCalendarDate
    ? sortedInterviews.filter(
        (interview) => dateKey(interview.start_at) === selectedCalendarDate,
      )
    : sortedInterviews;

  return (
    <>
      <PageHeading
        eyebrow="Coordination"
        title="Interviews"
        description="Find a free time, review the details, and explicitly approve the calendar booking."
      />
      <ErrorMessage>{error}</ErrorMessage>
      {notice && <div className="success-banner"><CalendarClock size={18} />{notice}</div>}
      {testMode === true && (
        <div className="notice-banner">
          Test mode is enabled. Calendar availability and email notifications are simulated; no external event or email is created.
        </div>
      )}

      <div className="content-grid content-grid-aside">
        <Panel
          title={reschedulingId ? "Reschedule interview" : "Schedule an interview"}
          subtitle="Availability suggestions use the configured interviewer calendar."
        >
          <label className="field-label" htmlFor="interview-application">
            HR-approved candidate and position
          </label>
          <select
            id="interview-application"
            value={applicationId}
            onChange={(event) => {
              setApplicationId(event.target.value);
              if (!reschedulingId) {
                setSlots([]);
                setSelectedSlot("");
              }
            }}
          >
            <option value="">Select an approved application</option>
            {approvedApplications.map((application) => (
              <option value={application.id} key={application.id}>
                {candidateById.get(application.candidate_id)?.full_name ?? "Candidate"}
                {" · "}
                {jobById.get(application.job_id)?.title ?? "Position"}
              </option>
            ))}
          </select>

          <label className="field-label" htmlFor="interviewer">
            Interviewer email
          </label>
          <input
            id="interviewer"
            list="interviewer-list"
            type="email"
            required
            placeholder="interviewer@company.com"
            value={interviewerEmail}
            onChange={(event) => setInterviewerEmail(event.target.value)}
          />
          <datalist id="interviewer-list">
            {interviewers.map((interviewer) => (
              <option value={interviewer.email} key={interviewer.id}>
                {interviewer.name}
              </option>
            ))}
          </datalist>
          <p className="form-note">
            Interviewers are loaded from active HR/interviewer accounts. You may
            also enter an email directly.
          </p>

          {!reschedulingId && (
            <div className="form-grid">
              <label>
                Interview mode
                <select
                  value={interviewMode}
                  onChange={(event) => setInterviewMode(event.target.value)}
                >
                  <option value="online">Online</option>
                  <option value="on_site">On-site</option>
                </select>
              </label>
              <label>
                {interviewMode === "online" ? "Meeting link" : "Office address"}
                <input
                  required
                  value={meetingDetails}
                  onChange={(event) => setMeetingDetails(event.target.value)}
                />
              </label>
            </div>
          )}

          <div className="form-grid">
            <label>
              Search from
              <input
                type="datetime-local"
                required
                value={rangeStart}
                onChange={(event) => setRangeStart(event.target.value)}
              />
            </label>
            <label>
              Search until
              <input
                type="datetime-local"
                required
                value={rangeEnd}
                onChange={(event) => setRangeEnd(event.target.value)}
              />
            </label>
            <label className="form-full">
              Interview duration
              <select
                value={duration}
                onChange={(event) => setDuration(Number(event.target.value))}
              >
                {[30, 45, 60, 90, 120].map((minutes) => (
                  <option value={minutes} key={minutes}>{minutes} minutes</option>
                ))}
              </select>
            </label>
          </div>
          <div className="form-actions">
            {reschedulingId && (
              <button
                type="button"
                className="button button-secondary"
                onClick={resetEditor}
              >
                Stop rescheduling
              </button>
            )}
            <button
              type="button"
              className="button button-secondary"
              disabled={!selectedApplication || !interviewerEmail}
              onClick={findSlots}
            >
              <RefreshCw size={16} /> Find available times
            </button>
          </div>
          {slots.length > 0 && (
            <div className="slot-section">
              <h3>Available slots</h3>
              <div className="slot-list">
                {slots.map((slot) => (
                  <button
                    type="button"
                    key={slot.start_at}
                    className={`slot-option${selectedSlot === slot.start_at ? " selected" : ""}`}
                    aria-pressed={selectedSlot === slot.start_at}
                    onClick={() => setSelectedSlot(slot.start_at)}
                  >
                    {new Date(slot.start_at).toLocaleString(undefined, {
                      weekday: "short",
                      month: "short",
                      day: "numeric",
                      hour: "numeric",
                      minute: "2-digit",
                    })}
                  </button>
                ))}
              </div>
            </div>
          )}
          <label className="consent-option">
            <input
              type="checkbox"
              checked={hrApproved}
              onChange={(event) => setHrApproved(event.target.checked)}
            />
            <span>I reviewed this time and approve the schedule change.</span>
          </label>
          <button
            type="button"
            className="button button-primary full-width-button"
            disabled={
              !selectedSlot ||
              !hrApproved ||
              busy ||
              (!reschedulingId && !meetingDetails.trim())
            }
            onClick={submitSchedule}
          >
            <CalendarPlus size={17} />
            {busy
              ? "Saving interview…"
              : reschedulingId
                ? "Approve reschedule"
                : "Approve and schedule"}
          </button>
        </Panel>

        <div className="interview-schedule-stack">
        <Panel
          title="Calendar overview"
          subtitle="Scheduled conversations from your hiring calendar"
          action={
            <div className="calendar-actions">
              {selectedCalendarDate && (
                <button
                  type="button"
                  className="button button-quiet button-small"
                  onClick={() => setSelectedCalendarDate("")}
                >
                  Clear date
                </button>
              )}
              <button
                type="button"
                className="icon-button"
                aria-label="Previous month"
                onClick={() => {
                  setSelectedCalendarDate("");
                  setCalendarMonth(
                    (month) => new Date(month.getFullYear(), month.getMonth() - 1, 1),
                  );
                }}
              >
                <ChevronLeft size={16} />
              </button>
              <button
                type="button"
                className="icon-button"
                aria-label="Next month"
                onClick={() => {
                  setSelectedCalendarDate("");
                  setCalendarMonth(
                    (month) => new Date(month.getFullYear(), month.getMonth() + 1, 1),
                  );
                }}
              >
                <ChevronRight size={16} />
              </button>
            </div>
          }
        >
          <div className="calendar-month-label">
            {calendarMonth.toLocaleDateString(undefined, {
              month: "long",
              year: "numeric",
            })}
          </div>
          <div className="calendar-grid" role="group" aria-label="Interview calendar">
            {["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"].map((day) => (
              <span className="calendar-weekday" key={day}>{day}</span>
            ))}
            {calendarDays.map((date) => {
              const key = dateKey(date);
              const count = scheduledByDate.get(key) ?? 0;
              const inMonth = date.getMonth() === calendarMonth.getMonth();
              return (
                <button
                  type="button"
                  key={key}
                  className={`calendar-day${inMonth ? "" : " outside-month"}${count ? " has-interviews" : ""}${selectedCalendarDate === key ? " selected" : ""}`}
                  aria-label={`${date.toLocaleDateString()}${count ? `, ${count} scheduled interviews` : ""}`}
                  aria-pressed={selectedCalendarDate === key}
                  onClick={() =>
                    setSelectedCalendarDate((current) => current === key ? "" : key)
                  }
                >
                  <span>{date.getDate()}</span>
                  {count > 0 && <small>{count}</small>}
                </button>
              );
            })}
          </div>
          <div className="calendar-legend">
            <span className="calendar-legend-dot" /> Scheduled interview
          </div>
        </Panel>

        <Panel
          title="Interview schedule"
          subtitle={
            selectedCalendarDate
              ? `${visibleInterviews.length} interview${visibleInterviews.length === 1 ? "" : "s"} on selected day`
              : `${visibleInterviews.length} recorded interview${visibleInterviews.length === 1 ? "" : "s"}`
          }
          action={
            <button
              type="button"
              className="icon-button"
              aria-label="Refresh interviews"
              onClick={loadData}
            >
              <RefreshCw size={17} />
            </button>
          }
        >
          {loading ? (
            <LoadingState label="Loading interview schedule…" />
          ) : visibleInterviews.length === 0 ? (
            <EmptyState title={error ? "Interview data unavailable" : "No interviews scheduled"}>
              {error
                ? "Reconnect to the FastAPI backend and retry."
                : selectedCalendarDate
                  ? "There are no recorded interviews on this date."
                  : "Approved appointments and their notification status will appear here."}
            </EmptyState>
          ) : (
            <div className="interview-list">
              {visibleInterviews.map((interview) => (
                <article className="interview-card" key={interview.id}>
                  <div className="interview-card-header">
                    <div className="interview-date-mark">
                      <strong>{new Date(interview.start_at).toLocaleDateString(undefined, { day: "2-digit" })}</strong>
                      <span>{new Date(interview.start_at).toLocaleDateString(undefined, { month: "short" })}</span>
                    </div>
                    <div className="interview-main-info">
                      <strong>{candidateById.get(interview.candidate_id)?.full_name ?? "Candidate"}</strong>
                      <span>{jobById.get(interview.job_id)?.title ?? "Position"}</span>
                      <small>{new Date(interview.start_at).toLocaleString()}</small>
                    </div>
                    <StatusBadge>{interview.status}</StatusBadge>
                  </div>
                  <div className="interview-meta">
                    <span>Interviewer: {interview.interviewer_email}</span>
                    <span>
                      Notifications: <strong>{interview.notifications_status}</strong>
                      {interview.test_mode ? " · Test mode" : ""}
                    </span>
                    {interview.notification_error && (
                      <span className="inline-error">{interview.notification_error}</span>
                    )}
                  </div>
                  {interview.status === "scheduled" && (
                    <div className="form-actions interview-actions">
                      <button
                        type="button"
                        className="button button-secondary button-small"
                        onClick={() => startReschedule(interview)}
                      >
                        Reschedule
                      </button>
                      <button
                        type="button"
                        className="button button-secondary button-small"
                        onClick={() => updateInterviewStatus(interview, "cancelled")}
                      >
                        Cancel
                      </button>
                      <button
                        type="button"
                        className="button button-quiet button-small"
                        onClick={() => updateInterviewStatus(interview, "completed")}
                      >
                        Mark completed
                      </button>
                    </div>
                  )}
                </article>
              ))}
            </div>
          )}
        </Panel>
        </div>
      </div>
    </>
  );
}
