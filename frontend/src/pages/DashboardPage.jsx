import { useEffect, useMemo, useState } from "react";
import {
  ArrowUpRight,
  BriefcaseBusiness,
  CalendarDays,
  ChartNoAxesCombined,
  FileSearch,
  ListChecks,
  UsersRound,
} from "lucide-react";
import { Link } from "react-router-dom";
import { api } from "../services/api";
import { getApplicationTrend } from "../services/dashboardMetrics";
import Panel from "../components/Panel";
import {
  AnimatedMetric,
  EmptyState,
  ErrorMessage,
  LoadingState,
  PageHeading,
  StatusBadge,
} from "../components/Feedback";

const pipelineSteps = [
  { key: "pending_review", label: "Needs review", color: "pipeline-blue" },
  { key: "screening", label: "Screening", color: "pipeline-violet" },
  { key: "interview_eligible", label: "Interview eligible", color: "pipeline-indigo" },
  { key: "approved_by_hr", label: "HR approved", color: "pipeline-indigo" },
  { key: "interview", label: "Interview", color: "pipeline-indigo" },
  { key: "hired", label: "Hired", color: "pipeline-green" },
];

function formatDate(value) {
  if (!value) return "—";
  return new Date(value).toLocaleDateString(undefined, {
    month: "short",
    day: "numeric",
    year: "numeric",
  });
}

function getGreeting() {
  const hour = new Date().getHours();
  if (hour < 12) return "Good morning";
  if (hour < 18) return "Good afternoon";
  return "Good evening";
}

