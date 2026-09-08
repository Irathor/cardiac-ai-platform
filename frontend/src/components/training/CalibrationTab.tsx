import { Box, Chip, Stack, Typography } from "@mui/material";
import { CartesianGrid, Legend, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

import type { ClassificationValidationReport } from "../../api/training";
import { chartAxisTick, chartColors, chartLegendStyle, chartTooltipStyle } from "../../theme";
import { fmtNumber, fmtPercent } from "./format";

interface CalibrationTabProps {
  report: ClassificationValidationReport;
}

export function CalibrationTab({ report }: CalibrationTabProps) {
  const { calibration, selective_prediction } = report;
  const reliabilityData = calibration.top1_reliability_diagram.bin_confidence.map((confidence, i) => ({
    confidence,
    accuracy: calibration.top1_reliability_diagram.bin_accuracy[i],
    count: calibration.top1_reliability_diagram.bin_count[i],
  }));

  return (
    <Box>
      <Stack direction="row" spacing={1} sx={{ mb: 3 }} flexWrap="wrap">
        <Chip label={`Multiclass Brier score: ${fmtNumber(calibration.multiclass_brier_score)}`} />
        <Chip label={`Log loss: ${fmtNumber(calibration.log_loss)}`} />
        <Chip label={`ECE: ${fmtNumber(calibration.top1_reliability_diagram.ece)}`} />
        <Chip label={`MCE: ${fmtNumber(calibration.top1_reliability_diagram.mce)}`} />
        <Chip label={`Calibration slope: ${fmtNumber(calibration.top1_reliability_diagram.calibration_slope)}`} />
        <Chip label={`Calibration intercept: ${fmtNumber(calibration.top1_reliability_diagram.calibration_intercept)}`} />
        <Chip label={`High-confidence (>90%) error rate: ${fmtPercent(calibration.high_confidence_error_rate_90)}`} />
      </Stack>

      <Typography variant="h6" gutterBottom>
        Reliability diagram
      </Typography>
      <Box sx={{ height: 300, mb: 4 }}>
        <ResponsiveContainer width="100%" height="100%">
          <LineChart>
            <CartesianGrid strokeDasharray="3 3" stroke={chartColors.grid} />
            <XAxis
              dataKey="confidence"
              type="number"
              domain={[0, 1]}
              allowDuplicatedCategory={false}
              tick={chartAxisTick}
              stroke={chartColors.axis}
            />
            <YAxis dataKey="accuracy" type="number" domain={[0, 1]} tick={chartAxisTick} stroke={chartColors.axis} />
            <Tooltip {...chartTooltipStyle} />
            <Legend {...chartLegendStyle} />
            <Line
              data={[{ confidence: 0, accuracy: 0 }, { confidence: 1, accuracy: 1 }]}
              dataKey="accuracy"
              stroke={chartColors.reference}
              strokeDasharray="4 4"
              dot={false}
              name="Perfect calibration"
              isAnimationActive={false}
            />
            <Line
              data={reliabilityData}
              dataKey="accuracy"
              stroke={chartColors.primary}
              name="Observed"
              isAnimationActive={false}
            />
          </LineChart>
        </ResponsiveContainer>
      </Box>

      <Typography variant="h6" gutterBottom>
        Risk-coverage curve
      </Typography>
      <Box sx={{ height: 300, mb: 2 }}>
        <ResponsiveContainer width="100%" height="100%">
          <LineChart data={selective_prediction.risk_coverage_curve}>
            <CartesianGrid strokeDasharray="3 3" stroke={chartColors.grid} />
            <XAxis dataKey="coverage" type="number" domain={[0, 1]} tick={chartAxisTick} stroke={chartColors.axis} />
            <YAxis domain={[0, 1]} tick={chartAxisTick} stroke={chartColors.axis} />
            <Tooltip {...chartTooltipStyle} />
            <Legend {...chartLegendStyle} />
            <Line
              type="monotone"
              dataKey="accuracy"
              stroke={chartColors.primary}
              dot={false}
              name="Accuracy"
              isAnimationActive={false}
            />
            <Line
              type="monotone"
              dataKey="macro_f1"
              stroke={chartColors.secondary}
              dot={false}
              name="Macro F1"
              isAnimationActive={false}
            />
          </LineChart>
        </ResponsiveContainer>
      </Box>
      <Stack direction="row" spacing={1} flexWrap="wrap">
        <Chip label={`Selective accuracy (reject 5%): ${fmtPercent(selective_prediction.selective_accuracy_reject_5pct)}`} />
        <Chip label={`Selective accuracy (reject 10%): ${fmtPercent(selective_prediction.selective_accuracy_reject_10pct)}`} />
        <Chip label={`Selective accuracy (reject 20%): ${fmtPercent(selective_prediction.selective_accuracy_reject_20pct)}`} />
      </Stack>
    </Box>
  );
}
