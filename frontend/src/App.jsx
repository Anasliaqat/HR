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
import AuthPage from "./pages/AuthPage";
import CandidatePortalPage from "./pages/CandidatePortalPage";

function NotFoundPage() {
  return <div className="not-found"><p className="eyebrow">404 · Page not found</p><h1>This page isn’t in your workspace.</h1><Link className="button button-primary" to="/login">Login</Link></div>;
}
function HrGuard({children}) {
  const token=localStorage.getItem("hireflow.accessToken");
  return token && localStorage.getItem("hireflow.role")==="hr" ? children : <Navigate to="/login" replace />;
}
function CandidateGuard({children}) {
  const token=localStorage.getItem("hireflow.accessToken");
  return token && localStorage.getItem("hireflow.role")==="candidate" ? children : <Navigate to="/login" replace />;
}
export default function App() {
 return <Routes>
   <Route path="/login" element={<AuthPage/>}/>
   <Route path="/candidate" element={<CandidateGuard><CandidatePortalPage/></CandidateGuard>}/>
   <Route element={<HrGuard><AppLayout/></HrGuard>}>
     <Route index element={<ResumeEvaluationPage/>}/>
     <Route path="dashboard" element={<DashboardPage/>}/>
     <Route path="jobs" element={<JobsPage/>}/>
     <Route path="candidates" element={<CandidatesPage/>}/>
     <Route path="resumes" element={<ResumeEvaluationPage/>}/>
     <Route path="screening" element={<ScreeningPage/>}/>
     <Route path="interviews" element={<InterviewsPage/>}/>
     <Route path="email-automation" element={<EmailAutomationPage/>}/>
     <Route path="settings" element={<SettingsPage/>}/>
   </Route>
   <Route path="404" element={<NotFoundPage/>}/>
   <Route path="*" element={<Navigate to="/login" replace/>}/>
 </Routes>;
}
