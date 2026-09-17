import { Box } from "@mui/material";
import { Route, Routes } from "react-router-dom";

import { ResearchDisclaimerBanner } from "../components/ResearchDisclaimerBanner";
import { SiteHeader } from "../components/SiteHeader";
import { DashboardPage } from "../pages/DashboardPage";
import { ExplainabilityShowcasePage } from "../pages/ExplainabilityShowcasePage";
import { ImagingViewerPage } from "../pages/ImagingViewerPage";
import { ModelTrainingPage } from "../pages/ModelTrainingPage";

export function App() {
  return (
    <Box display="flex" flexDirection="column" minHeight="100vh">
      <SiteHeader />
      <ResearchDisclaimerBanner />
      <Routes>
        <Route path="/" element={<DashboardPage />} />
        <Route path="/viewer" element={<ImagingViewerPage />} />
        <Route path="/admin/training" element={<ModelTrainingPage />} />
        <Route path="/explainability-showcase" element={<ExplainabilityShowcasePage />} />
      </Routes>
    </Box>
  );
}
