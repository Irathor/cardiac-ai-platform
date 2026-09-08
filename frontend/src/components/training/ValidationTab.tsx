import {
  Box,
  Chip,
  Stack,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  Typography,
} from "@mui/material";

import type { Cnn3dMetrics, UnetMetrics } from "../../api/training";
import { fmtCi, fmtNumber, fmtPercent, NOT_APPLICABLE } from "./format";

interface ValidationTabProps {
  unetMetrics?: UnetMetrics;
  cnn3dMetrics?: Cnn3dMetrics;
}

const NOT_IMPLEMENTED_NOTE =
  "Not implemented in this version (documented as out of scope rather than simulated): " +
  "synthetic robustness perturbation tests (noise, rotation, contrast, missing slices, corrupted files); " +
  "out-of-distribution detection; subgroup analysis beyond what's trivially available above; " +
  "latency/throughput/hardware benchmarks.";

function CnnValidation({ cnn3dMetrics }: { cnn3dMetrics: Cnn3dMetrics }) {
  const cv = cnn3dMetrics.cross_validation;
  const bootstrapCi = cnn3dMetrics.external_test.validation.bootstrap_ci_95;

  return (
    <Box>
      <Typography variant="h6" gutterBottom>
        Per-fold accuracy
      </Typography>
      <TableContainer sx={{ mb: 2, maxWidth: 480 }}>
        <Table size="small">
          <TableHead>
            <TableRow>
              <TableCell>Fold</TableCell>
              <TableCell align="right">Test patients</TableCell>
              <TableCell align="right">Accuracy</TableCell>
            </TableRow>
          </TableHead>
          <TableBody>
            {cv.folds.map((fold) => (
              <TableRow key={fold.fold}>
                <TableCell>{fold.fold}</TableCell>
                <TableCell align="right">{fold.test_patients.length}</TableCell>
                <TableCell align="right">{fmtPercent(fold.accuracy)}</TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </TableContainer>

      <Stack direction="row" spacing={1} sx={{ mb: 3 }} flexWrap="wrap">
        <Chip label={`Mean: ${fmtPercent(cv.mean_accuracy)}`} />
        <Chip label={`Std: ${fmtNumber(cv.std_accuracy)}`} />
        <Chip label={`Median: ${fmtPercent(cv.median_accuracy)}`} />
        <Chip label={`IQR: ${fmtNumber(cv.iqr_accuracy)}`} />
        <Chip label={`Min: ${fmtPercent(cv.min_accuracy)}`} />
        <Chip label={`Max: ${fmtPercent(cv.max_accuracy)}`} />
      </Stack>

      <Typography variant="h6" gutterBottom>
        Bootstrap 95% CI (external test)
      </Typography>
      <Stack direction="row" spacing={1} sx={{ mb: 3 }} flexWrap="wrap">
        <Chip label={`Accuracy: ${fmtCi(bootstrapCi.accuracy)}`} />
        <Chip label={`Balanced accuracy: ${fmtCi(bootstrapCi.balanced_accuracy)}`} />
        <Chip label={`Macro F1: ${fmtCi(bootstrapCi.macro_f1)}`} />
      </Stack>

      <Typography variant="h6" gutterBottom>
        Out-of-fold vs. external test
      </Typography>
      <Stack direction="row" spacing={1} flexWrap="wrap">
        <Chip label={`Out-of-fold accuracy: ${fmtPercent(cv.out_of_fold_validation.accuracy)}`} />
        <Chip label={`External test accuracy: ${fmtPercent(cnn3dMetrics.external_test.accuracy)}`} />
      </Stack>
    </Box>
  );
}

function UnetValidation({ unetMetrics }: { unetMetrics: UnetMetrics }) {
  const ci = unetMetrics.detailed_validation.bootstrap_ci_95_dice;
  return (
    <Box>
      <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
        Per-fold cross-validation: {NOT_APPLICABLE} (U-Net uses a single train/val/test split).
      </Typography>
      <Typography variant="h6" gutterBottom>
        Bootstrap 95% CI (Dice, by structure/phase)
      </Typography>
      <TableContainer sx={{ maxWidth: 480 }}>
        <Table size="small">
          <TableHead>
            <TableRow>
              <TableCell>Structure/phase</TableCell>
              <TableCell align="right">95% CI</TableCell>
            </TableRow>
          </TableHead>
          <TableBody>
            {Object.entries(ci).map(([key, interval]) => (
              <TableRow key={key}>
                <TableCell>{key}</TableCell>
                <TableCell align="right">{fmtCi(interval)}</TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </TableContainer>
    </Box>
  );
}

export function ValidationTab({ unetMetrics, cnn3dMetrics }: ValidationTabProps) {
  return (
    <Box>
      {cnn3dMetrics && <CnnValidation cnn3dMetrics={cnn3dMetrics} />}
      {unetMetrics && <UnetValidation unetMetrics={unetMetrics} />}
      {!cnn3dMetrics && !unetMetrics && (
        <Typography color="text.secondary" sx={{ mb: 3 }}>
          No cross-validation data for this model type.
        </Typography>
      )}
      <Typography variant="body2" color="text.secondary" sx={{ mt: 4 }}>
        {NOT_IMPLEMENTED_NOTE}
      </Typography>
    </Box>
  );
}
