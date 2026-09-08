import { alpha, createTheme } from "@mui/material/styles";

/**
 * Futuristic-medical dark theme — deep navy "command-center" background with
 * a cyan primary accent (clinical/tech) and a restrained violet secondary.
 * Semantic status colors (success/warning/error) stay close to their
 * conventional hues on purpose: they carry real meaning here (failed
 * training runs, anatomical violations, high-confidence errors) and must
 * never be sacrificed for aesthetics.
 */
export const theme = createTheme({
  palette: {
    mode: "dark",
    primary: { main: "#22d3ee", light: "#67e8f9", dark: "#0891b2", contrastText: "#04121a" },
    secondary: { main: "#818cf8", light: "#a5b4fc", dark: "#5b52d6", contrastText: "#0a0e1a" },
    success: { main: "#22c55e", light: "#4ade80", dark: "#15803d", contrastText: "#04140a" },
    warning: { main: "#f59e0b", light: "#fbbf24", dark: "#b45309", contrastText: "#1a1102" },
    error: { main: "#ef4444", light: "#f87171", dark: "#b91c1c" },
    background: { default: "#0a0e1a", paper: "#101a2c" },
    divider: alpha("#22d3ee", 0.12),
    text: { primary: "#e6edf7", secondary: "#93a4bf" },
  },
  shape: { borderRadius: 10 },
  typography: {
    fontFamily: '"Inter", "Roboto", "Helvetica", "Arial", sans-serif',
    h3: { fontWeight: 700, letterSpacing: -0.5 },
    h4: { fontWeight: 700, letterSpacing: -0.25 },
    h5: { fontWeight: 700 },
    h6: { fontWeight: 600 },
    subtitle1: { fontWeight: 600 },
    subtitle2: { fontWeight: 600, color: "#93a4bf" },
    button: { fontWeight: 600, textTransform: "none" },
  },
  components: {
    MuiCssBaseline: {
      styleOverrides: {
        body: {
          backgroundColor: "#0a0e1a",
          backgroundImage:
            "radial-gradient(circle at 12% -10%, rgba(34,211,238,0.09), transparent 40%), " +
            "radial-gradient(circle at 88% 10%, rgba(129,140,248,0.08), transparent 40%)",
          backgroundAttachment: "fixed",
          minHeight: "100vh",
        },
        "::selection": { backgroundColor: alpha("#22d3ee", 0.35) },
      },
    },
    MuiAppBar: {
      styleOverrides: {
        root: {
          backgroundColor: alpha("#0f1729", 0.78),
          backdropFilter: "blur(12px)",
          borderBottom: `1px solid ${alpha("#22d3ee", 0.14)}`,
          boxShadow: "none",
        },
      },
    },
    MuiPaper: {
      styleOverrides: {
        root: { backgroundImage: "none" },
      },
    },
    MuiCard: {
      styleOverrides: {
        root: {
          backgroundColor: alpha("#101a2c", 0.72),
          border: `1px solid ${alpha("#22d3ee", 0.12)}`,
          backdropFilter: "blur(6px)",
          transition: "border-color 200ms ease, box-shadow 200ms ease",
        },
      },
    },
    MuiButton: {
      styleOverrides: {
        root: { borderRadius: 8, fontWeight: 600 },
        containedPrimary: {
          backgroundImage: "linear-gradient(135deg, #22d3ee, #0891b2)",
          color: "#04121a",
          boxShadow: "0 0 0 rgba(34,211,238,0)",
          transition: "box-shadow 200ms ease, transform 150ms ease",
          "&:hover": {
            boxShadow: "0 0 18px rgba(34,211,238,0.45)",
            backgroundImage: "linear-gradient(135deg, #22d3ee, #0891b2)",
          },
        },
        outlined: {
          borderColor: alpha("#22d3ee", 0.4),
          "&:hover": { borderColor: "#22d3ee", backgroundColor: alpha("#22d3ee", 0.06) },
        },
      },
    },
    MuiChip: {
      styleOverrides: {
        root: { borderRadius: 6, fontWeight: 600 },
      },
    },
    MuiTabs: {
      styleOverrides: {
        indicator: { height: 3, borderRadius: 3, backgroundColor: "#22d3ee" },
      },
    },
    MuiTab: {
      styleOverrides: {
        root: {
          textTransform: "none",
          fontWeight: 600,
          color: "#93a4bf",
          transition: "color 200ms ease",
          "&.Mui-selected": { color: "#22d3ee" },
        },
      },
    },
    MuiTableCell: {
      styleOverrides: {
        root: { borderColor: alpha("#22d3ee", 0.08) },
        head: {
          fontWeight: 700,
          color: "#93a4bf",
          backgroundColor: alpha("#0f1729", 0.55),
          textTransform: "uppercase",
          fontSize: "0.72rem",
          letterSpacing: 0.4,
        },
      },
    },
    MuiListItemButton: {
      styleOverrides: {
        root: {
          borderRadius: 8,
          transition: "background-color 150ms ease, border-color 150ms ease",
          borderLeft: "3px solid transparent",
          "&.Mui-selected": {
            backgroundColor: alpha("#22d3ee", 0.12),
            borderLeft: "3px solid #22d3ee",
          },
          "&.Mui-selected:hover": { backgroundColor: alpha("#22d3ee", 0.16) },
          "&:hover": { backgroundColor: alpha("#22d3ee", 0.06) },
        },
      },
    },
    MuiOutlinedInput: {
      styleOverrides: {
        root: {
          transition: "box-shadow 150ms ease",
          "&.Mui-focused .MuiOutlinedInput-notchedOutline": { borderColor: "#22d3ee" },
        },
      },
    },
    MuiInputLabel: {
      styleOverrides: {
        root: { "&.Mui-focused": { color: "#22d3ee" } },
      },
    },
    MuiAlert: {
      styleOverrides: {
        root: { alignItems: "center", borderRadius: 8 },
      },
    },
  },
});

/** Shared recharts colors so every chart in the app reads from one palette. */
export const chartColors = {
  primary: "#22d3ee",
  secondary: "#818cf8",
  tertiary: "#f59e0b",
  success: "#34d399",
  error: "#f87171",
  info: "#38bdf8",
  grid: "rgba(148, 163, 184, 0.15)",
  axis: "#93a4bf",
  reference: "#64748b",
  tooltipBg: "#101a2c",
  tooltipBorder: "rgba(34, 211, 238, 0.25)",
};

export const categoricalChartColors = [
  chartColors.primary,
  chartColors.secondary,
  chartColors.tertiary,
  chartColors.success,
  chartColors.error,
  chartColors.info,
];

export const chartAxisTick = { fill: chartColors.axis, fontSize: 12 };

export const chartTooltipStyle = {
  contentStyle: {
    backgroundColor: chartColors.tooltipBg,
    border: `1px solid ${chartColors.tooltipBorder}`,
    borderRadius: 8,
  },
  labelStyle: { color: "#e6edf7" },
  itemStyle: { color: "#e6edf7" },
};

export const chartLegendStyle = { wrapperStyle: { color: chartColors.axis, fontSize: 13 } };

/** Confusion-matrix heat-map cell color, scaled by value against the matrix max. */
export function heatCellColor(value: number, max: number): string {
  const alphaValue = max > 0 ? Math.min(value / max, 1) : 0;
  return alpha(chartColors.primary, Math.max(alphaValue, 0.04));
}
