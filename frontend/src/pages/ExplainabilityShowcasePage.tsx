import {
  Alert,
  Box,
  Card,
  CardContent,
  Chip,
  CircularProgress,
  Container,
  Fade,
  Stack,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  Typography,
} from "@mui/material";
import { useQuery } from "@tanstack/react-query";
import { useEffect, useState } from "react";

import { ApiError } from "../api/client";
import { login as loginRequest } from "../api/auth";
import {
  fetchExplainabilityShowcase,
  fetchExplainabilityShowcaseImage,
  pngBasename,
  type Cnn3dGradCam,
  type ExplainabilityShowcase,
  type LimeShapleyPanel,
  type UnetSegGradCam,
} from "../api/explainability";
import { LoginCard } from "../components/LoginCard";
import { quietSurface } from "../theme";

/** Exact wording required by EPIC-15's "Contrato técnico" point 5 / ADR-3 —
 * this banner must stay visible the whole time the page is mounted, it is
 * never a dismissible tooltip or footnote. */
const PEDAGOGICAL_DISCLAIMER =
  "Esta página es una comparación pedagógica offline, no una explicación de producción — ver ADR-3.";

const SHOWCASE_NOT_GENERATED_MESSAGE =
  "Explainability showcase not generated in this environment. Run ml/scripts/run_explainability_showcase.py first.";

/** Fetches one showcase PNG (auth required, so it can't be a plain <img src>)
 * and turns it into a short-lived object URL — same pattern as NiftiViewer /
 * ImagingViewerPage for series/mask blobs. */
function ShowcaseImage({ filename, alt, token }: { filename: string; alt: string; token: string }) {
  const imageQuery = useQuery({
    queryKey: ["explainability-showcase-image", filename, token],
    queryFn: () => fetchExplainabilityShowcaseImage(filename, token),
  });
  const [objectUrl, setObjectUrl] = useState<string | null>(null);

  useEffect(() => {
    if (!imageQuery.data) {
      setObjectUrl(null);
      return;
    }
    const url = URL.createObjectURL(imageQuery.data);
    setObjectUrl(url);
    return () => URL.revokeObjectURL(url);
  }, [imageQuery.data]);

  if (imageQuery.isLoading) {
    return (
      <Box sx={{ display: "flex", alignItems: "center", justifyContent: "center", height: 160 }}>
        <CircularProgress size={28} aria-label={`Loading ${alt}`} />
      </Box>
    );
  }
  if (imageQuery.isError || !objectUrl) {
    return <Alert severity="error">Could not load image ({filename}).</Alert>;
  }
  return (
    <Box
      component="img"
      src={objectUrl}
      alt={alt}
      sx={{ display: "block", width: "100%", maxWidth: 320, height: "auto", borderRadius: 1 }}
    />
  );
}

function UnetGradCamSection({ data, token }: { data: UnetSegGradCam; token: string }) {
  const structureEntries = Object.entries(data.structures ?? {});
  return (
    <Card sx={quietSurface()}>
      <CardContent>
        <Typography variant="h6" gutterBottom>
          Seg-Grad-CAM — U-Net
        </Typography>
        <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
          {data.patient_id ? `Patient ${data.patient_id}` : "Patient"}
          {typeof data.slice_index === "number" ? `, slice ${data.slice_index}` : ""} — one Grad-CAM map per
          segmented structure.
        </Typography>
        <Stack direction="row" spacing={2} flexWrap="wrap" useFlexGap>
          {structureEntries.map(([structure, structureData]) => (
            <Box key={structure} sx={{ minWidth: 220 }}>
              <Typography variant="subtitle2" gutterBottom>
                {structure}
              </Typography>
              <ShowcaseImage
                filename={pngBasename(structureData.png_path)}
                alt={`Seg-Grad-CAM for the ${structure} structure, U-Net${
                  data.patient_id ? `, patient ${data.patient_id}` : ""
                }`}
                token={token}
              />
            </Box>
          ))}
          {structureEntries.length === 0 && (
            <Typography variant="body2" color="text.secondary">
              No structures in this showcase.
            </Typography>
          )}
        </Stack>
      </CardContent>
    </Card>
  );
}

function Cnn3dGradCamSection({ data, token }: { data: Cnn3dGradCam; token: string }) {
  return (
    <Card sx={quietSurface()}>
      <CardContent>
        <Typography variant="h6" gutterBottom>
          Grad-CAM — CNN3D
        </Typography>
        <Stack direction="row" spacing={1} sx={{ mb: 2 }} flexWrap="wrap" useFlexGap>
          {data.predicted_class && <Chip size="small" label={`Predicted: ${data.predicted_class}`} />}
          {data.true_class && <Chip size="small" variant="outlined" label={`True: ${data.true_class}`} />}
        </Stack>
        <Box sx={{ maxWidth: 320 }}>
          <ShowcaseImage
            filename={pngBasename(data.png_path)}
            alt={`Grad-CAM for the CNN3D classifier${data.patient_id ? `, patient ${data.patient_id}` : ""}`}
            token={token}
          />
        </Box>
      </CardContent>
    </Card>
  );
}

