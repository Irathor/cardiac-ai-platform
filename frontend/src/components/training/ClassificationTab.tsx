import {
  Box,
  Chip,
  MenuItem,
  Select,
  Stack,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  Typography,
} from "@mui/material";
import { useMemo, useState } from "react";
import { CartesianGrid, Legend, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

import type { Cnn3dMetrics, ClassificationValidationReport, NearestCentroidMetrics } from "../../api/training";
import {
  categoricalChartColors,
  chartAxisTick,
  chartColors,
  chartLegendStyle,
  chartTooltipStyle,
  heatCellColor,
} from "../../theme";
import { fmtNumber, fmtPercent } from "./format";

interface ClassificationTabProps {
  simpleMetrics?: NearestCentroidMetrics;
  cnn3dMetrics?: Cnn3dMetrics;
}

type Normalization = "raw" | "true" | "predicted";

const CURVE_COLORS = categoricalChartColors;

function matrixFor(report: ClassificationValidationReport, normalization: Normalization): number[][] {
  if (normalization === "true") return report.confusion_matrix_normalized_true;
  if (normalization === "predicted") return report.confusion_matrix_normalized_predicted;
  return report.confusion_matrix;
}

function SimpleClassificationView({ metrics }: { metrics: NearestCentroidMetrics }) {
  const accuracy = metrics.case_count > 0 ? metrics.correct_count / metrics.case_count : null;
  return (
    <Box>
      <Typography variant="body1" gutterBottom>
        {metrics.correct_count} / {metrics.case_count} cases correct ({fmtPercent(accuracy)})
      </Typography>
      <TableContainer sx={{ maxWidth: 480 }}>
        <Table size="small">
          <TableHead>
            <TableRow>
              <TableCell>Class</TableCell>
              <TableCell align="right">Accuracy</TableCell>
            </TableRow>
          </TableHead>
          <TableBody>
            {Object.entries(metrics.per_class_accuracy).map(([cls, acc]) => (
              <TableRow key={cls}>
                <TableCell>{cls}</TableCell>
                <TableCell align="right">{fmtPercent(acc)}</TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </TableContainer>
    </Box>
  );
}

function FullClassificationView({ cnn3dMetrics }: { cnn3dMetrics: Cnn3dMetrics }) {
  const [source, setSource] = useState<"external_test" | "out_of_fold">("external_test");
  const [normalization, setNormalization] = useState<Normalization>("true");

  const report: ClassificationValidationReport =
    source === "external_test" ? cnn3dMetrics.external_test.validation : cnn3dMetrics.cross_validation.out_of_fold_validation;

  const matrix = matrixFor(report, normalization);
  const maxCell = useMemo(() => Math.max(1e-9, ...matrix.flat()), [matrix]);

  const rocData = report.labels.map((label, i) => ({
    label,
    color: CURVE_COLORS[i % CURVE_COLORS.length],
    curve: report.roc.per_class[label],
  }));
  const prData = report.labels.map((label, i) => ({
    label,
    color: CURVE_COLORS[i % CURVE_COLORS.length],
    curve: report.precision_recall.per_class[label],
  }));

  return (
    <Box>
      <Stack direction="row" spacing={2} sx={{ mb: 2 }}>
        <Select size="small" value={source} onChange={(e) => setSource(e.target.value as typeof source)}>
          <MenuItem value="external_test">External test</MenuItem>
          <MenuItem value="out_of_fold">Cross-validation (out-of-fold)</MenuItem>
        </Select>
      </Stack>

      <Stack direction="row" spacing={1} sx={{ mb: 2 }} flexWrap="wrap">
        <Chip label={`Accuracy: ${fmtPercent(report.accuracy)}`} />
        <Chip label={`Balanced accuracy: ${fmtPercent(report.balanced_accuracy)}`} />
        <Chip label={`Macro F1: ${fmtNumber(report.macro.f1)}`} />
        <Chip label={`Weighted F1: ${fmtNumber(report.weighted.f1)}`} />
        <Chip label={`Micro F1: ${fmtNumber(report.micro.f1)}`} />
        <Chip label={`MCC: ${fmtNumber(report.matthews_correlation_coefficient)}`} />
        <Chip label={`Cohen's Kappa: ${fmtNumber(report.cohens_kappa)}`} />
        <Chip label={`Top-2 accuracy: ${fmtPercent(report.top_2_accuracy)}`} />
      </Stack>

      <Typography variant="h6" gutterBottom>
        Confusion matrix
      </Typography>
      <Select
        size="small"
        value={normalization}
        onChange={(e) => setNormalization(e.target.value as Normalization)}
        sx={{ mb: 1 }}
      >
        <MenuItem value="raw">Raw counts</MenuItem>
        <MenuItem value="true">Normalized by true class</MenuItem>
        <MenuItem value="predicted">Normalized by predicted class</MenuItem>
      </Select>
      <TableContainer sx={{ mb: 4, maxWidth: 720 }}>
        <Table size="small">
          <TableHead>
            <TableRow>
              <TableCell>True \ Predicted</TableCell>
              {report.labels.map((label) => (
                <TableCell key={label} align="right">
                  {label}
                </TableCell>
              ))}
            </TableRow>
          </TableHead>
          <TableBody>
            {report.labels.map((rowLabel, rowIdx) => (
              <TableRow key={rowLabel}>
                <TableCell>{rowLabel}</TableCell>
                {report.labels.map((_, colIdx) => {
                  const value = matrix[rowIdx][colIdx];
                  return (
                    <TableCell
                      key={colIdx}
                      align="right"
                      sx={{ backgroundColor: heatCellColor(value, maxCell) }}
                    >
                      {normalization === "raw" ? value : fmtPercent(value)}
                    </TableCell>
                  );
                })}
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </TableContainer>

      <Typography variant="h6" gutterBottom>
        Per-class metrics
      </Typography>
      <TableContainer sx={{ mb: 4 }}>
        <Table size="small">
          <TableHead>
            <TableRow>
              <TableCell>Class</TableCell>
              <TableCell align="right">Precision</TableCell>
              <TableCell align="right">Recall</TableCell>
              <TableCell align="right">Specificity</TableCell>
              <TableCell align="right">NPV</TableCell>
              <TableCell align="right">F1</TableCell>
            </TableRow>
          </TableHead>
          <TableBody>
            {report.labels.map((label) => {
              const row = report.per_class[label];
              return (
                <TableRow key={label}>
                  <TableCell>{label}</TableCell>
                  <TableCell align="right">{fmtNumber(row.precision)}</TableCell>
                  <TableCell align="right">{fmtNumber(row.recall)}</TableCell>
                  <TableCell align="right">{fmtNumber(row.specificity)}</TableCell>
                  <TableCell align="right">{fmtNumber(row.npv)}</TableCell>
                  <TableCell align="right">{fmtNumber(row.f1)}</TableCell>
                </TableRow>
              );
            })}
          </TableBody>
        </Table>
      </TableContainer>

      <Typography variant="h6" gutterBottom>
        ROC curves (AUC in legend)
      </Typography>
      <Box sx={{ height: 320, mb: 4 }}>
        <ResponsiveContainer width="100%" height="100%">
          <LineChart>
            <CartesianGrid strokeDasharray="3 3" stroke={chartColors.grid} />
            <XAxis
              dataKey="fpr"
              type="number"
              domain={[0, 1]}
              allowDuplicatedCategory={false}
              tick={chartAxisTick}
              stroke={chartColors.axis}
            />
            <YAxis dataKey="tpr" type="number" domain={[0, 1]} tick={chartAxisTick} stroke={chartColors.axis} />
            <Tooltip {...chartTooltipStyle} />
            <Legend {...chartLegendStyle} />
            <Line
              data={[{ fpr: 0, tpr: 0 }, { fpr: 1, tpr: 1 }]}
              dataKey="tpr"
              stroke={chartColors.reference}
              strokeDasharray="4 4"
              dot={false}
              name="Reference"
              isAnimationActive={false}
            />
            {rocData.map(({ label, color, curve }) => (
              <Line
                key={label}
                data={curve.fpr.map((f, i) => ({ fpr: f, tpr: curve.tpr[i] }))}
                dataKey="tpr"
                stroke={color}
                dot={false}
                name={`${label} (AUC ${fmtNumber(curve.auc, 2)})`}
                isAnimationActive={false}
              />
            ))}
          </LineChart>
        </ResponsiveContainer>
      </Box>

      <Typography variant="h6" gutterBottom>
        Precision-recall curves
      </Typography>
      <Box sx={{ height: 320 }}>
        <ResponsiveContainer width="100%" height="100%">
          <LineChart>
            <CartesianGrid strokeDasharray="3 3" stroke={chartColors.grid} />
            <XAxis
              dataKey="recall"
              type="number"
              domain={[0, 1]}
              allowDuplicatedCategory={false}
              tick={chartAxisTick}
              stroke={chartColors.axis}
            />
            <YAxis dataKey="precision" type="number" domain={[0, 1]} tick={chartAxisTick} stroke={chartColors.axis} />
            <Tooltip {...chartTooltipStyle} />
            <Legend {...chartLegendStyle} />
            {prData.map(({ label, color, curve }) => (
              <Line
                key={label}
                data={curve.recall.map((r, i) => ({ recall: r, precision: curve.precision[i] }))}
                dataKey="precision"
                stroke={color}
                dot={false}
                name={`${label} (AP ${fmtNumber(curve.average_precision, 2)})`}
                isAnimationActive={false}
              />
            ))}
          </LineChart>
        </ResponsiveContainer>
      </Box>
    </Box>
  );
}

export function ClassificationTab({ simpleMetrics, cnn3dMetrics }: ClassificationTabProps) {
  if (simpleMetrics) return <SimpleClassificationView metrics={simpleMetrics} />;
  if (cnn3dMetrics) return <FullClassificationView cnn3dMetrics={cnn3dMetrics} />;
  return <Typography color="text.secondary">No classification data available.</Typography>;
}
