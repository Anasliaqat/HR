import { useEffect, useState } from "react";
import { api } from "../services/api";
import BrowserConversation from "../components/BrowserConversation";

export default function CandidatePortalPage() {
  const [jobs, setJobs] = useState([]);
  const [applications, setApplications] = useState([]);
  const [screenings, setScreenings] = useState([]);
  const [selected, setSelected] = useState("");
  const [phone, setPhone] = useState("");
  const [details, setDetails] = useState("");
  const [consent, setConsent] = useState(false);
  const [resume, setResume] = useState(null);
  const [session, setSession] = useState(null);
  const [activeScreeningId, setActiveScreeningId] = useState("");
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");

  async function load() {
    try {
      const [jobRows, applicationRows, screeningRows] = await Promise.all([
        api.getPublicJobs(), api.getMyApplications(), api.getMyScreenings(),
      ]);
      setJobs(jobRows); setApplications(applicationRows); setScreenings(screeningRows);
    } catch (requestError) { setError(requestError.message); }
  }
  useEffect(() => { load(); }, []);

  async function apply(event) {
    event.preventDefault(); setError(""); setMessage("");
    try {
      const application = await api.applyForJob({
        job_id: selected, phone, details: details ? { notes: details } : {},
        email_consent: consent,
      });
      if (resume) await api.uploadMyResume(application.id, resume);
      setMessage("Application submitted.");
      setSelected(""); setResume(null); await load();
    } catch (requestError) { setError(requestError.message); }
  }

  async function startScreening(screening) {
    setError(""); setMessage("");
    try {
      const data = await api.createBrowserSession(screening.id, "voice", true);
      setActiveScreeningId(screening.id);
      setSession(data);
    } catch (requestError) { setError(requestError.message); }
  }
  function logout() {
    localStorage.removeItem("hireflow.accessToken");
    localStorage.removeItem("hireflow.role");
    location.href = "/login";
  }

  return <main style={{ maxWidth: 900, margin: "40px auto", padding: 24 }}>
    <header style={{ display: "flex", justifyContent: "space-between" }}>
      <div><p className="eyebrow">CANDIDATE PORTAL</p><h1>Find your next opportunity</h1></div>
      <button onClick={logout}>Log out</button>
    </header>
    <section><h2>Open positions</h2>
      {jobs.length ? jobs.map(job => <article key={job.id} style={{ padding: 16, border: "1px solid var(--border)", borderRadius: 12, marginBottom: 12 }}>
        <h3>{job.title}</h3><p>{job.department} · {job.location} · {job.employment_type}</p><p>{job.description}</p>
        <button onClick={() => setSelected(job.id)}>Apply for this job</button>
      </article>) : <p>No published jobs at the moment.</p>}
    </section>
    {selected && <form onSubmit={apply} style={{ display: "grid", gap: 12, maxWidth: 520 }}>
      <h2>Application details</h2>
      <input placeholder="Phone number (optional)" value={phone} onChange={event => setPhone(event.target.value)} />
      <textarea placeholder="Additional information" value={details} onChange={event => setDetails(event.target.value)} />
      <label>Upload CV (PDF, DOCX, or TXT, max 10 MB)
        <input required type="file" accept=".pdf,.docx,.txt" onChange={event => setResume(event.target.files?.[0] || null)} />
      </label>
      <label><input type="checkbox" checked={consent} onChange={event => setConsent(event.target.checked)} /> I agree to receive application-related emails.</label>
      <button className="button button-primary">Submit application</button>
    </form>}
    <section><h2>My applications</h2>
      {applications.map(application => <article key={application.id} style={{ padding: 12, borderBottom: "1px solid var(--border)" }}>
        <strong>{application.job_title}</strong><p>Status: {application.status} · Applied: {new Date(application.applied_at).toLocaleDateString()}</p>
      </article>)}
    </section>
    <section><h2>My AI screening sessions</h2>
      {screenings.length ? screenings.map(screening => <article key={screening.id} style={{ padding: 12, borderBottom: "1px solid var(--border)" }}>
        <strong>Initial screening</strong><p>Status: {screening.status}</p>
        {(screening.status === "queued" || (screening.status === "in_progress" && !screening.call_id)) &&
          <button className="button button-primary" onClick={() => startScreening(screening)}>Open screening session</button>}
        {screening.status === "completed" && <p>Your screening is complete. HR will review your responses.</p>}
      </article>) : <p>No screening invitation is available yet. HR will create one after reviewing your application.</p>}
    </section>
    {session && activeScreeningId && <BrowserConversation
      screeningId={activeScreeningId} candidate session={session}
      onFinished={async () => { setSession(null); await load(); }}
    />}
    {message && <p role="status">{message}</p>}
    {error && <p role="alert" style={{ color: "crimson" }}>{error}</p>}
  </main>;
}