function LimeShapleyPanelSection({ data }: { data: LimeShapleyPanel }) {
  // Method labels are shown exactly as the backend returns them (the
  // literal ADR-3 labels "LIME (aproximado)" / "Shapley (exacto)") — never
  // renamed or translated by the frontend, see EPIC-15.
  const methodLabels = Object.keys(data.method_attributions ?? {});
  const featureNames = Array.from(
    new Set(methodLabels.flatMap((label) => Object.keys(data.method_attributions[label] ?? {}))),
  );

  return (
    <Card sx={quietSurface()}>
      <CardContent>
        <Typography variant="h6" gutterBottom>
          LIME vs. Shapley
        </Typography>
        {data.predicted_class && (
          <Typography variant="body2" color="text.secondary" sx={{ mb: 1 }}>
            Predicted class: <strong>{data.predicted_class}</strong>
          </Typography>
        )}
        <TableContainer>
          <Table size="small" aria-label="Feature attributions, LIME vs. Shapley">
            <TableHead>
              <TableRow>
                <TableCell>Feature</TableCell>
                {methodLabels.map((label) => (
                  <TableCell key={label} align="right">
                    {label}
                  </TableCell>
                ))}
              </TableRow>
            </TableHead>
            <TableBody>
              {featureNames.map((feature) => (
                <TableRow key={feature}>
                  <TableCell component="th" scope="row">
                    {feature}
                  </TableCell>
                  {methodLabels.map((label) => {
                    const value = data.method_attributions[label]?.[feature];
                    return (
                      <TableCell key={label} align="right">
                        {typeof value === "number" ? value.toFixed(4) : "—"}
                      </TableCell>
                    );
                  })}
                </TableRow>
              ))}
              {featureNames.length === 0 && (
                <TableRow>
                  <TableCell colSpan={methodLabels.length + 1}>
                    <Typography variant="body2" color="text.secondary">
                      No feature attributions in this showcase.
                    </Typography>
                  </TableCell>
                </TableRow>
              )}
            </TableBody>
          </Table>
        </TableContainer>
        {data.note && (
          <Typography variant="caption" color="text.secondary" sx={{ display: "block", mt: 2 }}>
            {data.note}
          </Typography>
        )}
      </CardContent>
    </Card>
  );
}

function ShowcaseContent({ data, token }: { data: ExplainabilityShowcase; token: string }) {
  return (
    <Stack spacing={3}>
      <UnetGradCamSection data={data.unet_seg_grad_cam} token={token} />
      <Cnn3dGradCamSection data={data.cnn3d_grad_cam} token={token} />
      <LimeShapleyPanelSection data={data.lime_shapley_panel} />
    </Stack>
  );
}

/**
 * Pedagogical showcase of Grad-CAM (U-Net segmentation, CNN3D classification)
 * and the LIME-vs-Shapley panel — read-only, all artifacts pre-generated
 * offline by ml/scripts/run_explainability_showcase.py (EPIC-1). Deliberately
 * separate from any clinical flow (/viewer, an AIAnalysis report): see
 * EPIC-15's "Contrato técnico" and ADR-3. Owns its own login form, same
 * pattern as ImagingViewerPage/ModelTrainingPage — no shared auth store
 * exists yet.
 */
export function ExplainabilityShowcasePage() {
  const [email, setEmail] = useState("admin@demo.cardiacai-test.dev");
  const [password, setPassword] = useState("Demo-Password-123!");
  const [token, setToken] = useState<string | null>(null);
  const [loginError, setLoginError] = useState<string | null>(null);

  async function handleLogin() {
    setLoginError(null);
    try {
      const result = await loginRequest(email, password);
      setToken(result.access_token);
    } catch (err) {
      setLoginError(err instanceof Error ? err.message : "Login failed");
    }
  }

  const showcaseQuery = useQuery({
    queryKey: ["explainability-showcase", token],
    queryFn: () => fetchExplainabilityShowcase(token as string),
    enabled: !!token,
    retry: false,
  });

  const isNotGenerated = showcaseQuery.error instanceof ApiError && showcaseQuery.error.status === 404;

  return (
    <Container sx={{ py: 4 }}>
      <Typography variant="h4" gutterBottom>
        Explainability showcase
      </Typography>
      <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
        Grad-CAM maps and the LIME-vs-Shapley comparison panel generated offline by EPIC-1's showcase script.
      </Typography>

      {/* Permanent, non-dismissible — must stay visible the whole time this
          page is in use, regardless of login/loading/error state. */}
      <Alert severity="warning" variant="filled" sx={{ mb: 3, fontWeight: 600 }}>
        {PEDAGOGICAL_DISCLAIMER}
      </Alert>

      {!token && (
        <LoginCard
          title="Sign in to the explainability showcase"
          email={email}
          password={password}
          error={loginError}
          onEmailChange={setEmail}
          onPasswordChange={setPassword}
          onSubmit={handleLogin}
        />
      )}

      {token && (
        <Fade in timeout={400}>
          <Box sx={{ mt: 2 }}>
            {showcaseQuery.isLoading && (
              <Box sx={{ display: "flex", alignItems: "center", justifyContent: "center", py: 6 }}>
                <CircularProgress aria-label="Loading explainability showcase" />
              </Box>
            )}
            {showcaseQuery.isError && isNotGenerated && (
              <Alert severity="info">{SHOWCASE_NOT_GENERATED_MESSAGE}</Alert>
            )}
            {showcaseQuery.isError && !isNotGenerated && (
              <Alert severity="error">
                {showcaseQuery.error instanceof Error
                  ? showcaseQuery.error.message
                  : "Could not load the explainability showcase."}
              </Alert>
            )}
            {showcaseQuery.data && <ShowcaseContent data={showcaseQuery.data} token={token} />}
          </Box>
        </Fade>
      )}
    </Container>
  );
}
