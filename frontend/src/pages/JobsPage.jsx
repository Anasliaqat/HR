import { useEffect, useMemo, useState } from "react";
import {
  BriefcaseBusiness,
  MapPin,
  Pencil,
  Plus,
  Search,
  Trash2,
  UsersRound,
  X,
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

const emptyForm = {
  title: "",
  description: "",
  department: "",
  location: "",
  employment_type: "",
  required_skills: "",
  preferred_skills: "",
  required_experience_years: "",
  education: "",
  number_of_vacancies: "1",
  status: "draft",
};

export default function JobsPage() {
  const [jobs, setJobs] = useState([]);
  const [applications, setApplications] = useState([]);
  const [candidates, setCandidates] = useState([]);
  const [form, setForm] = useState(emptyForm);
  const [editingId, setEditingId] = useState("");
  const [showForm, setShowForm] = useState(false);
  const [expandedJob, setExpandedJob] = useState("");
  const [search, setSearch] = useState("");
  const [statusFilter, setStatusFilter] = useState("");
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");

  async function loadJobs() {
    setLoading(true);
    setError("");
    try {
      const [jobRows, applicationRows, candidateRows] = await Promise.all([
        api.getJobs(),
        api.getApplications(),
        api.getCandidates(),
      ]);
      setJobs(jobRows);
      setApplications(applicationRows);
      setCandidates(candidateRows);
    } catch (requestError) {
      setError(requestError.message);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    loadJobs();
  }, []);

  const candidateById = useMemo(
    () => new Map(candidates.map((candidate) => [candidate.id, candidate])),
    [candidates],
  );
  const applicantsByJob = useMemo(() => {
    const grouped = new Map();
    for (const application of applications) {
      const current = grouped.get(application.job_id) ?? [];
      current.push(application);
      grouped.set(application.job_id, current);
    }
    return grouped;
  }, [applications]);
  const filteredJobs = jobs.filter((job) => {
    const query = search.trim().toLowerCase();
    const matchesText =
      !query ||
      job.title?.toLowerCase().includes(query) ||
      job.department?.toLowerCase().includes(query) ||
      job.location?.toLowerCase().includes(query);
    return matchesText && (!statusFilter || job.status === statusFilter);
  });

  function beginEdit(job) {
    setError("");
    setSuccess("");
    setEditingId(job.id);
    setForm({
      title: job.title,
      description: job.description,
      department: job.department ?? "",
      location: job.location ?? "",
      employment_type: job.employment_type ?? "",
      required_skills: (job.required_skills ?? []).join(", "),
      preferred_skills: (job.preferred_skills ?? []).join(", "),
      required_experience_years:
        job.required_experience_years == null
          ? ""
          : String(job.required_experience_years),
      education: job.education ?? "",
      number_of_vacancies: String(job.number_of_vacancies ?? 1),
      status: job.status ?? "draft",
    });
    setShowForm(true);
  }

  function resetForm() {
    setForm(emptyForm);
    setEditingId("");
    setShowForm(false);
  }

  async function submitJob(event) {
    event.preventDefault();
    setSaving(true);
    setError("");
    const payload = {
      title: form.title.trim(),
      description: form.description.trim(),
      department: form.department.trim() || null,
      location: form.location.trim() || null,
      employment_type: form.employment_type.trim() || null,
      required_skills: form.required_skills
        .split(",")
        .map((skill) => skill.trim())
        .filter(Boolean),
      preferred_skills: form.preferred_skills
        .split(",")
        .map((skill) => skill.trim())
        .filter(Boolean),
      required_experience_years:
        form.required_experience_years === ""
          ? null
          : Number(form.required_experience_years),
      education: form.education.trim() || null,
      number_of_vacancies: Number(form.number_of_vacancies),
      status: form.status,
    };
    try {
      const savedJob = editingId
        ? await api.updateJob(editingId, payload)
        : await api.createJob(payload);
      setJobs((currentJobs) =>
        editingId
          ? currentJobs.map((job) => (job.id === savedJob.id ? savedJob : job))
          : [savedJob, ...currentJobs],
      );
      resetForm();
      setSuccess(editingId ? "Job updated successfully." : "Job created successfully.");
    } catch (requestError) {
      setError(requestError.message);
    } finally {
      setSaving(false);
    }
  }

  async function deleteJob(job) {
    if (
      !window.confirm(
        `Delete "${job.title}"? This may also remove related applications.`,
      )
    ) {
      return;
    }
    setError("");
    setSuccess("");
    try {
      await api.deleteJob(job.id);
      setJobs((currentJobs) => currentJobs.filter((item) => item.id !== job.id));
      setSuccess("Job deleted successfully.");
    } catch (requestError) {
      setError(requestError.message);
    }
  }

  return (
    <>
      <PageHeading
        eyebrow="Hiring"
        title="Jobs"
        description="Create vacancies and keep each role’s applicant pipeline organized."
        actions={
          <button
            type="button"
            className="button button-primary"
            onClick={() => {
              resetForm();
              setError("");
              setSuccess("");
              setShowForm(true);
            }}
          >
            <Plus size={17} /> Create job
          </button>
        }
      />
      <ErrorMessage>{error}</ErrorMessage>
      {success && <div className="success-banner" role="status">{success}</div>}
      <div className="table-toolbar job-toolbar">
        <div className="search-field">
          <Search size={17} />
          <input
          aria-label="Search jobs"
          placeholder="Search roles, departments, or locations..."
          value={search}
          onChange={(event) => setSearch(event.target.value)}
          />
        </div>
        <select
          aria-label="Filter jobs by status"
          className="filter-select"
          value={statusFilter}
          onChange={(event) => setStatusFilter(event.target.value)}
        >
          <option value="">All job statuses</option>
          <option value="open">Active</option>
          <option value="draft">Draft</option>
          <option value="closed">Closed</option>
        </select>
      </div>
      {showForm && (
        <div className="modal-backdrop job-form-backdrop" onClick={resetForm}>
          <section
          className="job-form-dialog"
          role="dialog"
          aria-modal="true"
          aria-labelledby="job-form-title"
          onClick={(event) => event.stopPropagation()}
          >
          <Panel
          title={editingId ? "Edit vacancy" : "Create a vacancy"}
          subtitle="Add role details and the skills you’ll evaluate applicants against."
          className="form-panel"
          action={
            <button
              type="button"
              className="icon-button"
              aria-label="Close form"
              onClick={resetForm}
            >
              <X size={18} />
            </button>
          }
          >
          <form className="form-grid" onSubmit={submitJob}>
            <span className="visually-hidden" id="job-form-title">
              {editingId ? "Edit vacancy" : "Create a vacancy"}
            </span>
            <label>
              Job title <span className="required">*</span>
              <input
                required
                minLength={2}
                maxLength={200}
                value={form.title}
                onChange={(event) =>
                  setForm({ ...form, title: event.target.value })
                }
              />
            </label>
            <label>
              Department
              <input
                maxLength={100}
                value={form.department}
                onChange={(event) =>
                  setForm({ ...form, department: event.target.value })
                }
              />
            </label>
            <label>
              Location
              <input
                maxLength={200}
                value={form.location}
                onChange={(event) =>
                  setForm({ ...form, location: event.target.value })
                }
              />
            </label>
            <label>
              Employment type
              <select
                value={form.employment_type}
                onChange={(event) =>
                  setForm({ ...form, employment_type: event.target.value })
                }
              >
                <option value="">Select type</option>
                <option>Full-time</option>
                <option>Part-time</option>
                <option>Contract</option>
                <option>Temporary</option>
                <option>Internship</option>
              </select>
            </label>
            <label>
              Required experience (years)
              <input
                type="number"
                min="0"
                max="80"
                step="1"
                value={form.required_experience_years}
                onChange={(event) =>
                  setForm({
                    ...form,
                    required_experience_years: event.target.value,
                  })
                }
              />
            </label>
            <label>
              Education
              <input
                maxLength={5000}
                value={form.education}
                onChange={(event) =>
                  setForm({ ...form, education: event.target.value })
                }
              />
            </label>
            <label>
              Number of vacancies <span className="required">*</span>
              <input
                type="number"
                required
                min="1"
                max="10000"
                step="1"
                value={form.number_of_vacancies}
                onChange={(event) =>
                  setForm({ ...form, number_of_vacancies: event.target.value })
                }
              />
            </label>
            <label>
              Status
              <select
                value={form.status}
                onChange={(event) =>
                  setForm({ ...form, status: event.target.value })
                }
              >
                <option value="draft">Draft</option>
                <option value="open">Open</option>
                <option value="closed">Closed</option>
              </select>
            </label>
            <label className="form-full">
              Required skills
              <input
                placeholder="Python, SQL, stakeholder management"
                value={form.required_skills}
                onChange={(event) =>
                  setForm({ ...form, required_skills: event.target.value })
                }
              />
              <small>Separate skills with commas.</small>
            </label>
            <label className="form-full">
              Preferred skills
              <input
                placeholder="Docker, mentoring, cloud platforms"
                value={form.preferred_skills}
                onChange={(event) =>
                  setForm({ ...form, preferred_skills: event.target.value })
                }
              />
              <small>Separate skills with commas.</small>
            </label>
            <label className="form-full">
              Job description <span className="required">*</span>
              <textarea
                required
                maxLength={20000}
                rows={5}
                value={form.description}
                onChange={(event) =>
                  setForm({ ...form, description: event.target.value })
                }
              />
            </label>
            <div className="form-actions form-full">
              <button
                type="button"
                className="button button-secondary"
                onClick={resetForm}
              >
                Cancel
              </button>
              <button
                type="submit"
                className="button button-primary"
                disabled={saving}
              >
                {saving ? "Saving…" : editingId ? "Save changes" : "Create job"}
              </button>
            </div>
          </form>
          </Panel>
          </section>
        </div>
      )}

      {loading ? (
        <LoadingState label="Loading vacancies…" />
      ) : jobs.length === 0 ? (
        <Panel>
          <EmptyState title={error ? "Jobs are unavailable" : "No jobs posted"}>
            {error
              ? "Reconnect to the FastAPI backend and retry."
              : "Create your first vacancy to start building an applicant pipeline."}
          </EmptyState>
          {error && (
            <div className="centered-actions">
              <button type="button" className="button button-secondary" onClick={loadJobs}>
                Retry
              </button>
            </div>
          )}
        </Panel>
      ) : filteredJobs.length === 0 ? (
        <Panel>
          <EmptyState title="No jobs match your filters">
            Adjust the search or status filter to see more roles.
          </EmptyState>
        </Panel>
      ) : (
        <div className="job-grid">
          {filteredJobs.map((job) => {
            const applicants = applicantsByJob.get(job.id) ?? [];
            const expanded = expandedJob === job.id;
            return (
              <article className="job-card" key={job.id}>
                <div className="job-card-top">
                  <div className="job-icon">
                    <BriefcaseBusiness size={19} />
                  </div>
                  <div className="job-card-actions">
                    <button
                      type="button"
                      className="icon-button"
                      aria-label={`Edit ${job.title}`}
                      onClick={() => beginEdit(job)}
                    >
                      <Pencil size={16} />
                    </button>
                    <button
                      type="button"
                      className="icon-button danger-icon"
                      aria-label={`Delete ${job.title}`}
                      onClick={() => deleteJob(job)}
                    >
                      <Trash2 size={16} />
                    </button>
                  </div>
                </div>
                <h2>{job.title}</h2>
                <p className="job-meta">
                  {job.department || "Department not set"}
                  {job.location && (
                    <>
                      <span>·</span>
                      <MapPin size={14} /> {job.location}
                    </>
                  )}
                </p>
                {job.employment_type && (
                  <span className="tag">{job.employment_type}</span>
                )}
                <StatusBadge>{job.status ?? "draft"}</StatusBadge>
                <p className="muted-copy">
                  {job.number_of_vacancies ?? 1}{" "}
                  {(job.number_of_vacancies ?? 1) === 1 ? "vacancy" : "vacancies"}
                  {job.required_experience_years != null &&
                    ` · ${job.required_experience_years}+ years experience`}
                  {job.education && ` · ${job.education}`}
                </p>
                <p className="job-description">{job.description}</p>
                {job.required_skills?.length > 0 && (
                  <div className="tag-list">
                    {job.required_skills.map((skill) => (
                      <span className="tag tag-blue" key={skill}>
                        {skill}
                      </span>
                    ))}
                  </div>
                )}
                {job.preferred_skills?.length > 0 && (
                  <div className="tag-list">
                    {job.preferred_skills.map((skill) => (
                      <span className="tag tag-amber" key={skill}>
                        {skill}
                      </span>
                    ))}
                  </div>
                )}
                <div className="job-card-footer">
                  <span>
                    <UsersRound size={15} /> {applicants.length} applicants
                  </span>
                  <button
                    type="button"
                    className="text-link"
                    onClick={() => setExpandedJob(expanded ? "" : job.id)}
                  >
                    {expanded ? "Hide applicants" : "View applicants"}
                  </button>
                </div>
                {expanded && (
                  <div className="applicant-list">
                    {applicants.length === 0 ? (
                      <p className="muted-copy">No applications for this job yet.</p>
                    ) : (
                      applicants.map((application) => (
                        <div className="applicant-row" key={application.id}>
                          <span className="person-avatar">
                            {candidateById
                              .get(application.candidate_id)
                              ?.full_name?.slice(0, 1) ?? "C"}
                          </span>
                          <span>
                            <strong>
                              {candidateById.get(application.candidate_id)
                                ?.full_name ?? "Candidate"}
                            </strong>
                            <small>
                              {candidateById.get(application.candidate_id)?.email}
                            </small>
                          </span>
                          <span className="applicant-status">
                            {application.status.replaceAll("_", " ")}
                          </span>
                        </div>
                      ))
                    )}
                  </div>
                )}
              </article>
            );
          })}
        </div>
      )}
    </>
  );
}
