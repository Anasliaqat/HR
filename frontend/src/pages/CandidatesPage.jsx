import { useEffect, useMemo, useState } from "react";
import { Search, UserRound } from "lucide-react";
import { api } from "../services/api";
import Panel from "../components/Panel";
import {
  EmptyState,
  ErrorMessage,
  LoadingState,
  PageHeading,
  StatusBadge,
} from "../components/Feedback";

const applicationStatuses = [
  "pending_review",
  "screening",
  "interview",
  "hired",
  "withdrawn",
  "rejected_by_hr",
  "rejected",
  "interview_eligible",
  "approved_by_hr",
  "over_agent_review",
];

export default function CandidatesPage() {
  const [candidates, setCandidates] = useState([]);
  const [applications, setApplications] = useState([]);
  const [jobs, setJobs] = useState([]);
  const [resumes, setResumes] = useState([]);
  const [search, setSearch] = useState("");
  const [statusFilter, setStatusFilter] = useState("");
  const [selected, setSelected] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [savingConsent, setSavingConsent] = useState(false);
  const [emailApplications, setEmailApplications] = useState([]);
  const [notice, setNotice] = useState("");

  async function loadCandidates() {
    setLoading(true);
    setError("");
    try {
      const [
        candidateRows,
        applicationRows,
        jobRows,
        resumeRows,
        emailApplicationRows,
      ] =
        await Promise.all([
          api.getCandidates(),
          api.getApplications(),
          api.getJobs(),
          api.getResumes(),
          api.getEmailApplications(),
        ]);
      setCandidates(candidateRows);
      setApplications(applicationRows);
      setJobs(jobRows);
      setResumes(resumeRows);
      setEmailApplications(emailApplicationRows);
    } catch (requestError) {
      setError(requestError.message);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    loadCandidates();
  }, []);

  const candidateById = useMemo(
    () => new Map(candidates.map((candidate) => [candidate.id, candidate])),
    [candidates],
  );
  const jobById = useMemo(
    () => new Map(jobs.map((job) => [job.id, job])),
    [jobs],
  );
  const resumeByApplication = useMemo(() => {
    const latestByApplication = new Map();
    for (const resume of resumes) {
      if (
        resume.application_id &&
        !latestByApplication.has(resume.application_id)
      ) {
        latestByApplication.set(resume.application_id, resume);
      }
    }
    return latestByApplication;
  }, [resumes]);
  const filteredApplications = applications.filter((application) => {
    const candidate = candidateById.get(application.candidate_id);
    const job = jobById.get(application.job_id);
    const query = search.trim().toLowerCase();
    const matchesText =
      !query ||
      candidate?.full_name?.toLowerCase().includes(query) ||
      candidate?.email?.toLowerCase().includes(query) ||
      job?.title?.toLowerCase().includes(query);
    return (
      matchesText &&
      (!statusFilter || application.status === statusFilter)
    );
  });

  async function changeStatus(applicationId, nextStatus) {
    setError("");
    setNotice("");
    try {
      if (nextStatus === "approved_by_hr" || nextStatus === "rejected_by_hr") {
        const application = emailApplications.find(
          (item) => item.application_id === applicationId,
        );
        if (!application) {
          throw new Error("Application workflow details could not be loaded.");
        }
        const decision = nextStatus === "approved_by_hr" ? "approve" : "reject";
        const result = application.review_reason
          ? await api.decideAgentReview(applicationId, decision)
          : await api.recordEmailDecision(applicationId, decision);
        const email = result.email ?? result;
        setNotice(
          email.status === "sent"
            ? `HR ${decision} recorded and email sent to ${email.recipient_email}.`
            : `HR ${decision} recorded. Email status: ${email.status}.${email.error_message ? ` ${email.error_message}` : ""}`,
        );
        await loadCandidates();
        return;
      }
      await api.updateApplication(applicationId, { status: nextStatus });
      await loadCandidates();
    } catch (requestError) {
      setError(requestError.message);
    }
  }

  async function changeEmailConsent(event) {
    const emailConsent = event.target.checked;
    setSavingConsent(true);
    setError("");
    try {
      const updated = await api.updateCandidateEmailConsent(selected.id, emailConsent);
      setSelected(updated);
      setCandidates((rows) =>
        rows.map((candidate) => candidate.id === updated.id ? updated : candidate),
      );
    } catch (requestError) {
      setError(requestError.message);
    } finally {
      setSavingConsent(false);
    }
  }

  return (
    <>
      <PageHeading
        eyebrow="Talent"
        title="Candidates"
        description="Review candidate profiles, application stages, and resume evaluations."
      />
      <ErrorMessage>{error}</ErrorMessage>
      {notice && <p className="form-note email-notice" role="status">{notice}</p>}
      <Panel className="table-panel">
        <div className="table-toolbar">
          <div className="search-field">
            <Search size={17} />
            <input
              aria-label="Search candidates"
              placeholder="Search candidates or roles…"
              value={search}
              onChange={(event) => setSearch(event.target.value)}
            />
          </div>
          <select
            aria-label="Filter by application status"
            className="filter-select"
            value={statusFilter}
            onChange={(event) => setStatusFilter(event.target.value)}
          >
            <option value="">All statuses</option>
            {applicationStatuses.map((status) => (
              <option value={status} key={status}>
                {status.replaceAll("_", " ")}
              </option>
            ))}
          </select>
        </div>
        {loading ? (
          <LoadingState label="Loading candidates…" />
        ) : filteredApplications.length === 0 ? (
          <EmptyState title={error ? "Candidate data is unavailable" : "No matching applications"}>
            {error
              ? "Reconnect to the FastAPI backend and retry."
              : "Candidate applications appear here when available from the API."}
          </EmptyState>
        ) : (
          <div className="table-scroll">
            <table className="data-table">
              <thead>
                <tr>
                  <th>Candidate</th>
                  <th>Applied position</th>
                  <th>Resume score</th>
                  <th>Application status</th>
                  <th>HR review</th>
                </tr>
              </thead>
              <tbody>
                {filteredApplications.map((application) => {
                  const candidate = candidateById.get(application.candidate_id);
                  const resume = resumeByApplication.get(application.id);
                  return (
                    <tr key={application.id}>
                      <td>
                        <button
                          type="button"
                          className="person-button"
                          onClick={() => setSelected(candidate)}
                        >
                          <span className="person-avatar">
                            {candidate?.full_name?.slice(0, 1) ?? "C"}
                          </span>
                          <span>
                            <strong>{candidate?.full_name ?? "Candidate"}</strong>
                            <small>{candidate?.email ?? ""}</small>
                          </span>
                        </button>
                      </td>
                      <td>{jobById.get(application.job_id)?.title ?? "—"}</td>
                      <td>
                        {resume?.score != null ? (
                          <span className="score-pill">{resume.score}/100</span>
                        ) : (
                          <span className="muted-copy">Not evaluated</span>
                        )}
                      </td>
                      <td>
                        <select
                          className="table-status-select"
                          value={application.status}
                          aria-label={`Status for ${candidate?.full_name ?? "candidate"}`}
                          onChange={(event) =>
                            changeStatus(application.id, event.target.value)
                          }
                        >
                          {applicationStatuses.map((status) => (
                            <option value={status} key={status}>
                              {status.replaceAll("_", " ")}
                            </option>
                          ))}
                        </select>
                      </td>
                      <td>
                        <StatusBadge>
                          {["interview_eligible", "approved_by_hr"].includes(
                            application.status,
                          )
                            ? "Application approved"
                            : candidate?.hr_approved
                              ? "HR approved"
                              : "Needs review"}
                        </StatusBadge>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </Panel>

      {selected && (
        <div className="modal-backdrop" role="presentation" onClick={() => setSelected(null)}>
          <section
            className="detail-drawer"
            role="dialog"
            aria-modal="true"
            aria-labelledby="candidate-detail-title"
            onClick={(event) => event.stopPropagation()}
          >
            <button
              type="button"
              className="drawer-close"
              aria-label="Close candidate details"
              onClick={() => setSelected(null)}
            >
              ×
            </button>
            <span className="detail-avatar"><UserRound size={24} /></span>
            <p className="eyebrow">Candidate profile</p>
            <h2 id="candidate-detail-title">{selected.full_name}</h2>
            <p>{selected.email}</p>
            <p>{selected.phone || "No phone number on file"}</p>
            <label className="consent-option email-consent-option">
              <input
                type="checkbox"
                checked={Boolean(selected.email_consent)}
                disabled={savingConsent}
                onChange={changeEmailConsent}
              />
              <span>
                Candidate has consented to receive recruitment emails.
                {selected.email_consent_at && (
                  <small>
                    {" "}Recorded {new Date(selected.email_consent_at).toLocaleString()}
                  </small>
                )}
              </span>
            </label>
            <h3>Profile details</h3>
            {Object.keys(selected.details ?? {}).length === 0 ? (
              <p className="muted-copy">No additional profile details provided.</p>
            ) : (
              <dl className="detail-list">
                {Object.entries(selected.details).map(([key, value]) => (
                  <div key={key}>
                    <dt>{key.replaceAll("_", " ")}</dt>
                    <dd>{typeof value === "string" ? value : JSON.stringify(value)}</dd>
                  </div>
                ))}
              </dl>
            )}
            <p>
              <StatusBadge>
                {selected.hr_approved ? "HR approved" : "Not approved"}
              </StatusBadge>
            </p>
          </section>
        </div>
      )}
    </>
  );
}
