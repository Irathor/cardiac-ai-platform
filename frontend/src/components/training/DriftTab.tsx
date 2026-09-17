import {
  Alert,
  Box,
  Chip,
  CircularProgress,
  Stack,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  Typography,
} from "@mui/material";

import type { BiomarkerDriftOut, DriftSeverity, ModelDriftReport } from "../../api/training";
import { fmtNumber } from "./format";

interface DriftTabProps {
  isLoading: boolean;
  /** Set when the query failed for a reason other than the 409 "not in
   * production" case (that case is filtered out before this tab is even
   * shown — see driftTabAvailable in ModelTrainingPage). */
  isError: boolean;
  errorMessage?: string;
  report?: ModelDriftReport;
}

const SEVERITY_COLOR: Record<DriftSeverity, "success" | "warning" | "error"> = {
  NONE: "success",
  MODERATE: "warning",
  SIGNIFICANT: "error",
};

const P_VALUE_THRESHOLD = 0.05;

function biomarkerRow(row: BiomarkerDriftOut) {
  if (row.skipped_reason) {
    return (
      <TableRow key={row.biomarker_name}>
        <TableCell component="th" scope="row">
          {row.biomarker_name}
        </TableCell>
        <TableCell colSpan={4}>
          <Typography variant="body2" color="text.secondary">
            Skipped: {row.skipped_reason}
          </Typography>
        </TableCell>
      </TableRow>
    );
  }

  return (
    <TableRow key={row.biomarker_name}>
      <TableCell component="th" scope="row">
        {row.biomarker_name}
      </TableCell>
      <TableCell align="right">{fmtNumber(row.ks_statistic)}</TableCell>
      <TableCell align="right">{fmtNumber(row.p_value)}</TableCell>
      <TableCell align="right">
        {row.base_sample_size} / {row.recent_sample_size}
      </TableCell>
      <TableCell align="right">
        <Chip
          size="small"
          label={row.drift_detected ? "Drift detected" : "No drift"}
          color={row.drift_detected ? "error" : "success"}
        />
      </TableCell>
    </TableRow>
  );
}

export function DriftTab({ isLoading, isError, errorMessage, report }: DriftTabProps) {
  if (isLoading) {
    return (
      <Stack direction="row" spacing={2} alignItems="center" sx={{ py: 4 }}>
        <CircularProgress size={20} />
        <Typography color="text.secondary">Computing drift against recent data…</Typography>
      </Stack>
    );
  }

  if (isError) {
    return (
      <Alert severity="info">
        {errorMessage ?? "Drift results are not available for this model version right now."}
      </Alert>
    );
  }

  if (!report) {
    return <Typography color="text.secondary">No drift data available.</Typography>;
  }

  return (
    <Box>
      <Typography variant="body2" color="text.secondary" sx={{ mb: 3 }}>
        Point-in-time check against recent predictions, evaluated at{" "}
        {new Date(report.evaluated_at).toLocaleString()} and cached for 5 minutes server-side — not a live
        monitor. Reopen this tab to recompute.
      </Typography>

      <Typography variant="h6" gutterBottom>
        Biomarker drift (Kolmogorov-Smirnov)
      </Typography>
      {report.biomarkers_skipped_reason ? (
        <Alert severity="info" sx={{ mb: 4 }}>
          {report.biomarkers_skipped_reason}
        </Alert>
      ) : (
        <TableContainer sx={{ mb: 4 }}>
          <Table size="small">
            <TableHead>
              <TableRow>
                <TableCell>Biomarker</TableCell>
                <TableCell align="right">KS statistic</TableCell>
                <TableCell align="right">p-value (threshold p &lt; {P_VALUE_THRESHOLD})</TableCell>
                <TableCell align="right">Sample size (base / recent)</TableCell>
                <TableCell align="right">Drift</TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {report.biomarkers.length === 0 ? (
                <TableRow>
                  <TableCell colSpan={5}>
                    <Typography variant="body2" color="text.secondary">
                      No biomarkers evaluated.
                    </Typography>
                  </TableCell>
                </TableRow>
              ) : (
                report.biomarkers.map(biomarkerRow)
              )}
            </TableBody>
          </Table>
        </TableContainer>
      )}

      <Typography variant="h6" gutterBottom>
        Prediction drift (PSI)
      </Typography>
      {report.prediction.skipped_reason ? (
        <Alert severity="info">{report.prediction.skipped_reason}</Alert>
      ) : (
        <Stack direction="row" spacing={1} flexWrap="wrap">
          <Chip label={`PSI: ${fmtNumber(report.prediction.psi)}`} />
          <Chip
            label={`Severity: ${report.prediction.severity}`}
            color={SEVERITY_COLOR[report.prediction.severity]}
          />
          <Chip
            label={`Drift detected: ${report.prediction.drift_detected ? "yes" : "no"}`}
            color={report.prediction.drift_detected ? "error" : "success"}
            variant="outlined"
          />
          <Chip
            label={`Sample size (base / recent): ${report.prediction.base_sample_size} / ${report.prediction.recent_sample_size}`}
          />
          <Chip variant="outlined" label="Bands: PSI < 0.1 none, 0.1–0.2 moderate, > 0.2 significant" />
        </Stack>
      )}
    </Box>
  );
}
