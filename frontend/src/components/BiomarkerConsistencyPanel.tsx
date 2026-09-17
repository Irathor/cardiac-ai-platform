import {
  Alert,
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

import type { BiomarkerConsistency } from "../api/analysis";

export interface BiomarkerConsistencyPanelProps {
  consistency: BiomarkerConsistency | null;
  error: string | null;
}

// Reference text fixed in EPIC-12 — kept verbatim so the caveat reads the
// same wherever this signal is shown.
const CONSISTENCY_NOTE =
  "Señal de consistencia indirecta entre los biomarcadores derivados por auto-segmentación " +
  "U-Net y los prototipos de la clase predicha por CNN3D — no es una atribución exacta del " +
  "modelo, es una comparación posterior con un clasificador distinto (nearest-centroid).";

/**
 * Table for EPIC-12's biomarker-consistency signal — same visual pattern as
 * `ClassificationTab`'s tables (plain MUI `Table`, no new styling). Mounted
 * inside the existing "AI analysis" card, below `feature_attributions` —
 * it's the same unit of information, not a separate hero surface.
 */
export function BiomarkerConsistencyPanel({ consistency, error }: BiomarkerConsistencyPanelProps) {
  if (!consistency && !error) return null;

  return (
    <Box sx={{ mt: 2 }}>
      <Typography variant="subtitle2" gutterBottom>
        Biomarker consistency
      </Typography>

      {error && <Alert severity="warning">{error}</Alert>}

      {consistency && (
        <Stack spacing={1.5}>
          <Typography variant="caption" color="text.secondary">
            {CONSISTENCY_NOTE}
          </Typography>
          <Typography variant="body2" color="text.secondary">
            Reference: {consistency.reference_source}
          </Typography>

          <TableContainer>
            <Table size="small" aria-label="Biomarker consistency per feature">
              <TableHead>
                <TableRow>
                  <TableCell>Feature</TableCell>
                  <TableCell align="right">Derived value</TableCell>
                  <TableCell align="right">Expected for {consistency.predicted_class}</TableCell>
                  <TableCell align="right">Scaled deviation</TableCell>
                  <TableCell align="center">Consistent</TableCell>
                </TableRow>
              </TableHead>
              <TableBody>
                {consistency.per_feature.map((row) => (
                  <TableRow key={row.feature}>
                    <TableCell>{row.feature}</TableCell>
                    <TableCell align="right">{row.derived_value.toFixed(2)}</TableCell>
                    <TableCell align="right">{row.expected_value_for_predicted_class.toFixed(2)}</TableCell>
                    <TableCell align="right">{row.scaled_deviation.toFixed(2)}</TableCell>
                    <TableCell align="center">
                      {/* Not red: a deviation is a signal, not proof the model is wrong. */}
                      <Chip
                        label={row.consistent ? "Consistent" : "Deviates"}
                        size="small"
                        color={row.consistent ? "success" : "warning"}
                      />
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </TableContainer>

          <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap>
            {Object.entries(consistency.distance_to_each_class).map(([cls, distance]) => (
              <Chip
                key={cls}
                variant={cls === consistency.predicted_class ? "filled" : "outlined"}
                color={cls === consistency.predicted_class ? "primary" : "default"}
                size="small"
                label={`${cls}: ${distance.toFixed(2)}`}
              />
            ))}
          </Stack>
        </Stack>
      )}
    </Box>
  );
}
