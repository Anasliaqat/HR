import { Link, Navigate, Route, Routes } from "react-router-dom";
import AppLayout from "./layout/AppLayout";
import CandidatesPage from "./pages/CandidatesPage";
import DashboardPage from "./pages/DashboardPage";
import InterviewsPage from "./pages/InterviewsPage";
import EmailAutomationPage from "./pages/EmailAutomationPage";
import JobsPage from "./pages/JobsPage";
import ResumeEvaluationPage from "./pages/ResumeEvaluationPage";
import ScreeningPage from "./pages/ScreeningPage";
import SettingsPage from "./pages/SettingsPage";

function NotFoundPage() {
  return (
    <div className="not-found">
      <p className="eyebrow">404 · Page not found</p>
      <h1>This page isn’t in your workspace.</h1>
      <Link className="button button-primary" to="/">
        Evaluate a CV
      </Link>
    </div>
  );
}

export default function App() {
  return (
    <Routes>
      <Route element={<AppLayout />}>
        <Route index element={<ResumeEvaluationPage />} />
        <Route path="dashboard" element={<DashboardPage />} />
        <Route path="jobs" element={<JobsPage />} />
        <Route path="candidates" element={<CandidatesPage />} />
        <Route path="resumes" element={<ResumeEvaluationPage />} />
        <Route path="screening" element={<ScreeningPage />} />
        <Route path="interviews" element={<InterviewsPage />} />
        <Route path="email-automation" element={<EmailAutomationPage />} />
        <Route path="settings" element={<SettingsPage />} />
      </Route>
      <Route path="404" element={<NotFoundPage />} />
      <Route path="*" element={<Navigate to="/404" replace />} />
    </Routes>
  );
}
