import { Box, Chip, Container, Link as MuiLink, Stack, Typography } from "@mui/material";
import { Link, Route, Routes } from "react-router-dom";

import { useBackendLiveness } from "../api/health";
import { ResearchDisclaimerBanner } from "../components/ResearchDisclaimerBanner";
import { ImagingViewerPage } from "../pages/ImagingViewerPage";

function Dashboard() {
  const { data, isLoading, isError } = useBackendLiveness();

  return (
    <Container sx={{ py: 4 }}>
      <Typography variant="h4" gutterBottom>
        CardiacAI Research Platform
      </Typography>
      <Typography variant="body1" color="text.secondary" gutterBottom>
        Automated Cardiac MRI Segmentation, Functional Biomarker Extraction and
        Explainable Disease Classification
      </Typography>
      <Stack direction="row" spacing={1} alignItems="center" sx={{ mt: 2 }}>
        <Typography variant="body2">Backend:</Typography>
        {isLoading && <Chip label="checking..." size="small" />}
        {isError && <Chip label="unreachable" color="error" size="small" />}
        {data?.status === "ok" && <Chip label="online" color="success" size="small" />}
      </Stack>
      <MuiLink component={Link} to="/viewer" sx={{ mt: 3, display: "inline-block" }}>
        Imaging viewer
      </MuiLink>
    </Container>
  );
}

export function App() {
  return (
    <Box display="flex" flexDirection="column" minHeight="100vh">
      <ResearchDisclaimerBanner />
      <Routes>
        <Route path="/" element={<Dashboard />} />
        <Route path="/viewer" element={<ImagingViewerPage />} />
      </Routes>
    </Box>
  );
}
