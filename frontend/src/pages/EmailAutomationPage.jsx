import { useEffect, useMemo, useState } from "react";
import { Mail, RefreshCw, Send, Trash2 } from "lucide-react";
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

const emailTypes = [
  { value: "rejection", label: "Rejection" },
  { value: "selection", label: "CV approved / selection" },
  { value: "screening_invitation", label: "AI screening invitation" },
  { value: "interview_invitation", label: "Interview invitation" },
];

function formatDate(value) {
  if (!value) return "—";
  return new Date(value).toLocaleString();
}

function labelForEmail(type) {
  return emailTypes.find((item) => item.value === type)?.label ?? type;
}

export default function EmailAutomationPage() {
  const [applications, setApplications] = useState([]);
  const [reviewQueue, setReviewQueue] = useState([]);
  const [interviews, setInterviews] = useState([]);
  const [selectedId, setSelectedId] = useState("");
  const [emailType, setEmailType] = useState("selection");
  const [interviewId, setInterviewId] = useState("");
  const [preview, setPreview] = useState(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");

  async function loadData() {
    setLoading(true);
    setError("");
    try {
      const [emailApplications, interviewRows, reviewRows] = await Promise.all([
        api.getEmailApplications(),
        api.getInterviews(),
        api.getAgentReviewQueue(),
      ]);
      setApplications(emailApplications);
      setInterviews(interviewRows);
      setReviewQueue(reviewRows);
      setSelectedId((current) =>
        emailApplications.some((item) => item.application_id === current)
          ? current
          : emailApplications[0]?.application_id ?? "",
      );
    } catch (requestError) {
      setError(requestError.message);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    loadData();
  }, []);

  const selected = applications.find(
    (item) => item.application_id === selectedId,
  );
  const selectedInterviews = useMemo(
    () =>
      interviews.filter(
        (interview) =>
          interview.candidate_id === selected?.candidate_id &&
          interview.job_id === selected?.job_id,
      ),
    [interviews, selected?.candidate_id, selected?.job_id],
  );
  const latestEmail = selected?.emails?.[0];
  const canDecide =
    selected?.application_status === "pending_review" &&
    ["hr_review", "hr_decision"].includes(selected?.score_action);

  function chooseApplication(id) {
    setSelectedId(id);
    setPreview(null);
    setNotice("");
    setInterviewId("");
    setEmailType("selection");
  }

  async function previewEmail() {
    if (!selected) return;
    setBusy(true);
    setError("");
    setNotice("");
    try {
      const result = await api.previewEmail(
        selected.application_id,
        emailType,
        emailType === "interview_invitation" ? interviewId : undefined,
      );
      setPreview(result);
    } catch (requestError) {
      setError(requestError.message);
      setPreview(null);
    } finally {
      setBusy(false);
    }
  }

  async function finishAction(action) {
    if (!selected || !preview) return;
    setBusy(true);
    setError("");
    setNotice("");
    try {
      const record = canDecide
        ? await api.recordEmailDecision(selected.application_id, action)
        : await api.sendEmail(
            selected.application_id,
            emailType,
            emailType === "interview_invitation" ? interviewId : undefined,
          );
      setNotice(
        record.status === "sent"
          ? `Email sent to ${record.recipient_email}.`
          : `Email status: ${record.status}.${record.error_message ? ` ${record.error_message}` : ""}`,
      );
      setPreview(null);
      await loadData();
    } catch (requestError) {
      setError(requestError.message);
    } finally {
      setBusy(false);
    }
  }

  async function retryEmail(emailId) {
    setBusy(true);
    setError("");
    setNotice("");
    try {
      const record = await api.retryEmail(emailId);
      setNotice(
        record.status === "sent"
          ? `Email sent to ${record.recipient_email}.`
          : `Email status: ${record.status}.${record.error_message ? ` ${record.error_message}` : ""}`,
      );
      await loadData();
    } catch (requestError) {
      setError(requestError.message);
    } finally {
      setBusy(false);
    }
  }

  async function deleteApplicationHistory(application) {
    if (
      !window.confirm(
        `Delete email history for ${application.candidate_name} · ${application.job_title}? The application will remain.`,
      )
    ) {
      return;
    }
    setBusy(true);
    setError("");
    setNotice("");
    try {
      await api.deleteApplicationEmailHistory(application.application_id);
      setNotice("Email history deleted. The application was kept.");
      await loadData();
    } catch (requestError) {
      setError(requestError.message);
    } finally {
      setBusy(false);
    }
  }

  async function decideAgentReview(application, decision) {
    const verb = decision === "approve" ? "approve" : "reject";
    if (
      !window.confirm(
        `${verb[0].toUpperCase()}${verb.slice(1)} ${application.candidate_name}? This records the HR decision and attempts the matching email if consent and delivery configuration allow it.`,
      )
    ) {
      return;
    }
    setBusy(true);
    setError("");
    setNotice("");
    try {
      const result = await api.decideAgentReview(
        application.application_id,
        decision,
      );
      const email = result.email;
      setNotice(
        email?.status === "sent"
          ? `HR ${decision} recorded and email sent to ${email.recipient_email}.`
          : `HR ${decision} recorded. Email status: ${email?.status ?? "unavailable"}.${email?.error_message ? ` ${email.error_message}` : ""}`,
      );
      await loadData();
      if (result.status) {
        setSelectedId(application.application_id);
      }
    } catch (requestError) {
      setError(requestError.message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      <PageHeading
        eyebrow="ZETECH · RECRUITMENT"
        title="Email automation"
        description="Review CV-driven workflow statuses, candidate email consent, and every recruiting email delivery."
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
      {notice && <p className="form-note email-notice" role="status">{notice}</p>}
      <Panel
        className="table-panel"
        title={`Over Agent Review (${reviewQueue.length})`}
        subtitle="Flagged CVs require an explicit HR decision. Only that manual decision attempts the matching email."
      >
        {reviewQueue.length === 0 ? (
          <EmptyState title="No applications are waiting for agent review">
            Low-scoring, irrelevant, and no-required-skill-match CVs will appear here.
          </EmptyState>
        ) : (
          <div className="table-scroll">
            <table className="data-table">
              <thead>
                <tr>
                  <th>Candidate</th>
                  <th>Job title</th>
                  <th>CV score</th>
                  <th>Matched skills</th>
                  <th>Missing skills</th>
                  <th>Reason for flagging</th>
                  <th>HR decision</th>
                </tr>
              </thead>
              <tbody>
                {reviewQueue.map((application) => (
                  <tr key={application.application_id}>
                    <td>
                      <strong>{application.candidate_name}</strong>
                      <small>{application.recipient_email}</small>
                    </td>
                    <td>{application.job_title}</td>
                    <td>
                      {application.cv_score == null
                        ? "—"
                        : `${application.cv_score}%`}
                    </td>
                    <td>{application.matched_skills.join(", ") || "None"}</td>
                    <td>{application.missing_skills.join(", ") || "None"}</td>
                    <td>{application.reason}</td>
                    <td>
                      <div className="form-actions">
                        <button
                          type="button"
                          className="button button-primary button-small"
                          disabled={busy}
                          onClick={() =>
                            decideAgentReview(application, "approve")
                          }
                        >
                          Approve
                        </button>
                        <button
                          type="button"
                          className="button button-secondary button-small"
                          disabled={busy}
                          onClick={() =>
                            decideAgentReview(application, "reject")
                          }
                        >
                          Reject
                        </button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Panel>
      {loading && applications.length === 0 ? (
        <LoadingState label="Loading email automation…" />
      ) : applications.length === 0 ? (
        <Panel>
          <EmptyState title="No applications are available">
            Applications and their latest CV scores will appear here.
          </EmptyState>
        </Panel>
      ) : (
        <>
          <Panel className="table-panel" title="Application email status">
            <div className="table-scroll">
              <table className="data-table">
                <thead>
                  <tr>
                    <th>Candidate</th>
                    <th>Job title</th>
                    <th>CV score</th>
                    <th>Email type</th>
                    <th>Recipient email</th>
                    <th>Sending status</th>
                    <th>Sent date and time</th>
                    <th>Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {applications.map((application) => {
                    const latest = application.emails[0];
                    return (
                      <tr
                        key={application.application_id}
                        className={
                          selectedId === application.application_id
                            ? "email-row-selected"
                            : ""
                        }
                      >
                        <td>
                          <button
                            type="button"
                            className="person-button"
                            onClick={() => chooseApplication(application.application_id)}
                          >
                            <span>
                              <strong>{application.candidate_name}</strong>
                              <small>{application.application_status.replaceAll("_", " ")}</small>
                            </span>
                          </button>
                        </td>
                        <td>{application.job_title}</td>
                        <td>{application.cv_score == null ? "—" : `${application.cv_score}%`}</td>
                        <td>{latest ? labelForEmail(latest.email_type) : "—"}</td>
                        <td>{application.recipient_email}</td>
                        <td>
                          <StatusBadge>{latest?.status ?? "not sent"}</StatusBadge>
                        </td>
                        <td>{formatDate(latest?.sent_at)}</td>
                        <td>
                          {application.emails.length > 0 && (
                            <button
                              type="button"
                              className="button button-quiet button-small"
                              aria-label={`Delete email history for ${application.candidate_name}`}
                              title="Delete email history; keep application"
                              disabled={busy}
                              onClick={() => deleteApplicationHistory(application)}
                            >
                              <Trash2 size={14} /> Delete
                            </button>
                          )}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          </Panel>

          {selected && (
            <div className="content-grid content-grid-aside email-automation-detail">
              <Panel
                title="Review and prepare email"
                subtitle={`${selected.candidate_name} · ${selected.job_title} · ${selected.cv_score == null ? "No CV score" : `${selected.cv_score}% CV score`}`}
              >
                <p className="email-consent-summary">
                  Candidate email consent:{" "}
                  <StatusBadge>
                    {selected.email_consent ? "recorded" : "not recorded"}
                  </StatusBadge>
                  {!selected.email_consent && (
                    <> Manage this in the <Link to="/candidates">candidate profile</Link>.</>
                  )}
                </p>
                <label className="field-label" htmlFor="email-type">
                  Email template
                </label>
                <select
                  id="email-type"
                  value={emailType}
                  onChange={(event) => {
                    setEmailType(event.target.value);
                    setPreview(null);
                  }}
                >
                  {emailTypes.map((item) => (
                    <option value={item.value} key={item.value}>{item.label}</option>
                  ))}
                </select>
                {emailType === "interview_invitation" && (
                  <>
                    <label className="field-label" htmlFor="interview-id">
                      Confirmed interview
                    </label>
                    <select
                      id="interview-id"
                      value={interviewId}
                      onChange={(event) => {
                        setInterviewId(event.target.value);
                        setPreview(null);
                      }}
                    >
                      <option value="">Select a real confirmed interview</option>
                      {selectedInterviews
                        .filter(
                          (interview) =>
                            interview.status === "scheduled" &&
                            !interview.test_mode,
                        )
                        .map((interview) => (
                          <option value={interview.id} key={interview.id}>
                            {formatDate(interview.start_at)}
                          </option>
                        ))}
                    </select>
                  </>
                )}
                <div className="form-actions">
                  <button
                    type="button"
                    className="button button-secondary"
                    disabled={
                      busy ||
                      (emailType === "interview_invitation" && !interviewId)
                    }
                    onClick={previewEmail}
                  >
                    <Mail size={16} /> Preview email
                  </button>
                </div>
                {preview && (
                  <section className="email-preview" aria-label="Email preview">
                    <p><strong>To:</strong> {preview.recipient_email}</p>
                    <p><strong>Subject:</strong> {preview.subject}</p>
                    <pre>{preview.body}</pre>
                    {preview.reason && (
                      <p className="form-note">{preview.reason}</p>
                    )}
                    {canDecide && emailType === "selection" && (
                      <button
                        type="button"
                        className="button button-primary"
                        disabled={busy}
                        onClick={() => finishAction("approve")}
                      >
                        <Send size={16} /> Approve and send reviewed email
                      </button>
                    )}
                    {canDecide && emailType === "rejection" && (
                      <button
                        type="button"
                        className="button button-secondary"
                        disabled={busy}
                        onClick={() => finishAction("reject")}
                      >
                        <Send size={16} /> Reject and send reviewed email
                      </button>
                    )}
                    {!canDecide && preview.can_send && (
                      <button
                        type="button"
                        className="button button-primary"
                        disabled={busy}
                        onClick={() => finishAction("send")}
                      >
                        <Send size={16} /> Send reviewed email
                      </button>
                    )}
                    {!canDecide &&
                      !preview.can_send &&
                      selected.application_status === "pending_review" &&
                      emailType !== "interview_invitation" && (
                        <p className="form-note">
                          An HR decision is required before this message can be sent.
                        </p>
                      )}
                  </section>
                )}
              </Panel>

              <Panel
                title="Email history"
                subtitle={`${selected.emails.length} recorded message(s) for this application`}
              >
                {selected.emails.length === 0 ? (
                  <EmptyState title="No email history yet">
                    Automated and manually sent messages will be recorded here.
                  </EmptyState>
                ) : (
                  <div className="email-history-list">
                    {selected.emails.map((email) => (
                      <article className="email-history-item" key={email.id}>
                        <div className="email-history-heading">
                          <strong>{labelForEmail(email.email_type)}</strong>
                          <StatusBadge>{email.status}</StatusBadge>
                        </div>
                        <p>{email.subject}</p>
                        <small>
                          {email.recipient_email} · Created {formatDate(email.created_at)}
                          {email.sent_at ? ` · Sent ${formatDate(email.sent_at)}` : ""}
                        </small>
                        {email.error_message && (
                          <p className="form-note">{email.error_message}</p>
                        )}
                        {email.body && <details>
                          <summary>View email content</summary>
                          <pre>{email.body}</pre>
                        </details>}
                        {email.status !== "sent" && (
                          <button
                            type="button"
                            className="button button-quiet button-small"
                            disabled={busy}
                            onClick={() => retryEmail(email.id)}
                          >
                            <RefreshCw size={14} /> Retry
                          </button>
                        )}
                      </article>
                    ))}
                  </div>
                )}
              </Panel>
            </div>
          )}
        </>
      )}
    </>
  );
}
