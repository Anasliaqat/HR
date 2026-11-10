import { useEffect, useMemo, useState } from "react";
import { PhoneCall, RefreshCw, ShieldCheck } from "lucide-react";
import { api } from "../services/api";
import Panel from "../components/Panel";
import {
  EmptyState,
  ErrorMessage,
  LoadingState,
  PageHeading,
  StatusBadge,
} from "../components/Feedback";

const activeStatuses = ["queued", "ringing", "in_progress"];
const statusLabels = {
  not_started: "Pending",
  queued: "Pending",
  ringing: "In Progress",
  in_progress: "In Progress",
  completed: "Completed",
  failed: "Failed",
};

export default function ScreeningPage() {
  const [candidates, setCandidates] = useState([]);
  const [applications, setApplications] = useState([]);
  const [jobs, setJobs] = useState([]);
  const [screenings, setScreenings] = useState([]);
  const [applicationId, setApplicationId] = useState("");
  const [screeningId, setScreeningId] = useState("");
  const [consentConfirmed, setConsentConfirmed] = useState(false);
  const [report, setReport] = useState(null);
  const [loading, setLoading] = useState(true);
  const [starting, setStarting] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");

  async function loadData() {
    setLoading(true);
    setError("");
    try {
      const [candidateRows, applicationRows, jobRows, screeningRows] = await Promise.all([
        api.getCandidates(),
        api.getApplications(),
        api.getJobs(),
        api.getScreenings(),
      ]);
      setCandidates(candidateRows);
      setApplications(applicationRows);
      setJobs(jobRows);
      setScreenings(screeningRows);
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
    (application) => candidateById.get(application.candidate_id)?.hr_approved,
  );
  const selectedApplication = applications.find(
    (application) => application.id === applicationId,
  );
  const selectedCandidate = selectedApplication
    ? candidateById.get(selectedApplication.candidate_id)
    : null;
  const selectedJob = selectedApplication
    ? jobById.get(selectedApplication.job_id)
    : null;
  const hasActiveScreenings = screenings.some((screening) =>
    activeStatuses.includes(screening.status),
  );

  useEffect(() => {
    if (!hasActiveScreenings) return undefined;
    const timer = window.setInterval(() => {
      api.getScreenings().then(setScreenings).catch((requestError) => {
        setError(requestError.message);
      });
    }, 5000);
    return () => window.clearInterval(timer);
  }, [hasActiveScreenings]);

  useEffect(() => {
    let active = true;
    setReport(null);
    setError("");
    if (!screeningId && !selectedCandidate) {
      return () => { active = false; };
    }
    (screeningId
      ? api.getScreeningRecord(screeningId)
      : api.getScreening(selectedCandidate.id))
      .then((result) => {
        if (active) setReport(result);
      })
      .catch((requestError) => {
        if (active && requestError.status !== 404) {
          setError(requestError.message);
        }
      });
    return () => { active = false; };
  }, [screeningId, selectedCandidate?.id]);

  useEffect(() => {
    if (
      (!screeningId && !selectedCandidate) ||
      !report ||
      !activeStatuses.includes(report.status)
    ) {
      return undefined;
    }
    let active = true;
    const timer = window.setInterval(() => {
      (screeningId
        ? api.getScreeningRecord(screeningId)
        : api.getScreening(selectedCandidate.id))
        .then((latest) => {
          if (active) setReport(latest);
        })
        .catch((requestError) => {
          if (active) setError(requestError.message);
        });
    }, 5000);
    return () => {
      active = false;
      window.clearInterval(timer);
    };
  }, [report?.status, screeningId, selectedCandidate?.id]);

  async function startCall() {
    if (!selectedApplication || !selectedCandidate || !consentConfirmed) return;
    setStarting(true);
    setError("");
    setNotice("");
    try {
      const result = await api.startScreening(selectedCandidate.id, {
        application_id: selectedApplication.id,
        consent_confirmed: true,
      });
      setReport(result);
      setScreeningId(result.id);
      setNotice("Call requested. This action starts a real outbound call when Vapi is configured.");
      setConsentConfirmed(false);
    } catch (requestError) {
      setError(requestError.message);
    } finally {
      setStarting(false);
    }
  }

  async function refreshReport() {
    if (!selectedCandidate && !screeningId) return;
    setError("");
    try {
      setReport(
        await (screeningId
          ? api.getScreeningRecord(screeningId)
          : api.getScreening(selectedCandidate.id)),
      );
    } catch (requestError) {
      setError(requestError.message);
    }
  }

  return (
    <>
      <PageHeading
        eyebrow="Candidate conversations"
        title="Initial screening"
        description="Review job-related screening responses. The assistant does not assess accent, voice, emotion, or personality."
        actions={
          <button
            type="button"
            className="button button-secondary"
            onClick={loadData}
            disabled={loading}
          >
            <RefreshCw size={16} /> Refresh
          </button>
        }
      />
      <ErrorMessage>{error}</ErrorMessage>
      {notice && <div className="success-banner"><ShieldCheck size={18} />{notice}</div>}
      {loading ? (
        <LoadingState label="Loading approved applications…" />
      ) : (
        <div className="content-grid content-grid-aside">
          <Panel title="Start screening call" subtitle="Calls are initiated manually and require confirmed consent.">
            <label className="field-label" htmlFor="screening-application">
              Approved candidate and position
            </label>
            <select
              id="screening-application"
              value={applicationId}
              onChange={(event) => {
                setApplicationId(event.target.value);
                setReport(null);
                setScreeningId("");
                setConsentConfirmed(false);
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
            {approvedApplications.length === 0 && (
              <p className="form-note">
                {error
                  ? "Approved candidate applications could not be loaded."
                  : "No HR-approved applications are available for screening."}
              </p>
            )}
            {selectedCandidate && (
              <div className="candidate-brief">
                <strong>{selectedCandidate.full_name}</strong>
                <span>{selectedCandidate.phone || "Phone number missing"}</span>
                <span>{selectedJob?.title}</span>
              </div>
            )}
            <label className="consent-option">
              <input
                type="checkbox"
                checked={consentConfirmed}
                onChange={(event) => setConsentConfirmed(event.target.checked)}
              />
              <span>
                I confirm the candidate consented to the screening call,
                recording, transcription, and AI summary where configured.
              </span>
            </label>
            <button
              type="button"
              className="button button-primary full-width-button"
              disabled={
                !selectedApplication ||
                !selectedCandidate?.hr_approved ||
                !selectedCandidate?.phone ||
                !consentConfirmed ||
                starting
              }
              onClick={startCall}
            >
              <PhoneCall size={17} />
              {starting ? "Requesting call…" : "Start screening call"}
            </button>
            <p className="form-note">
              Clicking starts a real call when Vapi credentials are configured.
              Use a test number while developing.
            </p>
          </Panel>

          <Panel
            title="Screening report"
            subtitle={
              report?.started_at || report?.created_at
                ? new Date(report.started_at ?? report.created_at).toLocaleString()
                : "Select a candidate to load the latest result."
            }
            action={selectedCandidate && (
              <button
                type="button"
                className="icon-button"
                aria-label="Refresh screening report"
                onClick={refreshReport}
              >
                <RefreshCw size={17} />
              </button>
            )}
          >
            {!report ? (
              <EmptyState title="No report selected">
                Previous call status, summary, answers, and transcript will be shown here.
              </EmptyState>
            ) : (
              <div className="screening-report">
                <div className="report-status-row">
                  <div>
                    <p className="eyebrow">Human review required</p>
                    <h3>{report.candidate_name ?? selectedCandidate?.full_name ?? "Candidate"}</h3>
                  </div>
                  <p className="muted-copy">
                    {report.job_title ?? selectedJob?.title ?? "Position unavailable"}
                    {" · "}
                    {report.phone ?? selectedCandidate?.phone ?? "Phone unavailable"}
                  </p>
                  <StatusBadge>{statusLabels[report.status] ?? report.status}</StatusBadge>
                </div>
                {report.ended_reason && (
                  <p className="muted-copy">Call ended: {report.ended_reason}</p>
                )}
                <p className="report-summary">
                  {report.summary ?? "The screening call is awaiting completion."}
                </p>
                {report.interview_availability && (
                  <p><strong>Interview availability:</strong> {report.interview_availability}</p>
                )}
                {report.job_related_highlights?.length > 0 && (
                  <>
                    <h3>Job-related highlights</h3>
                    <ul className="evidence-list">
                      {report.job_related_highlights.map((highlight, index) => (
                        <li key={`${highlight}-${index}`}>{highlight}</li>
                      ))}
                    </ul>
                  </>
                )}
                {Object.keys(report.answers ?? {}).length > 0 && (
                  <>
                    <h3>Candidate responses</h3>
                    <dl className="detail-list">
                      {Object.entries(report.answers).map(([question, answer]) => (
                        <div key={question}>
                          <dt>{question.replaceAll("_", " ")}</dt>
                          <dd>{answer || "No response recorded."}</dd>
                        </div>
                      ))}
                    </dl>
                  </>
                )}
                {report.transcript && (
                  <details className="transcript-details">
                    <summary>View call transcript</summary>
                    <pre>{report.transcript}</pre>
                  </details>
                )}
                {report.recording_url && (
                  <p className="form-note">
                    <a
                      href={report.recording_url}
                      target="_blank"
                      rel="noreferrer"
                    >
                      Open consented call recording
                    </a>
                  </p>
                )}
                {report.call_id && (
                  <p className="form-note">Call reference: {report.call_id}</p>
                )}
              </div>
            )}
          </Panel>
        </div>
      )}
      {!loading && (
        <Panel
          className="table-panel"
          title={`Candidate screening calls (${screenings.length})`}
          subtitle="Select a call to review its status, summary, answers, and transcript."
        >
          {screenings.length === 0 ? (
            <EmptyState title="No screening calls recorded">
              Calls are listed after a uniquely matched candidate calls the Vapi number.
            </EmptyState>
          ) : (
            <div className="table-scroll">
              <table className="data-table">
                <thead>
                  <tr>
                    <th>Candidate</th>
                    <th>Job title</th>
                    <th>Phone number</th>
                    <th>Call status</th>
                    <th>Call date and time</th>
                    <th>Screening summary</th>
                    <th>Details</th>
                  </tr>
                </thead>
                <tbody>
                  {screenings.map((screening) => (
                    <tr key={screening.id}>
                      <td>{screening.candidate_name}</td>
                      <td>{screening.job_title ?? "—"}</td>
                      <td>{screening.phone ?? "—"}</td>
                      <td><StatusBadge>{statusLabels[screening.status] ?? screening.status}</StatusBadge></td>
                      <td>
                        {new Date(
                          screening.started_at ?? screening.created_at,
                        ).toLocaleString()}
                      </td>
                      <td>{screening.summary ?? "Awaiting call completion."}</td>
                      <td>
                        <button
                          type="button"
                          className="button button-quiet button-small"
                          onClick={() => {
                            setApplicationId(screening.application_id ?? "");
                            setScreeningId(screening.id);
                            setReport(screening);
                            setError("");
                          }}
                        >
                          Review
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </Panel>
      )}
    </>
  );
}
