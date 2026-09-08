import {
  Alert,
  Box,
  Button,
  Chip,
  Container,
  List,
  ListItemButton,
  ListItemText,
  Stack,
  TextField,
  Typography,
} from "@mui/material";
import { useState } from "react";

import { fetchAnalysis, requestAnalysis, type AIAnalysis } from "../api/analysis";
import { login as loginRequest } from "../api/auth";
import {
  fetchBiomarkers,
  fetchSegmentationFile,
  fetchSegmentationsForSeries,
  fetchSeriesFile,
  fetchSeriesForStudy,
  type BiomarkerMeasurement,
  type ImageSeries,
  type Segmentation,
} from "../api/imaging";
import { NiftiViewer } from "../components/NiftiViewer";

/**
 * Minimal, functional demo page for the Phase 4 imaging viewer — login, pick
 * a study, pick a series, view it with its most recent segmentation overlay
 * and biomarkers. No routing/auth infrastructure exists elsewhere in the
 * frontend yet (see docs/phases.md — the frontend has stayed a Phase 1
 * skeleton while the backend advanced through Phase 3), so this page owns
 * its own login form rather than depending on one that doesn't exist.
 */
export function ImagingViewerPage() {
  const [email, setEmail] = useState("doctor@demo.cardiacai-test.dev");
  const [password, setPassword] = useState("Demo-Password-123!");
  const [token, setToken] = useState<string | null>(null);
  const [loginError, setLoginError] = useState<string | null>(null);

  const [studyId, setStudyId] = useState("");
  const [seriesList, setSeriesList] = useState<ImageSeries[]>([]);
  const [listError, setListError] = useState<string | null>(null);

  const [selectedSeries, setSelectedSeries] = useState<ImageSeries | null>(null);
  const [seriesBlob, setSeriesBlob] = useState<Blob | null>(null);
  const [maskBlob, setMaskBlob] = useState<Blob | null>(null);
  const [biomarkers, setBiomarkers] = useState<BiomarkerMeasurement[]>([]);
  const [viewerError, setViewerError] = useState<string | null>(null);

  const [analysis, setAnalysis] = useState<AIAnalysis | null>(null);
  const [analysisError, setAnalysisError] = useState<string | null>(null);

  async function handleLogin() {
    setLoginError(null);
    try {
      const result = await loginRequest(email, password);
      setToken(result.access_token);
    } catch (err) {
      setLoginError(err instanceof Error ? err.message : "Login failed");
    }
  }

  async function handleLoadSeries() {
    if (!token) return;
    setListError(null);
    setSeriesList([]);
    try {
      setSeriesList(await fetchSeriesForStudy(studyId, token));
    } catch (err) {
      setListError(err instanceof Error ? err.message : "Could not load series");
    }
  }

  async function handleSelectSeries(series: ImageSeries) {
    if (!token) return;
    setViewerError(null);
    setSelectedSeries(series);
    setSeriesBlob(null);
    setMaskBlob(null);
    setBiomarkers([]);
    try {
      const blob = await fetchSeriesFile(series.id, token);
      setSeriesBlob(blob);

      const segmentations: Segmentation[] = await fetchSegmentationsForSeries(series.id, token);
      const latest = segmentations.at(-1);
      if (latest) {
        setMaskBlob(await fetchSegmentationFile(latest.id, token));
        setBiomarkers(await fetchBiomarkers(latest.id, token));
      }
    } catch (err) {
      setViewerError(err instanceof Error ? err.message : "Could not load series");
    }
  }

  async function handleRequestAnalysis() {
    if (!token || !studyId) return;
    setAnalysisError(null);
    setAnalysis(null);
    try {
      let current = await requestAnalysis(studyId, token);
      setAnalysis(current);
      while (current.status === "QUEUED" || current.status === "RUNNING") {
        await new Promise((resolve) => setTimeout(resolve, 1000));
        current = await fetchAnalysis(current.id, token);
        setAnalysis(current);
      }
    } catch (err) {
      setAnalysisError(err instanceof Error ? err.message : "Could not run analysis");
    }
  }

  return (
    <Container sx={{ py: 4 }}>
      <Typography variant="h4" gutterBottom>
        Imaging viewer
      </Typography>

      {!token && (
        <Stack spacing={2} sx={{ maxWidth: 400 }}>
          <TextField label="Email" value={email} onChange={(e) => setEmail(e.target.value)} />
          <TextField
            label="Password"
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
          />
          <Button variant="contained" onClick={handleLogin}>
            Log in
          </Button>
          {loginError && <Alert severity="error">{loginError}</Alert>}
        </Stack>
      )}

      {token && (
        <Stack spacing={3} sx={{ mt: 2 }}>
          <Stack direction="row" spacing={2} alignItems="center">
            <TextField
              label="Study ID"
              value={studyId}
              onChange={(e) => setStudyId(e.target.value)}
              sx={{ minWidth: 340 }}
            />
            <Button variant="outlined" onClick={handleLoadSeries} disabled={!studyId}>
              Load series
            </Button>
            <Button
              variant="outlined"
              color="secondary"
              onClick={handleRequestAnalysis}
              disabled={!studyId || analysis?.status === "QUEUED" || analysis?.status === "RUNNING"}
            >
              Run AI analysis
            </Button>
          </Stack>
          {listError && <Alert severity="error">{listError}</Alert>}
          {analysisError && <Alert severity="error">{analysisError}</Alert>}

          {analysis && (
            <Box>
              <Typography variant="subtitle1">
                AI analysis — {analysis.status}
                {analysis.model_version ? ` (${analysis.model_version})` : ""}
              </Typography>
              {analysis.status === "FAILED" && (
                <Alert severity="warning">{analysis.error_message}</Alert>
              )}
              {analysis.status === "COMPLETED" && analysis.probabilities && (
                <Stack spacing={1}>
                  <Typography variant="body2">
                    Predicted: <strong>{analysis.predicted_class}</strong>
                    {analysis.confidence !== null && ` (confidence ${(analysis.confidence * 100).toFixed(1)}%)`}
                  </Typography>
                  <Stack direction="row" spacing={1} flexWrap="wrap">
                    {Object.entries(analysis.probabilities).map(([cls, prob]) => (
                      <Chip
                        key={cls}
                        label={`${cls}: ${(prob * 100).toFixed(1)}%`}
                        color={cls === analysis.predicted_class ? "primary" : "default"}
                        size="small"
                      />
                    ))}
                  </Stack>
                  {analysis.feature_attributions && (
                    <Stack direction="row" spacing={1} flexWrap="wrap">
                      {Object.entries(analysis.feature_attributions).map(([feature, contribution]) => (
                        <Chip key={feature} variant="outlined" size="small" label={`${feature}: ${contribution.toFixed(2)}`} />
                      ))}
                    </Stack>
                  )}
                </Stack>
              )}
            </Box>
          )}

          <Stack direction="row" spacing={4}>
            <Box sx={{ minWidth: 260 }}>
              <Typography variant="subtitle1">Series</Typography>
              <List dense>
                {seriesList.map((series) => (
                  <ListItemButton
                    key={series.id}
                    selected={selectedSeries?.id === series.id}
                    onClick={() => handleSelectSeries(series)}
                  >
                    <ListItemText
                      primary={`${series.series_type}${series.phase ? ` (${series.phase})` : ""}`}
                      secondary={`${series.shape_x}x${series.shape_y}x${series.shape_z}`}
                    />
                  </ListItemButton>
                ))}
              </List>
            </Box>

            <Box sx={{ flexGrow: 1 }}>
              {viewerError && <Alert severity="error">{viewerError}</Alert>}
              {seriesBlob && (
                <Box sx={{ height: 480, border: "1px solid", borderColor: "divider" }}>
                  <NiftiViewer seriesBlob={seriesBlob} maskBlob={maskBlob} />
                </Box>
              )}
              {biomarkers.length > 0 && (
                <Stack direction="row" spacing={1} sx={{ mt: 2 }} flexWrap="wrap">
                  {biomarkers.map((b) => (
                    <Chip key={b.id} label={`${b.name}: ${b.value.toFixed(2)} ${b.unit}`} />
                  ))}
                </Stack>
              )}
            </Box>
          </Stack>
        </Stack>
      )}
    </Container>
  );
}
