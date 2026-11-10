import axios from "axios";

export const API_BASE_URL = (
  import.meta.env.VITE_API_BASE_URL || "http://127.0.0.1:8000/api"
).replace(/\/+$/, "");

const client = axios.create({
  baseURL: API_BASE_URL,
  timeout: 30000,
});

client.interceptors.response.use(
  (response) => response,
  (error) => {
    const requestError = new Error(
      error.response?.data?.detail ??
        (error.code === "ECONNABORTED"
          ? "The HR API request timed out. Please try again."
          : error.request
            ? `Unable to reach the HR API at ${API_BASE_URL}. Check that the backend is running and CORS is configured.`
            : null) ??
        error.message ??
        "The request could not be completed.",
    );
    requestError.status = error.response?.status;
    return Promise.reject(requestError);
  },
);

export const api = {
  getJobs: () => client.get("/jobs").then(({ data }) => data),
  createJob: (payload) =>
    client.post("/jobs", payload).then(({ data }) => data),
  updateJob: (id, payload) =>
    client.put(`/jobs/${id}`, payload).then(({ data }) => data),
  deleteJob: (id) => client.delete(`/jobs/${id}`),
  getCandidates: () => client.get("/candidates").then(({ data }) => data),
  createCandidate: (payload) =>
    client.post("/candidates", payload).then(({ data }) => data),
  updateCandidate: (id, payload) =>
    client.put(`/candidates/${id}`, payload).then(({ data }) => data),
  approveCandidate: (id) =>
    client.post(`/candidates/${id}/approve`).then(({ data }) => data),
  updateCandidateEmailConsent: (id, emailConsent) =>
    client
      .put(`/candidates/${id}/email-consent`, { email_consent: emailConsent })
      .then(({ data }) => data),
  getApplications: () => client.get("/applications").then(({ data }) => data),
  createApplication: (payload) =>
    client.post("/applications", payload).then(({ data }) => data),
  updateApplication: (id, payload) =>
    client.patch(`/applications/${id}`, payload).then(({ data }) => data),
  getResumes: () => client.get("/resumes").then(({ data }) => data),
  deleteResume: (id) => client.delete(`/resumes/${id}`),
  uploadResume: (payload, onUploadProgress) =>
    client
      .post("/resumes/upload", payload, { onUploadProgress })
      .then(({ data }) => data),
  evaluateResume: (id, payload) =>
    client.post(`/resumes/${id}/evaluate`, payload).then(({ data }) => data),
  startResumeEvaluation: (id, payload) =>
    client.post(`/resumes/${id}/evaluate/async`, payload).then(({ data }) => data),
  getResumeStatus: (id) =>
    client.get(`/resumes/${id}/status`).then(({ data }) => data),
  getResumeScore: (id) =>
    client.get(`/resumes/${id}/score`).then(({ data }) => data),
  getScreening: (candidateId) =>
    client.get(`/screening/${candidateId}`).then(({ data }) => data),
  getScreenings: () => client.get("/screening").then(({ data }) => data),
  getScreeningRecord: (screeningId) =>
    client.get(`/screening/records/${screeningId}`).then(({ data }) => data),
  startScreening: (candidateId, payload) =>
    client
      .post(`/screening/${candidateId}/start`, payload)
      .then(({ data }) => data),
  getInterviews: () => client.get("/interviews").then(({ data }) => data),
  getInterviewers: () =>
    client.get("/interviews/interviewers").then(({ data }) => data),
  getAvailableSlots: (params) =>
    client.get("/interviews/available-slots", { params }).then(({ data }) => data),
  scheduleInterview: (payload) =>
    client.post("/interviews/schedule", payload).then(({ data }) => data),
  rescheduleInterview: (id, payload) =>
    client.put(`/interviews/${id}/reschedule`, payload).then(({ data }) => data),
  updateInterview: (id, payload) =>
    client.patch(`/interviews/${id}`, payload).then(({ data }) => data),
  getEmailApplications: () =>
    client.get("/email-automation/applications").then(({ data }) => data),
  getAgentReviewQueue: () =>
    client.get("/email-automation/review-queue").then(({ data }) => data),
  decideAgentReview: (applicationId, decision) =>
    client
      .post(`/email-automation/review-queue/${applicationId}/decision`, {
        decision,
      })
      .then(({ data }) => data),
  getEmailHistory: () =>
    client.get("/email-automation/history").then(({ data }) => data),
  previewEmail: (applicationId, emailType, interviewId) =>
    client
      .get(`/email-automation/applications/${applicationId}/preview`, {
        params: {
          email_type: emailType,
          ...(interviewId ? { interview_id: interviewId } : {}),
        },
      })
      .then(({ data }) => data),
  recordEmailDecision: (applicationId, decision) =>
    client
      .post(`/email-automation/applications/${applicationId}/decision`, {
        decision,
      })
      .then(({ data }) => data),
  sendEmail: (applicationId, emailType, interviewId) =>
    client
      .post(`/email-automation/applications/${applicationId}/send`, {
        email_type: emailType,
        ...(interviewId ? { interview_id: interviewId } : {}),
      })
      .then(({ data }) => data),
  retryEmail: (emailId) =>
    client.post(`/email-automation/history/${emailId}/retry`).then(({ data }) => data),
  deleteApplicationEmailHistory: (applicationId) =>
    client.delete(`/email-automation/applications/${applicationId}/history`),
  deleteEmailHistoryRecord: (emailId) =>
    client.delete(`/email-automation/history/${emailId}`),
};

export default client;
