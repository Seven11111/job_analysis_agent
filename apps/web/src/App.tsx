import { BrowserRouter, Route, Routes } from "react-router-dom";

import { AppLayout } from "./components/AppLayout";
import { AgentPage } from "./pages/AgentPage";
import { JobManagementPage } from "./pages/JobManagementPage";
import { JobSearchPage } from "./pages/JobSearchPage";
import { JobSubscriptionsPage } from "./pages/JobSubscriptionsPage";
import { ProfilePage } from "./pages/ProfilePage";
import { WorkbenchPage } from "./pages/WorkbenchPage";

export function App() {
  return <BrowserRouter><Routes><Route element={<AppLayout />}><Route index element={<WorkbenchPage />} /><Route path="jobs/search" element={<JobSearchPage />} /><Route path="jobs/subscriptions" element={<JobSubscriptionsPage />} /><Route path="jobs/manage" element={<JobManagementPage />} /><Route path="profile" element={<ProfilePage />} /><Route path="agent" element={<AgentPage />} /></Route></Routes></BrowserRouter>;
}
