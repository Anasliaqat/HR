import { useEffect, useMemo, useState } from "react";
import {
  ArrowUpRight,
  CheckCircle2,
  FileSearch,
  FileText,
  FileUp,
  LoaderCircle,
  Search,
  Trash2,
} from "lucide-react";
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

function matchLabel(score) {
  if (score >= 80) return "Strong Match";
  if (score >= 60) return "Partial Match";
  return "Low Match";
}

function profileField(value) {
  return typeof value === "string" || typeof value === "number"
    ? String(value)
    : "";
}

function profileSkills(value) {
  if (Array.isArray(value)) return value.map(profileField).filter(Boolean).join(", ");
  return profileField(value);
}

function EvaluationTags({ values, variant, empty }) {
  return values?.length ? (
    <div className="tag-list">
      {values.map((value) => (
        <span className={`tag ${variant}`} key={value}>
          {value}
        </span>
      ))}
    </div>
  ) : (
    <p className="muted-copy">{empty}</p>
  );
}

function SkillMatchReasons({ reasons, matched }) {
  const entries = Object.entries(reasons ?? {}).filter(
    ([, reason]) =>
      (reason !== "No supporting CV evidence found.") === matched,
  );
  if (!entries.length) return null;

  return (
    <ul className="cv-skill-match-reasons">
      {entries.map(([skill, reason]) => (
        <li key={skill}>
          <strong>{skill}</strong>
          <span>{reason}</span>
        </li>
      ))}
    </ul>
  );
}