export default function DashboardPage() {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  async function loadDashboard() {
    setLoading(true);
    setError("");
    try {
      const [jobs, candidates, applications, interviews, resumes] = await Promise.all([
        api.getJobs(),
        api.getCandidates(),
        api.getApplications(),
        api.getInterviews(),
        api.getResumes(),
      ]);
      setData({ jobs, candidates, applications, interviews, resumes });
    } catch (requestError) {
      setError(requestError.message);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    loadDashboard();
  }, []);

  const candidateById = useMemo(
    () => new Map((data?.candidates ?? []).map((item) => [item.id, item])),
    [data?.candidates],
  );
  const jobById = useMemo(
    () => new Map((data?.jobs ?? []).map((item) => [item.id, item])),
    [data?.jobs],
  );
  const pipeline = useMemo(() => {
    const counts = Object.fromEntries(
      pipelineSteps.map(({ key }) => [key, 0]),
    );
    for (const application of data?.applications ?? []) {
      if (Object.hasOwn(counts, application.status)) {
        counts[application.status] += 1;
      }
    }
    return counts;
  }, [data?.applications]);
  const maxPipeline = Math.max(1, ...Object.values(pipeline));
  const recentApplications = [...(data?.applications ?? [])]
    .sort((left, right) => new Date(right.applied_at) - new Date(left.applied_at))
    .slice(0, 5);
  const upcomingInterviews = (data?.interviews ?? [])
    .filter(
      (interview) =>
        interview.status === "scheduled" &&
        new Date(interview.start_at).getTime() >= Date.now(),
    )
    .sort(
      (left, right) =>
        new Date(left.start_at).getTime() - new Date(right.start_at).getTime(),
    )
    .slice(0, 4);
  const applicationTrend = getApplicationTrend(data?.applications ?? []);
  const maxTrend = Math.max(1, ...applicationTrend.map((day) => day.count));
  const recentJobs = [...(data?.jobs ?? [])]
    .sort(
      (left, right) =>
        new Date(right.created_at ?? right.updated_at ?? 0) -
        new Date(left.created_at ?? left.updated_at ?? 0),
    )
    .slice(0, 4);
  const recentActivities = [
    ...(data?.applications ?? []).map((application) => ({
      id: `application-${application.id}`,
      title: "New application received",
      detail: `${candidateById.get(application.candidate_id)?.full_name ?? "Candidate"} · ${jobById.get(application.job_id)?.title ?? "Position"}`,
      date: application.applied_at,
      icon: UsersRound,
      tone: "blue",
    })),
    ...(data?.interviews ?? []).map((interview) => ({
      id: `interview-${interview.id}`,
      title: interview.status === "scheduled" ? "Interview scheduled" : `Interview ${interview.status}`,
      detail: `${candidateById.get(interview.candidate_id)?.full_name ?? "Candidate"} · ${jobById.get(interview.job_id)?.title ?? "Position"}`,
      date: interview.start_at,
      icon: CalendarDays,
      tone: "violet",
    })),
  ]
    .filter((activity) => !Number.isNaN(new Date(activity.date).getTime()))
    .sort((left, right) => new Date(right.date) - new Date(left.date))
    .slice(0, 5);
  const evaluatedScores = (data?.resumes ?? [])
    .map((item) => item.score)
    .filter((score) => Number.isFinite(score));
  const averageMatchScore = evaluatedScores.length
    ? Math.round(
        evaluatedScores.reduce((sum, score) => sum + score, 0) /
          evaluatedScores.length,
      )
    : null;

  const stats = [
    {
      title: "Active jobs",
      value: data?.jobs?.filter((item) => item.status === "open").length ?? 0,
      note: "Currently accepting applications",
      icon: BriefcaseBusiness,
      tone: "blue",
    },
    {
      title: "Candidates",
      value: data?.candidates?.length ?? 0,
      note: "Candidate profiles",
      icon: UsersRound,
      tone: "violet",
    },
    {
      title: "Resumes analyzed",
      value: data?.resumes?.filter((item) => item.score != null).length ?? 0,
      note: "Completed evaluations",
      icon: FileSearch,
      tone: "violet",
    },
    {
      title: "Waiting for review",
      value: data?.candidates?.filter((item) => !item.hr_approved).length ?? 0,
      note: "Requires an HR decision",
      icon: ListChecks,
      tone: "amber",
    },
    {
      title: "Interviews scheduled",
      value:
        data?.interviews?.filter((item) => item.status === "scheduled").length ??
        0,
      note: "All scheduled interviews",
      icon: CalendarDays,
      tone: "green",
    },
    {
      title: "Average match score",
      value: averageMatchScore,
      suffix: averageMatchScore === null ? "" : "%",
      note: "Across evaluated resumes",
      icon: ChartNoAxesCombined,
      tone: "cyan",
    },
  ];

  return (
    <div className="dashboard-page">
      <PageHeading
        eyebrow="HIRING OVERVIEW"
        title={getGreeting()}
        description="Here’s what’s happening across your hiring pipeline."
        actions={
          <>
            <Link className="button button-secondary" to="/">
              <FileSearch size={16} /> Evaluate a CV
            </Link>
            <Link className="button button-primary" to="/jobs">
              <BriefcaseBusiness size={16} /> Create a job
            </Link>
          </>
        }
      />
      <ErrorMessage>{error}</ErrorMessage>
      {loading && !data ? (
        <LoadingState label="Loading your hiring overview…" />
      ) : !data ? (
        <Panel>
          <EmptyState title="Dashboard data is unavailable">
            Check the FastAPI connection and retry to load real hiring metrics.
          </EmptyState>
          <div className="centered-actions">
            <button type="button" className="button button-secondary" onClick={loadDashboard}>
              Retry
            </button>
          </div>
        </Panel>
      ) : (
        <>
          <div className="stats-grid">
            {stats.map(({ title, value, suffix = "", note, icon: Icon, tone }, index) => (
              <article className="stat-card" key={title} style={{ "--card-index": index }}>
                <div className={`stat-icon stat-${tone}`}>
                  <Icon size={19} />
                </div>
                <div className="stat-copy">
                  <span>{title}</span>
                  <strong><AnimatedMetric value={value} />{suffix}</strong>
                  <small>{note}</small>
                </div>
                <ArrowUpRight className="stat-arrow" size={17} />
              </article>
            ))}
          </div>

          <div className="dashboard-grid">
            <Panel
              title="Application activity"
              subtitle="New applications over the last seven days"
              className="trend-panel"
            >
              <div className="trend-total">
                <strong>
                  {applicationTrend.reduce((sum, day) => sum + day.count, 0)}
                </strong>
                <span>applications this week</span>
              </div>
              <div className="trend-chart" role="img" aria-label="Applications received by day in the last seven days">
                {applicationTrend.map(({ label, count }) => (
                  <div className="trend-column" key={label}>
                    <div className="trend-bar-wrap" title={`${count} applications`}>
                      <span
                        className="trend-bar"
                        style={{ "--bar-height": `${Math.max(count ? 10 : 3, (count / maxTrend) * 100)}%` }}
                      />
                    </div>
                    <strong>{count}</strong>
                    <span>{label}</span>
                  </div>
                ))}
              </div>
            </Panel>

            <Panel
              title="Hiring pipeline"
              subtitle="Candidates across each stage"
              className="pipeline-panel"
            >
              <div className="pipeline-chart" aria-label="Hiring pipeline chart">
                {pipelineSteps.map(({ key, label, color }) => {
                  const count = pipeline[key];
                  const width = count === 0 ? "0%" : `${Math.max(4, (count / maxPipeline) * 100)}%`;
                  return (
                    <div className="pipeline-row" key={key}>
                      <div className="pipeline-label">
                        <span>{label}</span>
                        <strong>{count}</strong>
                      </div>
                      <div className="pipeline-track">
                        <span
                          className={`pipeline-bar ${color}`}
                          style={{ width }}
                        />
                      </div>
                    </div>
                  );
                })}
              </div>
              <div className="chart-footnote">Pipeline counts reflect live application statuses.</div>
            </Panel>

            <Panel
              title="Upcoming interviews"
              subtitle="Your next scheduled conversations"
              action={
                <Link className="text-link" to="/interviews">
                  View all <ArrowUpRight size={14} />
                </Link>
              }
            >
              {upcomingInterviews.length === 0 ? (
                <EmptyState title="No upcoming interviews">
                  Scheduled interviews will appear here.
                </EmptyState>
              ) : (
                <div className="upcoming-list">
                  {upcomingInterviews.map((interview) => (
                    <div className="upcoming-item" key={interview.id}>
                      <div className="date-tile">
                        <strong>
                          {new Date(interview.start_at).toLocaleDateString(
                            undefined,
                            { day: "2-digit" },
                          )}
                        </strong>
                        <span>
                          {new Date(interview.start_at).toLocaleDateString(
                            undefined,
                            { month: "short" },
                          )}
                        </span>
                      </div>
                      <div className="upcoming-copy">
                        <strong>
                          {candidateById.get(interview.candidate_id)?.full_name ??
                            "Candidate"}
                        </strong>
                        <span>{jobById.get(interview.job_id)?.title ?? "Interview"}</span>
                        <small>
                          {new Date(interview.start_at).toLocaleTimeString(
                            undefined,
                            { hour: "numeric", minute: "2-digit" },
                          )}{" "}
                          · {interview.interviewer_email}
                        </small>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </Panel>
          </div>

          <div className="dashboard-grid dashboard-lower-grid">
            <Panel
              title="Recent applications"
              subtitle="Latest candidates to enter your pipeline"
              action={
                <Link className="text-link" to="/candidates">
                  View candidates <ArrowUpRight size={14} />
                </Link>
              }
            >
              {recentApplications.length === 0 ? (
                <EmptyState title="No applications yet">
                  Create a job and start adding candidate applications.
                </EmptyState>
              ) : (
                <div className="table-scroll">
                  <table className="data-table">
                    <thead>
                      <tr>
                        <th>Candidate</th>
                        <th>Position</th>
                        <th>Applied</th>
                        <th>Status</th>
                      </tr>
                    </thead>
                    <tbody>
                      {recentApplications.map((application) => {
                        const candidate = candidateById.get(application.candidate_id);
                        return (
                          <tr key={application.id}>
                            <td>
                              <div className="person-cell">
                                <span className="person-avatar">
                                  {candidate?.full_name?.slice(0, 1) ?? "C"}
                                </span>
                                <span>
                                  <strong>{candidate?.full_name ?? "Candidate"}</strong>
                                  <small>{candidate?.email ?? ""}</small>
                                </span>
                              </div>
                            </td>
                            <td>{jobById.get(application.job_id)?.title ?? "—"}</td>
                            <td>{formatDate(application.applied_at)}</td>
                            <td>
                              <StatusBadge>{application.status.replaceAll("_", " ")}</StatusBadge>
                            </td>
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>
                </div>
              )}
            </Panel>

            <div className="dashboard-side-stack">
              <Panel
                title="Recent activity"
                subtitle="Latest changes across your workspace"
              >
                {recentActivities.length === 0 ? (
                  <EmptyState title="Your activity will appear here">
                    Applications and interview updates will show up as they arrive.
                  </EmptyState>
                ) : (
                  <div className="activity-list">
                    {recentActivities.map(({ id, title, detail, date, icon: Icon, tone }) => (
                      <div className="activity-item" key={id}>
                        <span className={`activity-icon activity-${tone}`}><Icon size={15} /></span>
                        <span className="activity-copy">
                          <strong>{title}</strong>
                          <small>{detail}</small>
                        </span>
                        <time>{formatDate(date)}</time>
                      </div>
                    ))}
                  </div>
                )}
              </Panel>
              <Panel
                title="Recent job postings"
                subtitle="Roles currently in your workspace"
                action={<Link className="text-link" to="/jobs">All jobs <ArrowUpRight size={14} /></Link>}
              >
                {recentJobs.length === 0 ? (
                  <EmptyState title="No jobs posted yet">
                    Create a role to start building your hiring pipeline.
                  </EmptyState>
                ) : (
                  <div className="recent-jobs-list">
                    {recentJobs.map((job) => {
                      const applicants = (data?.applications ?? []).filter((item) => item.job_id === job.id).length;
                      return (
                        <div className="recent-job-item" key={job.id}>
                          <span className="job-icon"><BriefcaseBusiness size={16} /></span>
                          <span>
                            <strong>{job.title}</strong>
                            <small>{job.department || job.location || "Department not set"} · {applicants} applicants</small>
                          </span>
                          <StatusBadge>{job.status ?? "draft"}</StatusBadge>
                        </div>
                      );
                    })}
                  </div>
                )}
              </Panel>
            </div>
          </div>
        </>
      )}
    </div>
  );
}
