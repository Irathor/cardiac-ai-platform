import BiotechIcon from "@mui/icons-material/Biotech";
import ModelTrainingIcon from "@mui/icons-material/ModelTraining";
import ViewInArIcon from "@mui/icons-material/ViewInAr";
import { alpha, Box, Button, Card, CardContent, Chip, Container, Fade, Grid, Stack, Typography } from "@mui/material";
import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";

import { useBackendLiveness } from "../api/health";
import { tokens } from "../theme";

/** Landing page introducing the platform and routing into its two workflows. */
export function DashboardPage() {
  const { data, isLoading, isError } = useBackendLiveness();
  const { t } = useTranslation();

  return (
    <Container sx={{ py: 6 }}>
      <Fade in timeout={500}>
        <Box>
          <Chip
            icon={<BiotechIcon fontSize="small" />}
            label={t("dashboard.eyebrow")}
            size="small"
            variant="outlined"
            color="primary"
            sx={{ mb: 2 }}
          />
          <Typography variant="h3" gutterBottom>
            {t("dashboard.title")}
          </Typography>
          <Typography variant="body1" color="text.secondary" sx={{ maxWidth: 640, mb: 3 }}>
            {t("dashboard.subtitle")}
          </Typography>
          <Stack direction="row" spacing={1} alignItems="center">
            <Typography variant="body2" color="text.secondary">
              {t("dashboard.backendLabel")}
            </Typography>
            {isLoading && <Chip label={t("dashboard.backendChecking")} size="small" />}
            {isError && <Chip label={t("dashboard.backendUnreachable")} color="error" size="small" />}
            {data?.status === "ok" && (
              <Chip
                label={t("dashboard.backendOnline")}
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
          <Card
            sx={{
              height: "100%",
              borderColor: alpha(tokens.cyan, 0.18),
              transition: "border-color 200ms ease",
              "&:hover": { borderColor: alpha(tokens.cyan, 0.5) },
            }}
          >
            <CardContent sx={{ p: 3 }}>
              <ViewInArIcon sx={{ color: "primary.main", fontSize: 32, mb: 1 }} />
              <Typography variant="h6" gutterBottom>
                {t("dashboard.imagingViewerTitle")}
              </Typography>
              <Typography variant="body2" color="text.secondary" sx={{ mb: 3 }}>
                {t("dashboard.imagingViewerDescription")}
              </Typography>
              <Button component={Link} to="/viewer" variant="contained">
                {t("dashboard.imagingViewerTitle")}
              </Button>
            </CardContent>
          </Card>
        </Grid>
        <Grid item xs={12} md={6}>
          <Card
            sx={{
              height: "100%",
              borderColor: alpha(tokens.violet, 0.18),
              transition: "border-color 200ms ease",
              "&:hover": { borderColor: alpha(tokens.violet, 0.5) },
            }}
          >
            <CardContent sx={{ p: 3 }}>
              <ModelTrainingIcon sx={{ color: "secondary.main", fontSize: 32, mb: 1 }} />
              <Typography variant="h6" gutterBottom>
                {t("dashboard.modelTrainingTitle")}
              </Typography>
              <Typography variant="body2" color="text.secondary" sx={{ mb: 3 }}>
                {t("dashboard.modelTrainingDescription")}
              </Typography>
              <Button component={Link} to="/admin/training" variant="outlined" color="secondary">
                {t("dashboard.modelTrainingTitle")}
              </Button>
            </CardContent>
          </Card>
        </Grid>
      </Grid>
    </Container>
  );
}
