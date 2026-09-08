import {
  Box,
  MenuItem,
  Select,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  Typography,
} from "@mui/material";
import { useState } from "react";
import {
  Bar,
  BarChart,
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import type { AggregateStructureMetrics, DispersionSummary, UnetMetrics } from "../../api/training";
import { chartAxisTick, chartColors, chartLegendStyle, chartTooltipStyle } from "../../theme";
import { fmtNumber } from "./format";

interface SegmentationTabProps {
  metrics: UnetMetrics;
}

const BAR_METRICS: Array<{ key: keyof AggregateStructureMetrics; label: string }> = [
  { key: "dice", label: "Dice" },
  { key: "iou", label: "IoU" },
  { key: "hausdorff_distance_95_mm", label: "HD95 (mm)" },
  { key: "average_symmetric_surface_distance_mm", label: "ASSD (mm)" },
  { key: "relative_volume_error_percent", label: "Relative volume error (%)" },
];

const DISPERSION_FIELDS: Array<keyof DispersionSummary> = ["mean", "std", "median", "iqr", "min", "max", "undefined_count"];

function barChartData(metrics: UnetMetrics, metricKey: keyof AggregateStructureMetrics) {
  return metrics.detailed_validation.structures.map((structure) => {
    const row: Record<string, number | string> = { structure };
    for (const phase of metrics.detailed_validation.phases) {
      const summary = metrics.detailed_validation.aggregate[structure]?.[phase]?.[metricKey] as DispersionSummary | undefined;
      row[phase] = summary?.mean ?? 0;
    }
    return row;
  });
}

export function SegmentationTab({ metrics }: SegmentationTabProps) {
  const { structures, phases, aggregate, anatomical_violation_rate_percent } = metrics.detailed_validation;
  const [tableMetric, setTableMetric] = useState<keyof AggregateStructureMetrics>("dice");

  const lossHistoryData = metrics.history.map((h) => ({
    epoch: h.epoch,
    train_loss: h.train_loss,
    mean_dice_foreground: h.mean_dice_foreground,
  }));

  return (
    <Box>
      <Typography variant="h6" gutterBottom>
        Per-structure metrics by phase
      </Typography>
      {BAR_METRICS.map(({ key, label }) => (
        <Box key={key} sx={{ height: 260, mb: 3 }}>
          <Typography variant="subtitle2">{label}</Typography>
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={barChartData(metrics, key)}>
              <CartesianGrid strokeDasharray="3 3" stroke={chartColors.grid} />
              <XAxis dataKey="structure" tick={chartAxisTick} stroke={chartColors.axis} />
              <YAxis tick={chartAxisTick} stroke={chartColors.axis} />
              <Tooltip {...chartTooltipStyle} />
              <Legend {...chartLegendStyle} />
              {phases.map((phase, i) => (
                <Bar
                  key={phase}
                  dataKey={phase}
                  fill={i === 0 ? chartColors.primary : chartColors.secondary}
                  radius={[4, 4, 0, 0]}
                />
              ))}
            </BarChart>
          </ResponsiveContainer>
        </Box>
      ))}

      <Typography variant="h6" gutterBottom sx={{ mt: 4 }}>
        Dispersion summary
      </Typography>
      <Select
        size="small"
        value={tableMetric}
        onChange={(e) => setTableMetric(e.target.value as keyof AggregateStructureMetrics)}
        sx={{ mb: 1 }}
      >
        {BAR_METRICS.map(({ key, label }) => (
          <MenuItem key={key} value={key}>
            {label}
          </MenuItem>
        ))}
      </Select>
      <TableContainer sx={{ mb: 4 }}>
        <Table size="small">
          <TableHead>
            <TableRow>
              <TableCell>Structure</TableCell>
              <TableCell>Phase</TableCell>
              {DISPERSION_FIELDS.map((f) => (
                <TableCell key={f} align="right">
                  {f}
                </TableCell>
              ))}
            </TableRow>
          </TableHead>
          <TableBody>
            {structures.flatMap((structure) =>
              phases.map((phase) => {
                const summary = aggregate[structure]?.[phase]?.[tableMetric] as DispersionSummary | undefined;
                return (
                  <TableRow key={`${structure}-${phase}`}>
                    <TableCell>{structure}</TableCell>
                    <TableCell>{phase}</TableCell>
                    {DISPERSION_FIELDS.map((f) => (
                      <TableCell key={f} align="right">
                        {summary ? fmtNumber(summary[f], f === "undefined_count" ? 0 : 3) : "not available"}
                      </TableCell>
                    ))}
                  </TableRow>
                );
              }),
            )}
          </TableBody>
        </Table>
      </TableContainer>

      <Typography variant="h6" gutterBottom>
        Empty-mask and anatomical-violation rates
      </Typography>
      <TableContainer sx={{ mb: 4 }}>
        <Table size="small">
          <TableHead>
            <TableRow>
              <TableCell>Structure</TableCell>
              <TableCell>Phase</TableCell>
              <TableCell align="right">Empty prediction %</TableCell>
              <TableCell align="right">Empty target %</TableCell>
            </TableRow>
          </TableHead>
          <TableBody>
            {structures.flatMap((structure) =>
              phases.map((phase) => {
                const summary = aggregate[structure]?.[phase];
                return (
                  <TableRow key={`${structure}-${phase}-empty`}>
                    <TableCell>{structure}</TableCell>
                    <TableCell>{phase}</TableCell>
                    <TableCell align="right">{fmtNumber(summary?.empty_prediction_percent, 1)}</TableCell>
                    <TableCell align="right">{fmtNumber(summary?.empty_target_percent, 1)}</TableCell>
                  </TableRow>
                );
              }),
            )}
          </TableBody>
        </Table>
      </TableContainer>
      <Typography variant="body2" sx={{ mb: 4 }}>
        Anatomical violation rate —{" "}
        {phases.map((phase) => `${phase}: ${fmtNumber(anatomical_violation_rate_percent[phase], 1)}%`).join(", ")}
      </Typography>

      <Typography variant="h6" gutterBottom>
        Training curve
      </Typography>
      <Box sx={{ height: 300 }}>
        <ResponsiveContainer width="100%" height="100%">
          <LineChart data={lossHistoryData}>
            <CartesianGrid strokeDasharray="3 3" stroke={chartColors.grid} />
            <XAxis dataKey="epoch" tick={chartAxisTick} stroke={chartColors.axis} />
            <YAxis yAxisId="loss" tick={chartAxisTick} stroke={chartColors.axis} />
            <YAxis yAxisId="dice" orientation="right" domain={[0, 1]} tick={chartAxisTick} stroke={chartColors.axis} />
            <Tooltip {...chartTooltipStyle} />
            <Legend {...chartLegendStyle} />
            <Line
              yAxisId="loss"
              type="monotone"
              dataKey="train_loss"
              stroke={chartColors.secondary}
              dot={false}
              name="Train loss"
            />
            <Line
              yAxisId="dice"
              type="monotone"
              dataKey="mean_dice_foreground"
              stroke={chartColors.primary}
              dot={false}
              name="Val mean Dice"
            />
          </LineChart>
        </ResponsiveContainer>
      </Box>
    </Box>
  );
}