export default function ResumeEvaluationPage() {
  const [candidates, setCandidates] = useState([]);
  const [applications, setApplications] = useState([]);
  const [jobs, setJobs] = useState([]);
  const [resumes, setResumes] = useState([]);
  const [candidateId, setCandidateId] = useState("");
  const [jobId, setJobId] = useState("");
  const [candidateForm, setCandidateForm] = useState({
    fullName: "",
    email: "",
    phone: "",
    education: "",
    skills: "",
    experience: "",
    portfolio: "",
  });
  const [file, setFile] = useState(null);
  const [uploadProgress, setUploadProgress] = useState(null);
  const [draggingFile, setDraggingFile] = useState(false);
  const [selectedResumeId, setSelectedResumeId] = useState("");
  const [trackingResumeId, setTrackingResumeId] = useState("");
  const [comparisonIds, setComparisonIds] = useState([]);
  const [evaluation, setEvaluation] = useState(null);
  const [processingStage, setProcessingStage] = useState("");
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [deletingResumeId, setDeletingResumeId] = useState("");
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");

  async function loadData() {
    setLoading(true);
    setError("");
    try {
      const [candidateRows, applicationRows, jobRows, resumeRows] =
        await Promise.all([
          api.getCandidates(),
          api.getApplications(),
          api.getJobs(),
          api.getResumes(),
        ]);
      setCandidates(candidateRows);
      setApplications(applicationRows);
      setJobs(jobRows);
      setResumes(resumeRows);
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
  const currentResume = resumes.find((resume) => resume.id === selectedResumeId);
  const displayedCandidateId = currentResume?.candidate_id ?? candidateId;
  const selectedCandidate = candidateById.get(displayedCandidateId);
  const selectedJob = jobById.get(jobId);
  useEffect(() => {
    if (!trackingResumeId || trackingResumeId !== selectedResumeId) return undefined;

    let active = true;
    let timer;
    async function checkEvaluationStatus() {
      try {
        const status = await api.getResumeStatus(trackingResumeId);
        if (!active) return;
        setResumes((current) =>
          current.map((resume) =>
            resume.id === status.id ? status : resume,
          ),
        );

        if (status.evaluation_status === "completed") {
          const result = await api.getResumeScore(trackingResumeId);
          if (!active) return;
          setEvaluation(result);
          setNotice(
            "CV evaluation is complete. Review the backend evidence before making any decision.",
          );
          setTrackingResumeId("");
          return;
        }
        if (status.evaluation_status === "failed") {
          setError(
            status.evaluation_details?.error ??
              "The backend agent could not complete this CV evaluation. You can retry it.",
          );
          setTrackingResumeId("");
          return;
        }

        timer = window.setTimeout(checkEvaluationStatus, 1500);
      } catch (requestError) {
        if (!active) return;
        setError(`Unable to refresh evaluation status. ${requestError.message}`);
        timer = window.setTimeout(checkEvaluationStatus, 5000);
      }
    }

    checkEvaluationStatus();
    return () => {
      active = false;
      window.clearTimeout(timer);
    };
  }, [selectedResumeId, trackingResumeId]);

  const canUpload =
    Boolean(file && jobId && candidateForm.fullName.trim() && candidateForm.email.trim()) &&
    !busy;
  const canEvaluate =
    Boolean(selectedResumeId && currentResume && jobId) &&
    !busy &&
    currentResume?.evaluation_status !== "processing";

  function chooseCandidate(value) {
    setCandidateId(value);
    setTrackingResumeId("");
    const candidate = candidateById.get(value);
    const details = candidate?.details ?? {};
    setCandidateForm({
      fullName: candidate?.full_name ?? "",
      email: candidate?.email ?? "",
      phone: candidate?.phone ?? "",
      education: profileField(details.education),
      skills: profileSkills(details.skills),
      experience: profileField(details.experience),
      portfolio: profileField(details.portfolio),
    });
    setSelectedResumeId("");
    setEvaluation(null);
    setFile(null);
    setNotice("");
  }

  function chooseJob(value) {
    setJobId(value);
    setEvaluation(null);
    setNotice("");
  }

  function chooseResumeFile(selected) {
    if (!selected) return;
    const extension = selected.name.split(".").pop()?.toLowerCase();
    if (!["pdf", "docx"].includes(extension)) {
      setFile(null);
      setError("Choose a PDF or DOCX resume.");
      return;
    }
    if (selected.size > 10 * 1024 * 1024) {
      setFile(null);
      setError("CV exceeds the 10 MB upload limit.");
      return;
    }
    setFile(selected);
    setError("");
    setEvaluation(null);
    setNotice("");
    setUploadProgress(null);
  }

  async function uploadResume(event) {
    event.preventDefault();
    if (!file || !jobId || !candidateForm.fullName.trim() || !candidateForm.email.trim()) return;

    setBusy(true);
    setError("");
    setNotice("");
    setEvaluation(null);
    setUploadProgress(0);
    setProcessingStage("Saving candidate and application…");
    let candidateSaved = false;
    let applicationSaved = false;
    try {
      const candidatePayload = {
        full_name: candidateForm.fullName.trim(),
        email: candidateForm.email.trim(),
        phone: candidateForm.phone.trim() || null,
        details: {
          ...(candidateById.get(candidateId)?.details ?? {}),
          education: candidateForm.education.trim(),
          skills: candidateForm.skills
            .split(",")
            .map((skill) => skill.trim())
            .filter(Boolean),
          experience: candidateForm.experience.trim(),
          portfolio: candidateForm.portfolio.trim(),
        },
      };
      let candidate;
      if (candidateId) {
        candidate = await api.updateCandidate(candidateId, candidatePayload);
      } else {
        try {
          candidate = await api.createCandidate(candidatePayload);
        } catch (requestError) {
          if (requestError.status !== 409) throw requestError;
          const existingCandidates = await api.getCandidates();
          candidate = existingCandidates.find(
            (item) => item.email.toLowerCase() === candidatePayload.email.toLowerCase(),
          );
          if (!candidate) throw requestError;
          candidate = await api.updateCandidate(candidate.id, candidatePayload);
        }
      }
      candidateSaved = true;
      setCandidateId(candidate.id);
      setCandidates((current) => [
        candidate,
        ...current.filter((item) => item.id !== candidate.id),
      ]);

      let application;
      try {
        application = await api.createApplication({
          candidate_id: candidate.id,
          job_id: jobId,
        });
      } catch (requestError) {
        if (requestError.status !== 409) throw requestError;
        const existingApplications = await api.getApplications();
        application = existingApplications.find(
          (item) => item.candidate_id === candidate.id && item.job_id === jobId,
        );
        if (!application) throw requestError;
      }
      applicationSaved = true;

      const formData = new FormData();
      formData.set("candidate_id", candidate.id);
      formData.set("application_id", application.id);
      formData.set("job_id", jobId);
      formData.set("file", file);
      setProcessingStage("Uploading CV…");
      const uploaded = await api.uploadResume(formData, (progressEvent) => {
        if (progressEvent.total) {
          setUploadProgress(
            Math.min(99, Math.round((progressEvent.loaded / progressEvent.total) * 100)),
          );
        }
      });
      setUploadProgress(100);
      setResumes((current) => [
        uploaded,
        ...current.filter((resume) => resume.id !== uploaded.id),
      ]);
      setSelectedResumeId(uploaded.id);
      setUploadProgress(100);
      setProcessingStage("Starting CV evaluation…");
      const queuedResume = await api.startResumeEvaluation(uploaded.id, {
        job_id: jobId,
      });
      setResumes((current) => [
        queuedResume,
        ...current.filter((resume) => resume.id !== queuedResume.id),
      ]);
      setTrackingResumeId(uploaded.id);
      setFile(null);
      setNotice("CV evaluation started. You can follow its live status below.");
    } catch (requestError) {
      const progress = candidateSaved
        ? applicationSaved
          ? "Candidate and application are saved, but CV evaluation did not complete."
          : "Candidate profile is saved, but the application could not be completed."
        : "";
      setError(progress ? `${progress} ${requestError.message}` : requestError.message);
    } finally {
      setBusy(false);
      setProcessingStage("");
      window.setTimeout(() => setUploadProgress(null), 1200);
    }
  }

  async function evaluateResume(event) {
    event.preventDefault();
    if (!jobId || !selectedResumeId) return;

    setBusy(true);
    setError("");
    setNotice("");
    setEvaluation(null);
    setProcessingStage("Starting CV evaluation…");
    try {
      const queuedResume = await api.startResumeEvaluation(selectedResumeId, {
        job_id: jobId,
        force: currentResume?.evaluation_status === "completed",
      });
      setResumes((current) =>
        current.map((resume) =>
          resume.id === queuedResume.id ? queuedResume : resume,
        ),
      );
      if (queuedResume.evaluation_status === "completed") {
        const result = await api.getResumeScore(selectedResumeId);
        setEvaluation(result);
        setNotice("CV evaluation is complete. Review the evidence before making any decision.");
      } else {
        setTrackingResumeId(selectedResumeId);
        setNotice("CV evaluation started. You can follow its live status below.");
      }
    } catch (requestError) {
      setError(requestError.message);
      try {
        setResumes(await api.getResumes());
      } catch (refreshError) {
        setError(
          `${requestError.message} Evaluation history could not be refreshed: ${refreshError.message}`,
        );
      }
    } finally {
      setBusy(false);
      setProcessingStage("");
    }
  }

  async function reviewExistingResume(resume) {
    setError("");
    setNotice("");
    setEvaluation(null);
    setFile(null);
    setSelectedResumeId(resume.id);
    setTrackingResumeId(
      resume.evaluation_status === "processing" ? resume.id : "",
    );
    setCandidateId(resume.candidate_id);
    const candidate = candidateById.get(resume.candidate_id);
    const details = candidate?.details ?? {};
    setCandidateForm({
      fullName: candidate?.full_name ?? "",
      email: candidate?.email ?? "",
      phone: candidate?.phone ?? "",
      education: profileField(details.education),
      skills: profileSkills(details.skills),
      experience: profileField(details.experience),
      portfolio: profileField(details.portfolio),
    });

    const savedJobId =
      resume.job_id ??
      resume.evaluation_details?.job_id ??
      applications.find((application) => application.id === resume.application_id)
        ?.job_id ??
      "";
    setJobId(savedJobId);

    if (resume.score == null) return;

    setBusy(true);
    try {
      const result = await api.getResumeScore(resume.id);
      setEvaluation(result);
      if (result.job_id) setJobId(result.job_id);
    } catch (requestError) {
      setError(requestError.message);
    } finally {
      setBusy(false);
    }
  }

  async function deleteResume(resume) {
    const confirmed = window.confirm(
      `Delete "${resume.filename}" and its saved evaluation and uploaded file? This cannot be undone. The candidate and application records will remain.`,
    );
    if (!confirmed) return;

    setDeletingResumeId(resume.id);
    setError("");
    setNotice("");
    try {
      await api.deleteResume(resume.id);
      setResumes((current) => current.filter((item) => item.id !== resume.id));
      setComparisonIds((current) => current.filter((id) => id !== resume.id));
      if (selectedResumeId === resume.id) {
        setSelectedResumeId("");
        setTrackingResumeId("");
        setEvaluation(null);
      }
      setNotice("The CV evaluation and uploaded resume were deleted.");
    } catch (requestError) {
      setError(`Unable to delete this CV evaluation. ${requestError.message}`);
    } finally {
      setDeletingResumeId("");
    }
  }

  async function approveForScreening() {
    if (!selectedCandidate || !evaluation) return;
    setBusy(true);
    setError("");
    setNotice("");
    try {
      await api.approveCandidate(selectedCandidate.id);
      setNotice(`${selectedCandidate.full_name} is approved for HR screening review.`);
      await loadData();
    } catch (requestError) {
      setError(requestError.message);
    } finally {
      setBusy(false);
    }
  }

  function toggleComparison(resumeId, checked) {
    setComparisonIds((current) =>
      checked
        ? [...new Set([...current, resumeId])]
        : current.filter((id) => id !== resumeId),
    );
  }

  const comparisonResumes = resumes.filter(
    (resume) =>
      comparisonIds.includes(resume.id) &&
      resume.score != null &&
      resume.evaluation_details,
  );

  return (
    <>
      <PageHeading
        eyebrow="AI-POWERED CV REVIEW"
        title="Evaluate a CV"
        description="Submit candidate details and a PDF or DOCX resume for an evidence-based match against a real job opening."
        actions={
          <a className="button button-secondary" href="#cv-application-form">
            Start an evaluation <ArrowUpRight size={16} />
          </a>
        }
      />
      <ErrorMessage>{error}</ErrorMessage>
      {notice && (
        <div className="success-banner">
          <CheckCircle2 size={18} />
          {notice}
        </div>
      )}

      <div className="content-grid content-grid-aside cv-evaluation-layout">
        <div className="evaluation-controls">
          <Panel
            title="Candidate application"
            subtitle="Candidate details and the selected job are saved to your existing HR API."
            className="cv-application-panel"
            id="cv-application-form"
          >
            <div className="cv-workflow-steps" aria-label="CV evaluation workflow">
              <span className="current"><b>01</b> Candidate</span>
              <i />
              <span><b>02</b> Resume</span>
              <i />
              <span><b>03</b> Results</span>
            </div>
            <form onSubmit={file ? uploadResume : evaluateResume}>
              <div className="cv-form-section">
                <div className="cv-section-heading">
                  <span className="cv-section-number">01</span>
                  <span>
                    <strong>Candidate details</strong>
                    <small>Enter a new profile or select an existing one.</small>
                  </span>
                </div>
                <label className="field-label" htmlFor="resume-candidate">
                  Existing candidate
                </label>
                <select
                  id="resume-candidate"
                  value={candidateId}
                  onChange={(event) => chooseCandidate(event.target.value)}
                >
                  <option value="">Create a new candidate profile</option>
                  {candidates.map((candidate) => (
                    <option key={candidate.id} value={candidate.id}>
                      {candidate.full_name} · {candidate.email}
                    </option>
                  ))}
                </select>

                <div className="cv-form-grid">
                  <label>
                    Full name <span className="required">*</span>
                    <input
                      required
                      autoComplete="name"
                      maxLength={200}
                      placeholder="Candidate's full name"
                      value={candidateForm.fullName}
                      onChange={(event) =>
                        setCandidateForm({ ...candidateForm, fullName: event.target.value })
                      }
                    />
                  </label>
                  <label>
                    Email address <span className="required">*</span>
                    <input
                      required
                      type="email"
                      autoComplete="email"
                      maxLength={320}
                      placeholder="name@example.com"
                      value={candidateForm.email}
                      onChange={(event) =>
                        setCandidateForm({ ...candidateForm, email: event.target.value })
                      }
                    />
                  </label>
                  <label>
                    Phone number
                    <input
                      type="tel"
                      autoComplete="tel"
                      maxLength={40}
                      placeholder="+1 (555) 000-0000"
                      value={candidateForm.phone}
                      onChange={(event) =>
                        setCandidateForm({ ...candidateForm, phone: event.target.value })
                      }
                    />
                  </label>
                  <label>
                    Education
                    <input
                      maxLength={500}
                      placeholder="Degree, institution, or certification"
                      value={candidateForm.education}
                      onChange={(event) =>
                        setCandidateForm({ ...candidateForm, education: event.target.value })
                      }
                    />
                  </label>
                  <label className="cv-form-full">
                    Skills
                    <input
                      placeholder="Python, SQL, project management"
                      value={candidateForm.skills}
                      onChange={(event) =>
                        setCandidateForm({ ...candidateForm, skills: event.target.value })
                      }
                    />
                    <small>Separate skills with commas. The agent evaluates the uploaded CV against the job requirements.</small>
                  </label>
                  <label className="cv-form-full">
                    Relevant experience
                    <textarea
                      rows={3}
                      maxLength={5000}
                      placeholder="Briefly describe relevant roles, responsibilities, or years of experience"
                      value={candidateForm.experience}
                      onChange={(event) =>
                        setCandidateForm({ ...candidateForm, experience: event.target.value })
                      }
                    />
                  </label>
                  <label className="cv-form-full">
                    Portfolio or LinkedIn
                    <input
                      type="url"
                      maxLength={1000}
                      placeholder="https://"
                      value={candidateForm.portfolio}
                      onChange={(event) =>
                        setCandidateForm({ ...candidateForm, portfolio: event.target.value })
                      }
                    />
                  </label>
                </div>
              </div>

              <div className="cv-form-section">
                <div className="cv-section-heading">
                  <span className="cv-section-number">02</span>
                  <span>
                    <strong>Choose a job</strong>
                    <small>The AI compares resume evidence to the job description and requirements.</small>
                  </span>
                </div>
                <label className="field-label" htmlFor="resume-job">
                  Job to evaluate against <span className="required">*</span>
                </label>
                <select
                  id="resume-job"
                  required
                  value={jobId}
                  onChange={(event) => chooseJob(event.target.value)}
                >
                  <option value="">Select a job</option>
                  {jobs.map((job) => (
                    <option key={job.id} value={job.id}>
                      {job.title}{job.department ? ` · ${job.department}` : ""}
                    </option>
                  ))}
                </select>
                {selectedJob && (
                  <div className="selected-job-card">
                    <div className="selected-job-heading">
                      <strong>{selectedJob.title}</strong>
                      <span>{selectedJob.department || "Open role"}</span>
                    </div>
                    <p>{selectedJob.description}</p>
                    <h3>Required skills</h3>
                    <EvaluationTags
                      values={selectedJob.required_skills}
                      variant="tag-blue"
                      empty="No required skills listed for this job."
                    />
                  </div>
                )}
                {jobs.length === 0 && !loading && (
                  <p className="cv-inline-note">
                    No jobs are available from the API yet. <Link to="/jobs">Create a job</Link> before evaluating a CV.
                  </p>
                )}
              </div>

              <div className="cv-form-section">
                <div className="cv-section-heading">
                  <span className="cv-section-number">03</span>
                  <span>
                    <strong>Upload resume</strong>
                    <small>PDF or DOCX · 10 MB maximum</small>
                  </span>
                </div>

              {!selectedResumeId && (
                <>
                  <label
                    className={`upload-dropzone${draggingFile ? " is-dragging" : ""}`}
                    htmlFor="resume-file"
                    onDragOver={(event) => {
                      event.preventDefault();
                      setDraggingFile(true);
                    }}
                    onDragLeave={() => setDraggingFile(false)}
                    onDrop={(event) => {
                      event.preventDefault();
                      setDraggingFile(false);
                      chooseResumeFile(event.dataTransfer.files?.[0]);
                    }}
                  >
                    <span className="upload-icon">
                      <FileUp size={22} />
                    </span>
                    <strong>{file?.name ?? "Drop a resume here or browse files"}</strong>
                    <small>PDF or DOCX · 10 MB maximum</small>
                    <input
                      id="resume-file"
                      type="file"
                      accept=".pdf,.docx,application/pdf,application/vnd.openxmlformats-officedocument.wordprocessingml.document"
                      onChange={(event) => {
                        chooseResumeFile(event.target.files?.[0]);
                        event.target.value = "";
                      }}
                    />
                  </label>
                  {file && (
                    <div className="selected-file">
                      <FileText size={17} />
                      <span>{file.name}</span>
                      <small>{(file.size / (1024 * 1024)).toFixed(2)} MB</small>
                    </div>
                  )}
                  {busy && file && uploadProgress !== null && (
                    <div className="upload-progress" role="status" aria-live="polite">
                      <div className="upload-progress-copy">
                        <span>Uploading resume</span><strong>{uploadProgress}%</strong>
                      </div>
                      <div className="upload-progress-track">
                        <span style={{ width: `${uploadProgress}%` }} />
                      </div>
                    </div>
                  )}
                </>
              )}

              {selectedResumeId && currentResume && (
                <div className="selected-file selected-existing-resume">
                  <FileText size={17} />
                  <span>{currentResume.filename}</span>
                  <button
                    className="button button-quiet"
                    type="button"
                    onClick={() => {
                      setSelectedResumeId("");
                      setEvaluation(null);
                      setNotice("");
                    }}
                  >
                    Choose another CV
                  </button>
                </div>
              )}
              </div>

              <button
                className="button button-primary full-width-button"
                type="submit"
                disabled={file ? !canUpload : !canEvaluate}
              >
                {busy ? (
                  <>
                    <LoaderCircle className="spin" size={16} />
                    {processingStage || "Processing CV…"}
                  </>
                ) : (
                  <>
                    <FileSearch size={16} />
                    {currentResume?.evaluation_status === "processing"
                      ? "Evaluation processing…"
                      : currentResume?.evaluation_status === "failed"
                        ? "Retry CV evaluation"
                        : currentResume?.evaluation_status === "completed"
                          ? "Re-evaluate CV"
                          : "Evaluate CV"}
                  </>
                )}
              </button>
            </form>
          </Panel>
          <Panel
            title="Previous evaluations"
            subtitle="Select a saved result to review or check multiple CVs to compare."
            className="cv-history-panel"
          >
            {loading ? (
              <LoadingState label="Loading resume history…" />
            ) : resumes.length === 0 ? (
              <EmptyState title="No resumes uploaded yet">
                Upload a CV above to start testing the resume evaluation workflow.
              </EmptyState>
            ) : (
              <div className="resume-history">
                {resumes.map((resume) => {
                  const details = resume.evaluation_details ?? {};
                  const comparisonEnabled =
                    resume.score != null && Boolean(resume.evaluation_details);
                  return (
                    <div
                      className={`resume-history-row${resume.id === selectedResumeId ? " selected" : ""}`}
                      key={resume.id}
                    >
                      <button
                        type="button"
                        className="resume-history-item"
                        onClick={() => reviewExistingResume(resume)}
                      >
                        <FileText size={17} />
                        <span>
                          <strong>{resume.filename}</strong>
                          <small>
                            {candidateById.get(resume.candidate_id)?.full_name ??
                              "Candidate"}
                            {details.job_title || jobById.get(resume.job_id)?.title
                              ? ` · ${details.job_title ?? jobById.get(resume.job_id)?.title}`
                              : ""}
                          </small>
                        </span>
                        {resume.score != null &&
                          resume.evaluation_status === "completed" && (
                          <span className="score-pill">{resume.score}</span>
                          )}
                        <StatusBadge>{resume.evaluation_status}</StatusBadge>
                      </button>
                      {comparisonEnabled && (
                        <label className="compare-select">
                          <input
                            type="checkbox"
                            checked={comparisonIds.includes(resume.id)}
                            onChange={(event) =>
                              toggleComparison(resume.id, event.target.checked)
                            }
                          />
                          <span>Compare</span>
                        </label>
                      )}
                      <button
                        type="button"
                        className="button button-quiet resume-delete-button"
                        aria-label={`Delete evaluation for ${resume.filename}`}
                        title="Delete evaluation"
                        disabled={deletingResumeId === resume.id}
                        onClick={() => deleteResume(resume)}
                      >
                        {deletingResumeId === resume.id ? (
                          <LoaderCircle className="spin" size={15} />
                        ) : (
                          <Trash2 size={15} />
                        )}
                      </button>
                    </div>
                  );
                })}
              </div>
            )}
          </Panel>
        </div>

        <div className="evaluation-column cv-evaluation-results">
          {!evaluation ? (
            <Panel
              title="Evaluation results"
              subtitle={busy ? "The backend is analyzing CV evidence against the selected role." : "Results are returned by the configured FastAPI service."}
            >
              {busy ? (
                <LoadingState label={processingStage || "Starting the backend evaluation…"} />
              ) : selectedResumeId && currentResume ? (
                <div className="cv-status-card" role="status" aria-live="polite">
                  <div className="cv-status-heading">
                    <strong>Evaluation status</strong>
                    <StatusBadge>{currentResume.evaluation_status}</StatusBadge>
                  </div>
                  {["pending", "processing"].includes(
                    currentResume.evaluation_status,
                  ) ? (
                    <LoadingState
                      label={
                        currentResume.evaluation_status === "pending"
                          ? "Waiting for the evaluation agent to start…"
                          : "The backend agent is analyzing CV evidence against the selected role…"
                      }
                    />
                  ) : currentResume.evaluation_status === "failed" ? (
                    <p>
                      {currentResume.evaluation_details?.error ??
                        "The backend agent could not complete this evaluation. Retry when ready."}
                    </p>
                  ) : (
                    <p>Evaluation completed. Load its saved result to review the evidence.</p>
                  )}
                </div>
              ) : (
                <EmptyState title="No evaluation selected">
                  Choose a candidate and job, upload a CV, then start evaluation.
                  Results use the actual backend response; no placeholder scores are used.
                </EmptyState>
              )}
            </Panel>
          ) : (
            <>
              <Panel className="score-panel">
                <div className="score-overview">
                  <div
                    className="score-ring"
                    role="progressbar"
                    aria-label="Resume match score"
                    aria-valuemin={0}
                    aria-valuemax={100}
                    aria-valuenow={evaluation.score}
                    style={{ "--score": `${evaluation.score}%` }}
                  >
                    <strong>{evaluation.score}</strong>
                    <span>out of 100</span>
                  </div>
                  <div className="score-copy">
                    <p className="eyebrow">Resume match</p>
                    <h2>{selectedCandidate?.full_name ?? "Candidate"}</h2>
                    <StatusBadge>completed</StatusBadge>
                    <p>
                      {selectedJob?.title ??
                        evaluation.job_title ??
                        "Selected job"}{" "}
                      · {currentResume?.filename ?? "Resume"}
                    </p>
                    <span
                      className={`match-label match-${matchLabel(evaluation.score)
                        .toLowerCase()
                        .replaceAll(" ", "-")}`}
                    >
                      {matchLabel(evaluation.score)}
                    </span>
                    <p className="score-disclaimer">
                      A job-related evidence summary only—not a hiring
                      probability or an automated decision.
                    </p>
                  </div>
                </div>
                {Object.keys(evaluation.rubric_scores ?? {}).length > 0 && (
                  <div className="rubric-grid">
                    {Object.entries(evaluation.rubric_scores).map(
                      ([name, score]) => (
                        <div className="rubric-item" key={name}>
                          <span>{name.replaceAll("_", " ")}</span>
                          <strong>{score}</strong>
                        </div>
                      ),
                    )}
                  </div>
                )}
              </Panel>

              <Panel title="Candidate information">
                <div className="candidate-summary">
                  <div>
                    <span>Name</span>
                    <strong>{selectedCandidate?.full_name ?? "Not available"}</strong>
                  </div>
                  <div>
                    <span>Email</span>
                    <strong>{selectedCandidate?.email ?? "Not available"}</strong>
                  </div>
                  <div>
                    <span>Phone</span>
                    <strong>{selectedCandidate?.phone ?? "Not provided"}</strong>
                  </div>
                </div>
              </Panel>

              <Panel title="AI evaluation explanation">
                <p className="evaluation-explanation">
                  {evaluation.explanation}
                </p>
              </Panel>

              <div className="evaluation-lists cv-strengths-gaps">
                <Panel title="Candidate strengths">
                  <EvaluationTags
                    values={evaluation.candidate_strengths}
                    variant="tag-green"
                    empty="No specific strengths were supported by the extracted CV evidence."
                  />
                </Panel>
                <Panel title="Matched skills">
                  <EvaluationTags
                    values={evaluation.matched_skills}
                    variant="tag-green"
                    empty="No matched skills were identified."
                  />
                  <SkillMatchReasons
                    reasons={evaluation.skill_match_reasons}
                    matched
                  />
                </Panel>
                <Panel title="Experience match">
                  <EvaluationTags
                    values={evaluation.relevant_experience}
                    variant="tag-blue"
                    empty="The backend did not identify specific relevant experience in this CV."
                  />
                  {evaluation.rubric_scores?.relevant_experience !== undefined && (
                    <p className="cv-rubric-result">
                      Agent rubric: <strong>{evaluation.rubric_scores.relevant_experience}</strong>
                    </p>
                  )}
                </Panel>
                <Panel title="Weaknesses · missing required skills">
                  <EvaluationTags
                    values={evaluation.missing_required_skills}
                    variant="tag-amber"
                    empty="No missing required skills were reported."
                  />
                  <SkillMatchReasons
                    reasons={evaluation.skill_match_reasons}
                    matched={false}
                  />
                </Panel>
                <Panel title="Other gaps to review">
                  <EvaluationTags
                    values={evaluation.missing_requirements}
                    variant="tag-amber"
                    empty="No additional missing requirements were identified."
                  />
                </Panel>
              </div>

              <Panel title="Experience evidence, projects & education">
                <div className="evidence-columns">
                  <div>
                    <h3>Relevant work experience</h3>
                    <ul className="evidence-list">
                      {(evaluation.relevant_experience ?? []).map(
                        (item, index) => (
                          <li key={`${item}-${index}`}>{item}</li>
                        ),
                      )}
                    </ul>
                    {!evaluation.relevant_experience?.length && (
                      <p className="muted-copy">
                        No relevant experience was identified.
                      </p>
                    )}
                  </div>
                  <div>
                    <h3>Relevant projects</h3>
                    <ul className="evidence-list">
                      {(evaluation.relevant_projects ?? []).map(
                        (item, index) => (
                          <li key={`${item}-${index}`}>{item}</li>
                        ),
                      )}
                    </ul>
                    {!evaluation.relevant_projects?.length && (
                      <p className="muted-copy">
                        No relevant projects were identified.
                      </p>
                    )}
                  </div>
                </div>
                <h3>Education and certifications</h3>
                <ul className="evidence-list">
                  {(evaluation.education_and_certifications ?? []).map(
                    (item, index) => (
                      <li key={`${item}-${index}`}>{item}</li>
                    ),
                  )}
                </ul>
                {!evaluation.education_and_certifications?.length && (
                  <p className="muted-copy">
                    No education details were extracted.
                  </p>
                )}
                <h3>Evidence extracted from the CV</h3>
                <ul className="evidence-list">
                  {(evaluation.evidence ?? []).map((item, index) => (
                    <li key={`${item}-${index}`}>{item}</li>
                  ))}
                </ul>
                {!evaluation.evidence?.length && (
                  <p className="muted-copy">No supporting evidence was reported.</p>
                )}
              </Panel>

              <Panel title="Extracted CV text">
                {evaluation.extracted_text ? (
                  <details className="extracted-text">
                    <summary>
                      <Search size={15} />
                      View text extracted by the backend
                    </summary>
                    <pre>{evaluation.extracted_text}</pre>
                  </details>
                ) : (
                  <p className="muted-copy">
                    The backend did not return extracted CV text for this result.
                  </p>
                )}
              </Panel>

              {selectedCandidate && !selectedCandidate.hr_approved && (
                <div className="approval-callout">
                  <div>
                    <strong>Ready for HR review?</strong>
                    <p>
                      Approval is a manual HR action and does not guarantee
                      advancement.
                    </p>
                  </div>
                  <button
                    className="button button-primary"
                    type="button"
                    onClick={approveForScreening}
                    disabled={busy}
                  >
                    {busy ? "Saving…" : "Approve for screening"}
                  </button>
                </div>
              )}
            </>
          )}

          {comparisonResumes.length > 0 && (
            <Panel
              title="Compare evaluation results"
              subtitle="Compare backend scores and extracted skill evidence. These are review aids, not candidate rankings or hiring decisions."
            >
              <div className="comparison-table-wrap">
                <table className="comparison-table">
                  <thead>
                    <tr>
                      <th>Candidate / CV</th>
                      <th>Job</th>
                      <th>Match score</th>
                      <th>Matched skills</th>
                      <th>Missing required skills</th>
                    </tr>
                  </thead>
                  <tbody>
                    {comparisonResumes.map((resume) => {
                      const details = resume.evaluation_details;
                      return (
                        <tr key={resume.id}>
                          <td>
                            <strong>
                              {candidateById.get(resume.candidate_id)
                                ?.full_name ?? "Candidate"}
                            </strong>
                            <small>{resume.filename}</small>
                          </td>
                          <td>
                            {details.job_title ??
                              jobById.get(details.job_id)?.title ??
                              "Job not recorded"}
                          </td>
                          <td>
                            <strong>{resume.score}/100</strong>
                            <small>{matchLabel(resume.score)}</small>
                          </td>
                          <td>
                            {(details.matched_skills ?? []).join(", ") || "None"}
                          </td>
                          <td>
                            {(details.missing_required_skills ?? []).join(", ") ||
                              "None"}
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            </Panel>
          )}
        </div>
      </div>
    </>
  );
}
