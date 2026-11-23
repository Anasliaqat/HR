import { useEffect, useMemo, useState } from "react";
import { Search, UserRound } from "lucide-react";
import { Link } from "react-router-dom";
import { api } from "../services/api";
import Panel from "../components/Panel";
import {
  EmptyState,
  ErrorMessage,
  LoadingState,
  PageHeading,
  StatusBadge,
} from "../components/Feedback";

function formatDate(value) {
  return value ? new Date(value).toLocaleDateString() : "—";
}

export default function CandidatesPage() {
  const [candidates, setCandidates] = useState([]);
  const [applications, setApplications] = useState([]);
  const [jobs, setJobs] = useState([]);
  const [resumes, setResumes] = useState([]);
  const [search, setSearch] = useState("");
  const [selected, setSelected] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [savingConsent, setSavingConsent] = useState(false);
  const [deletingCandidate, setDeletingCandidate] = useState(false);

  async function loadCandidates() {
    setLoading(true);
    setError("");
    try {
      const results = await Promise.allSettled([
        api.getCandidates(),
        api.getApplications(),
        api.getJobs(),
        api.getResumes(),
      ]);
      const [candidateResult, applicationResult, jobResult, resumeResult] = results;
      if (candidateResult.status === "rejected") throw candidateResult.reason;
      setCandidates(candidateResult.value);
      setApplications(applicationResult.status === "fulfilled" ? applicationResult.value : []);
      setJobs(jobResult.status === "fulfilled" ? jobResult.value : []);
      setResumes(resumeResult.status === "fulfilled" ? resumeResult.value : []);
      if (applicationResult.status === "rejected" || jobResult.status === "rejected" || resumeResult.status === "rejected") {
        setNotice("Candidate profiles loaded. Some application details could not be loaded.");
      }
    } catch (requestError) {
      setError(requestError.message || "Unable to load candidates.");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => { loadCandidates(); }, []);

  const jobById = useMemo(() => new Map(jobs.map((job) => [job.id, job])), [jobs]);
  const resumeByApplication = useMemo(() => {
    const map = new Map();
    for (const resume of resumes) {
      if (resume.application_id && !map.has(resume.application_id)) map.set(resume.application_id, resume);
    }
    return map;
  }, [resumes]);

  const filteredCandidates = candidates.filter((candidate) => {
    const q = search.trim().toLowerCase();
    if (!q) return true;
    const candidateApplications = applications.filter((item) => item.candidate_id === candidate.id);
    return candidate.full_name?.toLowerCase().includes(q)
      || candidate.email?.toLowerCase().includes(q)
      || candidateApplications.some((item) => jobById.get(item.job_id)?.title?.toLowerCase().includes(q));
  });

  async function removeCandidate() {
    if (!selected || !window.confirm(`Delete ${selected.full_name}'s candidate profile and related records? This cannot be undone.`)) return;
    setDeletingCandidate(true);
    setError("");
    try {
      const candidateResumes = resumes.filter((resume) => resume.candidate_id === selected.id);
      for (const resume of candidateResumes) {
        await api.deleteResume(resume.id);
      }
      await api.deleteCandidate(selected.id);
      setResumes((rows) => rows.filter((resume) => resume.candidate_id !== selected.id));
      setSelected(null);
      setNotice("Candidate profile deleted.");
      await loadCandidates();
    } catch (requestError) {
      setError(requestError.message || "Candidate could not be deleted. Check whether related CV records must be removed first.");
    } finally {
      setDeletingCandidate(false);
    }
  }

  async function changeEmailConsent(event) {
    if (!selected) return;
    const emailConsent = event.target.checked;
    setSavingConsent(true);
    setError("");
    try {
      const updated = await api.updateCandidateEmailConsent(selected.id, emailConsent);
      setSelected(updated);
      setCandidates((rows) => rows.map((row) => row.id === updated.id ? updated : row));
      setNotice(emailConsent ? "Candidate email consent saved. You can retry any consent-blocked email from Email Automation." : "Candidate email consent removed.");
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
        description="All saved candidate profiles and their job applications, including candidates who have not applied to a role yet."
        actions={<button type="button" className="button button-secondary" onClick={loadCandidates} disabled={loading}>Refresh</button>}
      />
      <ErrorMessage>{error}</ErrorMessage>
      {notice && <p className="form-note email-notice" role="status">{notice}</p>}
      <Panel className="table-panel" title={`Candidate profiles (${candidates.length})`} subtitle="Candidate records are loaded directly from the database, not only from application rows.">
        <div className="table-toolbar">
          <div className="search-field">
            <Search size={17} />
            <input aria-label="Search candidates" placeholder="Search name, email, or job title…" value={search} onChange={(event) => setSearch(event.target.value)} />
          </div>
        </div>
        {loading ? <LoadingState label="Loading candidates…" /> : filteredCandidates.length === 0 ? (
          <EmptyState title={error ? "Candidate data is unavailable" : "No candidates found"}>
            {error ? "Check the FastAPI connection and refresh." : "Candidate profiles will appear here after an application is submitted."}
          </EmptyState>
        ) : (
          <div className="table-scroll">
            <table className="data-table">
              <thead><tr><th>Candidate</th><th>Applied jobs</th><th>Latest CV score</th><th>Email consent</th><th>Profile</th></tr></thead>
              <tbody>
                {filteredCandidates.map((candidate) => {
                  const rows = applications.filter((item) => item.candidate_id === candidate.id);
                  const scored = rows.map((item) => resumeByApplication.get(item.id)).filter((item) => item?.score != null).sort((a,b) => new Date(b.uploaded_at) - new Date(a.uploaded_at));
                  const latest = scored[0];
                  return (
                    <tr key={candidate.id}>
                      <td><button type="button" className="person-button" onClick={() => setSelected(candidate)}>
                        <span className="person-avatar">{candidate.full_name?.slice(0,1) ?? "C"}</span>
                        <span><strong>{candidate.full_name}</strong><small>{candidate.email}</small></span>
                      </button></td>
                      <td>{rows.length ? rows.map((item) => jobById.get(item.job_id)?.title ?? "Unknown job").join(", ") : "No application yet"}</td>
                      <td>{latest ? <span className="score-pill">{latest.score}/100</span> : "Not evaluated"}</td>
                      <td><StatusBadge>{candidate.email_consent ? "consent recorded" : "not recorded"}</StatusBadge></td>
                      <td><button type="button" className="button button-secondary button-small" onClick={() => setSelected(candidate)}>View profile</button></td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </Panel>

      <Panel className="table-panel" title={`Applications (${applications.length})`} subtitle="Every application is linked to its candidate and saved job.">
        {loading ? <LoadingState label="Loading applications…" /> : applications.length === 0 ? (
          <EmptyState title="No applications yet">Applications appear here after a candidate submits a CV for a job.</EmptyState>
        ) : (
          <div className="table-scroll"><table className="data-table">
            <thead><tr><th>Candidate</th><th>Position</th><th>CV score</th><th>Status</th><th>HR action</th></tr></thead>
            <tbody>{applications.map((application) => {
              const candidate = candidates.find((item) => item.id === application.candidate_id);
              const resume = resumeByApplication.get(application.id);
              const needsReview = application.status === "pending_review" && resume?.score > 50;
              return <tr key={application.id}>
                <td>{candidate?.full_name ?? "Candidate"}<small>{candidate?.email ?? ""}</small></td>
                <td>{jobById.get(application.job_id)?.title ?? "—"}</td>
                <td>{resume?.score == null ? "Not evaluated" : <span className="score-pill">{resume.score}/100</span>}</td>
                <td><StatusBadge>{application.status.replaceAll("_"," ")}</StatusBadge></td>
                <td>{needsReview ? <Link className="text-link" to="/email-automation">Open HR review</Link> : "—"}</td>
              </tr>;
            })}</tbody>
          </table></div>
        )}
      </Panel>

      {selected && (
        <div className="modal-backdrop" role="presentation" onClick={() => setSelected(null)}>
          <section className="detail-drawer" role="dialog" aria-modal="true" aria-labelledby="candidate-detail-title" onClick={(event) => event.stopPropagation()}>
            <button type="button" className="drawer-close" aria-label="Close candidate details" onClick={() => setSelected(null)}>×</button>
            <span className="detail-avatar"><UserRound size={24} /></span>
            <p className="eyebrow">Candidate profile</p>
            <h2 id="candidate-detail-title">{selected.full_name}</h2>
            <p>{selected.email}</p>
            <p>{selected.phone || "No phone number on file"}</p>
            <label className="consent-option email-consent-option">
              <input type="checkbox" checked={Boolean(selected.email_consent)} disabled={savingConsent} onChange={changeEmailConsent} />
              <span>Candidate has explicitly consented to receive recruitment emails.
                {selected.email_consent_at && <small> Recorded {new Date(selected.email_consent_at).toLocaleString()}</small>}
              </span>
            </label>
            <h3>Profile details</h3>
            {Object.keys(selected.details ?? {}).length === 0 ? <p className="muted-copy">No additional profile details provided.</p> : (
              <dl className="detail-list">{Object.entries(selected.details).map(([key,value]) => <div key={key}><dt>{key.replaceAll("_"," ")}</dt><dd>{Array.isArray(value) ? value.join(", ") : String(value ?? "—")}</dd></div>)}</dl>
            )}
            <h3>Applications</h3>
            {applications.filter((item) => item.candidate_id === selected.id).map((item) => (
              <p key={item.id}>{jobById.get(item.job_id)?.title ?? "Job"} · {item.status.replaceAll("_"," ")} · {formatDate(item.applied_at)}</p>
            ))}
            <div className="candidate-delete-row">
              <button type="button" className="button button-danger button-small" onClick={removeCandidate} disabled={deletingCandidate}>
                {deletingCandidate ? "Deleting…" : "Delete candidate"}
              </button>
              <small>This removes the candidate and linked applications. Uploaded CV records may need to be deleted first.</small>
            </div>
            <p className="muted-copy">Manage HR decisions and retry emails in <Link to="/email-automation">Email Automation</Link>.</p>
          </section>
        </div>
      )}
    </>
  );
}
