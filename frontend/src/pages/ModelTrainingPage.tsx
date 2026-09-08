import {
  Alert,
  Box,
  Button,
  Container,
  FormControl,
  InputLabel,
  List,
  ListItemButton,
  ListItemText,
  MenuItem,
  Select,
  type SelectChangeEvent,
  Stack,
  Tab,
  Tabs,
  TextField,
  Typography,
} from "@mui/material";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";

import { login as loginRequest } from "../api/auth";
import { listDatasets, listDatasetVersions } from "../api/datasets";
import {
  getTrainingRun,
  listModelEvaluations,
  listModelVersions,
  listTrainingRunsForVersion,
  requestTrainingRun,
  MODEL_NAME_CNN3D,
  MODEL_NAME_NEAREST_CENTROID,
  MODEL_NAME_UNET,
  type Cnn3dMetrics,
  type ModelEvaluationOut,
  type ModelVersionOut,
  type NearestCentroidMetrics,
  type TrainingModelType,
  type UnetMetrics,
} from "../api/training";
import { CalibrationTab } from "../components/training/CalibrationTab";
import { ClassificationTab } from "../components/training/ClassificationTab";
import { SegmentationTab } from "../components/training/SegmentationTab";
import { SummaryTab } from "../components/training/SummaryTab";
import { ValidationTab } from "../components/training/ValidationTab";

const MODEL_TYPE_OPTIONS: Array<{ value: TrainingModelType; label: string }> = [
  { value: "NEAREST_CENTROID", label: "Biomarker classifier (nearest-centroid)" },
  { value: "UNET_SEGMENTATION", label: "U-Net segmentation" },
  { value: "CNN3D_CLASSIFICATION", label: "CNN3D classification" },
];

type TabKey = "summary" | "segmentation" | "classification" | "calibration" | "validation";

function tabsForModel(name: string): Array<{ key: TabKey; label: string }> {
  if (name === MODEL_NAME_UNET) {
    return [
      { key: "summary", label: "Summary" },
      { key: "segmentation", label: "Segmentation" },
      { key: "validation", label: "Validation" },
    ];
  }
  if (name === MODEL_NAME_CNN3D) {
    return [
      { key: "summary", label: "Summary" },
      { key: "classification", label: "Classification" },
      { key: "calibration", label: "Calibration" },
      { key: "validation", label: "Validation" },
    ];
  }
  return [
    { key: "summary", label: "Summary" },
    { key: "classification", label: "Classification" },
    { key: "validation", label: "Validation" },
  ];
}

/**
 * Admin/ML-engineer page: pick a model type to retrain, watch the run, then
 * browse any past model version's full validation results. No shared
 * auth/routing exists yet (see ImagingViewerPage.tsx) — this page owns its
 * own login form too, following that same pattern.
 */
