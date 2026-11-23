import { useEffect, useMemo, useState } from "react";
import {
  ArrowRight, BriefcaseBusiness, CalendarClock, CheckCircle2, Clock3,
  FileText, LogOut, MapPin, RefreshCw, ShieldCheck, Sparkles, UploadCloud,
  Video, XCircle,
} from "lucide-react";
import { api } from "../services/api";
import BrowserConversation from "../components/BrowserConversation";
import "../candidate-portal.css";

const statusText = (value = "") => value.replaceAll("_", " ").replace(/\b\w/g, (letter) => letter.toUpperCase());
const dateText = (value) => value ? new Date(value).toLocaleDateString() : "—";

export default function CandidatePortalPage() {
  const [jobs, setJobs] = useState([]);
  const [applications, setApplications] = useState([]);
  const [screenings, setScreenings] = useState([]);
  const [selectedJob, setSelectedJob] = useState(null);
  const [phone, setPhone] = useState("");
  const [notes, setNotes] = useState("");
  const [emailConsent, setEmailConsent] = useState(false);
  const [resume, setResume] = useState(null);
  const [session, setSession] = useState(null);
  const [activeScreeningId, setActiveScreeningId] = useState("");
  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");

  async function load(showLoader = false) {
    if (showLoader) setLoading(true);
    try {
      const [jobRows, applicationRows, screeningRows] = await Promise.all([
        api.getPublicJobs(), api.getMyApplications(), api.getMyScreenings(),
      ]);
      setJobs(jobRows);
      setApplications(applicationRows);
      setScreenings(screeningRows);
      setError("");
    } catch (requestError) {
      setError(requestError.message || "We could not load your candidate portal.");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => { load(true); }, []);
  useEffect(() => {
    const timer = window.setInterval(() => load(false), 12000);
    return () => window.clearInterval(timer);
  }, []);

  const activeScreenings = useMemo(
    () => screenings.filter((item) => ["queued", "ringing", "in_progress"].includes(item.status)),
    [screenings],
  );
  const pendingScreenings = activeScreenings.filter((item) => item.status === "queued");
  const email = localStorage.getItem("hireflow.email") || "";

  async function apply(event) {
    event.preventDefault();
    if (!selectedJob || !resume) {
      setError("Please attach your CV before submitting the application.");
      return;
    }
    setSubmitting(true);
    setError("");
    setMessage("");
    try {
      const application = await api.applyForJob({
        job_id: selectedJob.id,
        phone,
        details: notes ? { notes } : {},
        email_consent: emailConsent,
      });
      await api.uploadMyResume(application.id, resume);
      setMessage("Your application has been submitted successfully.");
      setSelectedJob(null);
      setPhone("");
      setNotes("");
      setEmailConsent(false);
      setResume(null);
      await load();
    } catch (requestError) {
      setError(requestError.message || "Your application could not be submitted.");
    } finally {
      setSubmitting(false);
    }
  }

  async function startScreening(screening) {
    setError("");
    setMessage("");
    try {
      const browserSession = await api.createBrowserSession(screening.id, "voice", true);
      setActiveScreeningId(screening.id);
      setSession(browserSession);
    } catch (requestError) {
      setError(requestError.message || "The screening session could not be opened.");
    }
  }

  function logout() {
    localStorage.removeItem("hireflow.accessToken");
    localStorage.removeItem("hireflow.role");
    localStorage.removeItem("hireflow.email");
    window.location.assign("/login");
  }

  return (
    <main className="candidate-shell">
      <header className="candidate-topbar">
        <a className="candidate-brand" href="/candidate"><span className="candidate-brand-mark">Z</span><span><strong>ZETECH</strong><small>Candidate workspace</small></span></a>
        <div className="candidate-account"><span className="candidate-account-email">{email}</span><button type="button" className="candidate-logout" onClick={logout}><LogOut size={16}/> Log out</button></div>
      </header>

      <section className="candidate-hero">
        <div><p className="candidate-eyebrow"><Sparkles size={15}/> YOUR CAREER JOURNEY</p><h1>Find work that moves you forward.</h1><p>Explore opportunities, track your applications, and complete your AI screening when invited.</p></div>
        <div className="candidate-hero-art"><BriefcaseBusiness size={58}/><span>Opportunities start here</span></div>
      </section>

      {pendingScreenings.length > 0 && (
        <section className="candidate-alert" role="status">
          <span className="candidate-alert-icon"><Video size={21}/></span>
          <div><strong>You have an AI screening invitation</strong><p>{pendingScreenings.length} screening session{pendingScreenings.length > 1 ? "s are" : " is"} ready. Open your invitation below when you're somewhere quiet and ready to speak.</p></div>
          <a href="#candidate-screenings" className="candidate-alert-link">View invitation <ArrowRight size={15}/></a>
        </section>
      )}

      {message && <div className="candidate-message success" role="status"><CheckCircle2 size={17}/>{message}</div>}
      {error && <div className="candidate-message error" role="alert"><XCircle size={17}/>{error}</div>}

      <section className="candidate-stats">
        <article><span className="candidate-stat-icon"><BriefcaseBusiness size={18}/></span><div><strong>{applications.length}</strong><small>Applications submitted</small></div></article>
        <article><span className="candidate-stat-icon violet"><Clock3 size={18}/></span><div><strong>{applications.filter((item) => ["pending_review", "over_agent_review"].includes(item.status)).length}</strong><small>Under review</small></div></article>
        <article><span className="candidate-stat-icon green"><Video size={18}/></span><div><strong>{activeScreenings.length}</strong><small>Screenings to complete</small></div></article>
      </section>

      <div className="candidate-content-grid">
        <section className="candidate-main-column">
          <div className="candidate-section-heading"><div><p className="candidate-eyebrow">EXPLORE ZETECH</p><h2>Open opportunities</h2><p>Choose a role that matches your skills and interests.</p></div><button className="candidate-refresh" type="button" onClick={() => load(true)} disabled={loading}><RefreshCw size={15}/> Refresh</button></div>
          {loading ? <div className="candidate-empty">Loading opportunities…</div> : jobs.length === 0 ? <div className="candidate-empty">There are no open positions right now. Please check again later.</div> : (
            <div className="candidate-job-list">
              {jobs.map((job) => {
                const alreadyApplied = applications.some((application) => application.job_id === job.id);
                return <article className="candidate-job-card" key={job.id}>
                  <div className="candidate-job-icon"><BriefcaseBusiness size={21}/></div>
                  <div className="candidate-job-copy"><div className="candidate-job-title-row"><h3>{job.title}</h3>{alreadyApplied && <span className="candidate-pill applied">Applied</span>}</div><div className="candidate-job-meta"><span>{job.department || "Technology"}</span><span><MapPin size={13}/>{job.location || "Location not specified"}</span><span>{job.employment_type || "Position"}</span></div><p>{job.description}</p>{job.required_skills?.length > 0 && <div className="candidate-skill-list">{job.required_skills.slice(0, 6).map((skill) => <span key={skill}>{skill}</span>)}</div>}</div>
                  <button type="button" className="candidate-apply-button" disabled={alreadyApplied} onClick={() => {setSelectedJob(job);setError("");setMessage("");}}>{alreadyApplied ? "Applied" : "Apply now"} <ArrowRight size={15}/></button>
                </article>;
              })}
            </div>
          )}

          <section className="candidate-panel candidate-application-panel">
            <div className="candidate-section-heading"><div><p className="candidate-eyebrow">YOUR PROGRESS</p><h2>My applications</h2><p>Follow the progress of every role you've applied for.</p></div></div>
            {applications.length === 0 ? <div className="candidate-empty">Your applications will appear here after you apply for a position.</div> : <div className="candidate-application-list">{applications.map((application) => <article key={application.id}><div className="candidate-application-icon"><FileText size={18}/></div><div className="candidate-application-copy"><strong>{application.job_title || "Job application"}</strong><small>Submitted {dateText(application.applied_at)}</small></div><span className="candidate-pill">{statusText(application.status)}</span></article>)}</div>}
          </section>
        </section>

        <aside className="candidate-side-column" id="candidate-screenings">
          <section className="candidate-panel candidate-screening-panel">
            <div className="candidate-section-heading"><div><p className="candidate-eyebrow">NEXT STEP</p><h2>AI screening</h2><p>Complete your first conversation with our screening assistant.</p></div><span className="candidate-screening-icon"><Video size={19}/></span></div>
            {screenings.length === 0 ? <div className="candidate-screening-empty"><CalendarClock size={28}/><strong>No invitation yet</strong><p>When HR approves your application and prepares a screening, your invitation will appear here.</p></div> : screenings.map((screening) => <article className="candidate-screening-card" key={screening.id}>
              <div className="candidate-screening-card-top"><span className={`candidate-status-dot ${screening.status === "completed" ? "done" : screening.status === "failed" ? "failed" : "waiting"}`}/><strong>{screening.status === "completed" ? "Screening completed" : screening.status === "failed" ? "Session needs attention" : "You're invited to screen"}</strong><span className="candidate-pill">{statusText(screening.status)}</span></div>
              <p>{screening.status === "completed" ? "Thank you. Your responses have been submitted for HR review." : screening.status === "failed" ? "The previous session did not finish. Contact HR if you need a new invitation." : "Start a secure browser conversation with the ZETECH AI screening assistant. You can use voice or text."}</p>
              {(screening.status === "queued" || (screening.status === "in_progress" && !screening.call_id)) && <button type="button" className="candidate-start-call" onClick={() => startScreening(screening)}><Video size={17}/> Start AI screening <ArrowRight size={16}/></button>}
              {screening.status === "completed" && <div className="candidate-complete-note"><ShieldCheck size={16}/> Your screening is complete.</div>}
            </article>)}
            <p className="candidate-privacy-note"><ShieldCheck size={14}/> The assistant asks for your consent before screening and transcription. You can decline or stop at any time.</p>
          </section>
          <section className="candidate-panel candidate-help-panel"><h3>Need help?</h3><p>If you have a question about your application or screening invitation, contact the ZETECH HR team using the email address in your application messages.</p></section>
        </aside>
      </div>

      {selectedJob && <div className="candidate-modal-backdrop" role="presentation" onClick={() => !submitting && setSelectedJob(null)}><section className="candidate-application-modal" role="dialog" aria-modal="true" aria-labelledby="candidate-application-title" onClick={(event) => event.stopPropagation()}>
        <header><div><p className="candidate-eyebrow">APPLICATION FORM</p><h2 id="candidate-application-title">Apply for {selectedJob.title}</h2><p>Complete the details below and attach your latest CV.</p></div><button type="button" aria-label="Close application form" onClick={() => setSelectedJob(null)} disabled={submitting}><XCircle size={20}/></button></header>
        <form onSubmit={apply}>
          <div className="candidate-form-section"><div className="candidate-form-section-title"><span>01</span><div><strong>Contact information</strong><small>Confirm how our HR team can reach you.</small></div></div><div className="candidate-form-grid"><label>Email address<input value={email} readOnly/></label><label>Phone number <span className="candidate-optional">Optional</span><input type="tel" placeholder="+92 3XX XXXXXXX" value={phone} onChange={(event) => setPhone(event.target.value)}/></label></div></div>
          <div className="candidate-form-section"><div className="candidate-form-section-title"><span>02</span><div><strong>Additional information</strong><small>Tell us anything useful about your application.</small></div></div><label className="candidate-full-field">Cover note <span className="candidate-optional">Optional</span><textarea rows="4" placeholder="Briefly describe your relevant skills, experience, or projects…" value={notes} onChange={(event) => setNotes(event.target.value)}/></label></div>
          <div className="candidate-form-section"><div className="candidate-form-section-title"><span>03</span><div><strong>Upload your CV</strong><small>PDF, DOCX, or TXT · Maximum 10 MB</small></div></div><label className="candidate-upload-zone"><UploadCloud size={27}/><strong>{resume ? resume.name : "Choose your CV file"}</strong><span>{resume ? "File selected — ready to upload" : "Click to browse your device"}</span><input required type="file" accept=".pdf,.docx,.txt" onChange={(event) => setResume(event.target.files?.[0] || null)}/></label></div>
          <label className="candidate-consent"><input type="checkbox" checked={emailConsent} onChange={(event) => setEmailConsent(event.target.checked)}/><span>I agree to receive application updates and recruitment-related emails from ZETECH. This is optional and can be changed later.</span></label>
          <div className="candidate-modal-actions"><button type="button" className="candidate-cancel-button" onClick={() => setSelectedJob(null)} disabled={submitting}>Cancel</button><button type="submit" className="candidate-submit-button" disabled={submitting}>{submitting ? "Submitting…" : "Submit application"} <ArrowRight size={16}/></button></div>
        </form>
      </section></div>}

      {session && activeScreeningId && <div className="candidate-conversation-wrap"><div className="candidate-conversation-heading"><div><p className="candidate-eyebrow">LIVE SESSION</p><h2>Your AI screening conversation</h2></div><button type="button" onClick={() => {setSession(null);setActiveScreeningId("");load();}}>Close <XCircle size={16}/></button></div><BrowserConversation screeningId={activeScreeningId} candidate session={session} onFinished={async () => {setSession(null);setActiveScreeningId("");await load();}}/></div>}
      <footer className="candidate-footer"><span>© ZETECH · Candidate workspace</span><span>Fair hiring · Human-led decisions</span></footer>
    </main>
  );
}
