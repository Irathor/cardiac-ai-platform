import BiotechIcon from "@mui/icons-material/Biotech";
import ModelTrainingIcon from "@mui/icons-material/ModelTraining";
import ViewInArIcon from "@mui/icons-material/ViewInAr";
import { Box, Button, Card, CardContent, Chip, Container, Fade, Grid, Stack, Typography } from "@mui/material";
import { Link } from "react-router-dom";

import { useBackendLiveness } from "../api/health";

/** Landing page introducing the platform and routing into its two workflows. */
export function DashboardPage() {
  const { data, isLoading, isError } = useBackendLiveness();

  return (
    <Container sx={{ py: 6 }}>
      <Fade in timeout={500}>
        <Box>
          <Chip
            icon={<BiotechIcon fontSize="small" />}
            label="Cardiac MRI Research Platform"
            size="small"
            variant="outlined"
            color="primary"
            sx={{ mb: 2 }}
          />
          <Typography variant="h3" gutterBottom>
            CardiacAI Research Platform
          </Typography>
          <Typography variant="body1" color="text.secondary" sx={{ maxWidth: 640, mb: 3 }}>
            Automated Cardiac MRI Segmentation, Functional Biomarker Extraction and Explainable Disease
            Classification
          </Typography>
          <Stack direction="row" spacing={1} alignItems="center">
            <Typography variant="body2" color="text.secondary">
              Backend:
            </Typography>
            {isLoading && <Chip label="checking..." size="small" />}
            {isError && <Chip label="unreachable" color="error" size="small" />}
            {data?.status === "ok" && (
              <Chip
                label="online"
                color="success"
                size="small"
                sx={{ animation: "pulse-glow 2.2s ease-in-out infinite" }}
              />
            )}
          </Stack>
        </Box>
      </Fade>

      <Grid container spacing={3} sx={{ mt: 4 }}>
        <Grid item xs={12} md={6}>
          <Card sx={{ height: "100%", "&:hover": { borderColor: "primary.main" } }}>
            <CardContent sx={{ p: 3 }}>
              <ViewInArIcon sx={{ color: "primary.main", fontSize: 36, mb: 1 }} />
              <Typography variant="h6" gutterBottom>
                Imaging Viewer
              </Typography>
              <Typography variant="body2" color="text.secondary" sx={{ mb: 3 }}>
                Browse studies, inspect NIfTI series and segmentation overlays, and run AI-assisted
                classification on a study.
              </Typography>
              <Button component={Link} to="/viewer" variant="contained">
                Imaging viewer
              </Button>
            </CardContent>
          </Card>
        </Grid>
        <Grid item xs={12} md={6}>
          <Card sx={{ height: "100%", "&:hover": { borderColor: "secondary.main" } }}>
            <CardContent sx={{ p: 3 }}>
              <ModelTrainingIcon sx={{ color: "secondary.main", fontSize: 36, mb: 1 }} />
              <Typography variant="h6" gutterBottom>
                Model Training
              </Typography>
              <Typography variant="body2" color="text.secondary" sx={{ mb: 3 }}>
                Launch retraining runs and review validation results — segmentation, classification and
                calibration metrics for every model version.
              </Typography>
              <Button component={Link} to="/admin/training" variant="outlined" color="secondary">
                Model training
              </Button>
            </CardContent>
          </Card>
        </Grid>
      </Grid>
    </Container>
  );
}