export function ModelTrainingPage() {
  const [email, setEmail] = useState("admin@demo.cardiacai-test.dev");
  const [password, setPassword] = useState("Demo-Password-123!");
  const [token, setToken] = useState<string | null>(null);
  const [loginError, setLoginError] = useState<string | null>(null);

  const [modelType, setModelType] = useState<TrainingModelType>("NEAREST_CENTROID");
  const [datasetId, setDatasetId] = useState("");
  const [versionId, setVersionId] = useState("");
  const [requestError, setRequestError] = useState<string | null>(null);
  const [activeRunId, setActiveRunId] = useState<string | null>(null);

  const [selectedModelVersionId, setSelectedModelVersionId] = useState<string | null>(null);
  const [activeTab, setActiveTab] = useState<TabKey>("summary");

  const queryClient = useQueryClient();

  const datasetsQuery = useQuery({
    queryKey: ["datasets", token],
    queryFn: () => listDatasets(token as string),
    enabled: !!token,
  });

  const versionsQuery = useQuery({
    queryKey: ["dataset-versions", datasetId, token],
    queryFn: () => listDatasetVersions(datasetId, token as string),
    enabled: !!token && !!datasetId,
  });

  // Both nearest-centroid and the DL model types need *some* dataset version
  // in the request URL (see requestTrainingRun) — auto-pick the first one so
  // the DL path works without asking the user to pick a meaningless value.
  useEffect(() => {
    if (!datasetId && datasetsQuery.data && datasetsQuery.data.length > 0) {
      setDatasetId(datasetsQuery.data[0].id);
    }
  }, [datasetsQuery.data, datasetId]);

  useEffect(() => {
    if (!versionId && versionsQuery.data && versionsQuery.data.length > 0) {
      setVersionId(versionsQuery.data[0].id);
    }
  }, [versionsQuery.data, versionId]);

  const activeRunQuery = useQuery({
    queryKey: ["training-run", activeRunId],
    queryFn: () => getTrainingRun(activeRunId as string, token as string),
    enabled: !!token && !!activeRunId,
    refetchInterval: (query) => {
      const status = query.state.data?.status;
      return status === "RUNNING" || status === "QUEUED" ? 5000 : false;
    },
  });

  const runsHistoryQuery = useQuery({
    queryKey: ["training-runs", datasetId, versionId, token],
    queryFn: () => listTrainingRunsForVersion(datasetId, versionId, token as string),
    enabled: !!token && !!datasetId && !!versionId,
  });

  const modelVersionsQuery = useQuery({
    queryKey: ["model-versions", token],
    queryFn: () => listModelVersions(token as string),
    enabled: !!token,
  });

  const evaluationsQuery = useQuery({
    queryKey: ["model-evaluations", selectedModelVersionId, token],
    queryFn: () => listModelEvaluations(selectedModelVersionId as string, token as string),
    enabled: !!token && !!selectedModelVersionId,
  });

  useEffect(() => {
    if (activeRunQuery.data?.status === "COMPLETED") {
      queryClient.invalidateQueries({ queryKey: ["model-versions", token] });
    }
  }, [activeRunQuery.data?.status, queryClient, token]);

  async function handleLogin() {
    setLoginError(null);
    try {
      const result = await loginRequest(email, password);
      setToken(result.access_token);
    } catch (err) {
      setLoginError(err instanceof Error ? err.message : "Login failed");
    }
  }

  async function handleStartTraining() {
    if (!token || !datasetId || !versionId) return;
    setRequestError(null);
    try {
      const run = await requestTrainingRun(datasetId, versionId, modelType, token);
      setActiveRunId(run.id);
    } catch (err) {
      setRequestError(err instanceof Error ? err.message : "Could not start training run");
    }
  }

  function handleSelectModelVersion(version: ModelVersionOut) {
    setSelectedModelVersionId(version.id);
    setActiveTab("summary");
  }

  const isRunInFlight = activeRunQuery.data?.status === "RUNNING" || activeRunQuery.data?.status === "QUEUED";
  const isDlModel = modelType !== "NEAREST_CENTROID";

  const sortedModelVersions: ModelVersionOut[] = [...(modelVersionsQuery.data ?? [])].sort(
    (a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime(),
  );

  const selectedModelVersion = sortedModelVersions.find((v) => v.id === selectedModelVersionId) ?? null;
  const selectedEvaluation: ModelEvaluationOut | null =
    evaluationsQuery.data?.find((e) => e.split === "TEST") ?? evaluationsQuery.data?.[0] ?? null;

  const tabs = selectedModelVersion ? tabsForModel(selectedModelVersion.name) : [];

  return (
    <Container sx={{ py: 4 }}>
      <Typography variant="h4" gutterBottom>
        Model training
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
        <Stack spacing={4} sx={{ mt: 2 }}>
          <Box>
            <Typography variant="h6" gutterBottom>
              Retrain
            </Typography>
            <Stack direction="row" spacing={2} alignItems="center" flexWrap="wrap">
              <FormControl size="small" sx={{ minWidth: 320 }}>
                <InputLabel id="model-type-label">Model</InputLabel>
                <Select
                  labelId="model-type-label"
                  label="Model"
                  value={modelType}
                  onChange={(e: SelectChangeEvent<TrainingModelType>) =>
                    setModelType(e.target.value as TrainingModelType)
                  }
                >
                  {MODEL_TYPE_OPTIONS.map((opt) => (
                    <MenuItem key={opt.value} value={opt.value}>
                      {opt.label}
                    </MenuItem>
                  ))}
                </Select>
              </FormControl>

              {!isDlModel && (
                <FormControl size="small" sx={{ minWidth: 220 }}>
                  <InputLabel id="dataset-label">Dataset</InputLabel>
                  <Select
                    labelId="dataset-label"
                    label="Dataset"
                    value={datasetId}
                    onChange={(e: SelectChangeEvent) => setDatasetId(e.target.value)}
                  >
                    {(datasetsQuery.data ?? []).map((d) => (
                      <MenuItem key={d.id} value={d.id}>
                        {d.name}
                      </MenuItem>
                    ))}
                  </Select>
                </FormControl>
              )}

              {!isDlModel && (
                <FormControl size="small" sx={{ minWidth: 220 }}>
                  <InputLabel id="version-label">Dataset version</InputLabel>
                  <Select
                    labelId="version-label"
                    label="Dataset version"
                    value={versionId}
                    onChange={(e: SelectChangeEvent) => setVersionId(e.target.value)}
                  >
                    {(versionsQuery.data ?? []).map((v) => (
                      <MenuItem key={v.id} value={v.id}>
                        v{v.version_number} ({v.status})
                      </MenuItem>
                    ))}
                  </Select>
                </FormControl>
              )}

              <Button
                variant="contained"
                onClick={handleStartTraining}
                disabled={!datasetId || !versionId || isRunInFlight}
              >
                Start training
              </Button>
            </Stack>

            {isDlModel && (
              <Typography variant="caption" color="text.secondary" sx={{ display: "block", mt: 1 }}>
                For deep-learning models, the dataset version is only an audit identifier for the request
                URL — it is not used as the data source (these models always train against the fixed ACDC
                dataset already on disk).
              </Typography>
            )}

            {requestError && (
              <Alert severity="error" sx={{ mt: 2 }}>
                {requestError}
              </Alert>
            )}

            {activeRunQuery.data && (
              <Alert severity={activeRunQuery.data.status === "FAILED" ? "error" : "info"} sx={{ mt: 2 }}>
                Run {activeRunQuery.data.id} — {activeRunQuery.data.status}
                {activeRunQuery.data.status === "FAILED" && activeRunQuery.data.error_message
                  ? `: ${activeRunQuery.data.error_message}`
                  : ""}
              </Alert>
            )}
          </Box>

          <Stack direction="row" spacing={4}>
            <Box sx={{ minWidth: 280 }}>
              <Typography variant="h6" gutterBottom>
                History
              </Typography>
              <List dense>
                {sortedModelVersions.map((version) => (
                  <ListItemButton
                    key={version.id}
                    selected={selectedModelVersionId === version.id}
                    onClick={() => handleSelectModelVersion(version)}
                  >
                    <ListItemText
                      primary={version.name}
                      secondary={`${version.status} — ${new Date(version.created_at).toLocaleString()}`}
                    />
                  </ListItemButton>
                ))}
              </List>
            </Box>

            <Box sx={{ flexGrow: 1 }}>
              {selectedModelVersion && selectedEvaluation && (
                <Box>
                  <Tabs value={activeTab} onChange={(_, value: TabKey) => setActiveTab(value)} sx={{ mb: 2 }}>
                    {tabs.map((tab) => (
                      <Tab key={tab.key} value={tab.key} label={tab.label} />
                    ))}
                  </Tabs>

                  {activeTab === "summary" && (
                    <SummaryTab
                      modelVersion={selectedModelVersion}
                      evaluation={selectedEvaluation}
                      runsHistory={runsHistoryQuery.data ?? []}
                    />
                  )}
                  {activeTab === "segmentation" && selectedModelVersion.name === MODEL_NAME_UNET && (
                    <SegmentationTab metrics={selectedEvaluation.metrics as unknown as UnetMetrics} />
                  )}
                  {activeTab === "classification" && selectedModelVersion.name === MODEL_NAME_CNN3D && (
                    <ClassificationTab cnn3dMetrics={selectedEvaluation.metrics as unknown as Cnn3dMetrics} />
                  )}
                  {activeTab === "classification" && selectedModelVersion.name === MODEL_NAME_NEAREST_CENTROID && (
                    <ClassificationTab
                      simpleMetrics={selectedEvaluation.metrics as unknown as NearestCentroidMetrics}
                    />
                  )}
                  {activeTab === "calibration" && selectedModelVersion.name === MODEL_NAME_CNN3D && (
                    <CalibrationTab
                      report={(selectedEvaluation.metrics as unknown as Cnn3dMetrics).external_test.validation}
                    />
                  )}
                  {activeTab === "validation" && (
                    <ValidationTab
                      unetMetrics={
                        selectedModelVersion.name === MODEL_NAME_UNET
                          ? (selectedEvaluation.metrics as unknown as UnetMetrics)
                          : undefined
                      }
                      cnn3dMetrics={
                        selectedModelVersion.name === MODEL_NAME_CNN3D
                          ? (selectedEvaluation.metrics as unknown as Cnn3dMetrics)
                          : undefined
                      }
                    />
                  )}
                </Box>
              )}
              {selectedModelVersion && !selectedEvaluation && (
                <Typography color="text.secondary">No evaluation results for this model version yet.</Typography>
              )}
              {!selectedModelVersion && (
                <Typography color="text.secondary">
                  Select a model version from the history to view its results.
                </Typography>
              )}
            </Box>
          </Stack>
        </Stack>
      )}
    </Container>
  );
}
