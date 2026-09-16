import { alpha, createTheme } from "@mui/material/styles";
import type { CSSObject } from "@mui/material/styles";

/**
 * "AI-Ops cardiac" dark theme — see docs/epics/EPIC-10-rediseno-visual-frontend.md
 * for the full design-token rationale (two-pass frontend-design process,
 * critique notes, before/after).
 *
 * Two structural ideas carry the whole redesign instead of one repeated
 * card style everywhere:
 *
 * 1. Domain-coded accent — cyan always means "looking at a patient"
 *    (imaging/clinical surfaces: the viewer, biomarkers, segmentation),
 *    violet always means "looking at the model" (MLOps surfaces: training
 *    runs, model versions, calibration). The color carries information,
 *    it isn't picked per-component for variety.
 * 2. Two elevation tiers, used deliberately — "quiet" (flat, hairline
 *    border, no glow: tables, lists, secondary panels — the majority of
 *    the UI) and "hero" (raised surface + directional glow, reserved for
 *    the one focal element per screen: the volume viewer, the in-flight
 *    training run, the leading metric). Never both tiers look the same,
 *    and never more than one hero per screen.
 */

export const tokens = {
  bgVoid: "#060910",
  surface: "#0d1524",
  surfaceRaised: "#131f34",
  cyan: "#2dd9e8",
  cyanDark: "#0ba9ba",
  violet: "#8b7cf6",
  violetDark: "#5d4fd1",
  line: "rgba(148, 163, 184, 0.09)",
  textPrimary: "#e7edf6",
  textSecondary: "#8fa0bd",
};

export type Accent = "cyan" | "violet";

const accentColor: Record<Accent, string> = { cyan: tokens.cyan, violet: tokens.violet };

/** Flat, quiet tier — the default for tables, lists, secondary panels. No glow, no lift. */
export function quietSurface(): CSSObject {
  return {
    backgroundColor: tokens.surface,
    border: `1px solid ${tokens.line}`,
    borderRadius: "10px",
    boxShadow: "none",
  };
}

/** Hero tier — reserved for the single focal element on a screen. Raised surface + directional glow. */
export function heroSurface(accent: Accent = "cyan"): CSSObject {
  const c = accentColor[accent];
  return {
    backgroundColor: tokens.surfaceRaised,
    border: `1px solid ${alpha(c, 0.4)}`,
    borderRadius: "16px",
    boxShadow: `0 0 0 1px ${alpha(c, 0.06)}, 0 24px 64px -28px ${alpha(c, 0.55)}`,
  };
}

export const theme = createTheme({
  palette: {
    mode: "dark",
    primary: { main: tokens.cyan, light: "#7de9f0", dark: tokens.cyanDark, contrastText: "#03141a" },
    secondary: { main: tokens.violet, light: "#ab9ffb", dark: tokens.violetDark, contrastText: "#0b0a1f" },
    success: { main: "#22c55e", light: "#4ade80", dark: "#15803d", contrastText: "#04140a" },
    warning: { main: "#f59e0b", light: "#fbbf24", dark: "#b45309", contrastText: "#1a1102" },
    error: { main: "#ef4444", light: "#f87171", dark: "#b91c1c" },
    background: { default: tokens.bgVoid, paper: tokens.surface },
    divider: tokens.line,
    text: { primary: tokens.textPrimary, secondary: tokens.textSecondary },
  },
  shape: { borderRadius: 10 },
  typography: {
    fontFamily: '"Inter", "Roboto", "Helvetica", "Arial", sans-serif',
    // Space Grotesk is reserved for page titles and hero numerals only — it
    // never runs into body copy or small labels, so it reads as a display
    // role rather than a themed re-skin of every string in the app.
    h3: { fontFamily: '"Space Grotesk", "Inter", sans-serif', fontWeight: 600, letterSpacing: -0.3 },
    h4: { fontFamily: '"Space Grotesk", "Inter", sans-serif', fontWeight: 600, letterSpacing: -0.2 },
    h5: { fontWeight: 700 },
    h6: { fontWeight: 600 },
    subtitle1: { fontWeight: 600 },
    subtitle2: { fontWeight: 600, color: tokens.textSecondary },
    button: { fontWeight: 600, textTransform: "none" },
  },
  components: {
    MuiCssBaseline: {
      styleOverrides: {
        body: {
          backgroundColor: tokens.bgVoid,
          backgroundImage: `radial-gradient(circle at 15% -12%, ${alpha(tokens.cyan, 0.1)}, transparent 42%)`,
          backgroundAttachment: "fixed",
          minHeight: "100vh",
        },
        "::selection": { backgroundColor: alpha(tokens.cyan, 0.32) },
        "*:focus-visible": {
          outline: `2px solid ${tokens.cyan}`,
          outlineOffset: "2px",
        },
      },
    },
    MuiAppBar: {
      styleOverrides: {
        root: {
          backgroundColor: alpha("#0a1220", 0.82),
          backdropFilter: "blur(14px)",
          borderBottom: `1px solid ${tokens.line}`,
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
        // Cards default to the quiet tier; call sites opt into the hero
        // tier explicitly via `sx={heroSurface(...)}` when they hold the
        // one focal element on their screen.
        root: { ...quietSurface(), transition: "border-color 200ms ease" },
      },
    },
    MuiButton: {
      styleOverrides: {
        root: { borderRadius: 8, fontWeight: 600 },
        containedPrimary: {
          backgroundImage: `linear-gradient(135deg, ${tokens.cyan}, ${tokens.cyanDark})`,
          color: "#03141a",
          transition: "box-shadow 200ms ease",
          "&:hover": {
            boxShadow: `0 0 20px ${alpha(tokens.cyan, 0.4)}`,
            backgroundImage: `linear-gradient(135deg, ${tokens.cyan}, ${tokens.cyanDark})`,
          },
        },
        containedSecondary: {
          backgroundImage: `linear-gradient(135deg, ${tokens.violet}, ${tokens.violetDark})`,
          transition: "box-shadow 200ms ease",
          "&:hover": { boxShadow: `0 0 20px ${alpha(tokens.violet, 0.4)}` },
        },
        outlined: {
          borderColor: alpha(tokens.cyan, 0.4),
          "&:hover": { borderColor: tokens.cyan, backgroundColor: alpha(tokens.cyan, 0.06) },
        },
        outlinedSecondary: {
          borderColor: alpha(tokens.violet, 0.4),
          "&:hover": { borderColor: tokens.violet, backgroundColor: alpha(tokens.violet, 0.08) },
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
        indicator: { height: 3, borderRadius: 3, backgroundColor: tokens.cyan },
      },
    },
    MuiTab: {
      styleOverrides: {
        root: {
          textTransform: "none",
          fontWeight: 600,
          color: tokens.textSecondary,
          transition: "color 200ms ease",
          "&.Mui-selected": { color: tokens.cyan },
        },
      },
    },
    MuiTableCell: {
      styleOverrides: {
        root: { borderColor: tokens.line },
        // Sentence case, not the tracked-out ALL-CAPS eyebrow — hierarchy
        // comes from weight and color, not shouting.
        head: {
          fontWeight: 700,
          color: tokens.textSecondary,
          backgroundColor: alpha("#0a1220", 0.5),
          fontSize: "0.78rem",
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
            backgroundColor: alpha(tokens.cyan, 0.12),
            borderLeft: `3px solid ${tokens.cyan}`,
          },
          "&.Mui-selected:hover": { backgroundColor: alpha(tokens.cyan, 0.16) },
          "&:hover": { backgroundColor: alpha(tokens.cyan, 0.06) },
        },
      },
    },
    MuiOutlinedInput: {
      styleOverrides: {
        root: {
          transition: "box-shadow 150ms ease",
          "&.Mui-focused .MuiOutlinedInput-notchedOutline": { borderColor: tokens.cyan },
        },
      },
    },
    MuiInputLabel: {
      styleOverrides: {
        root: { "&.Mui-focused": { color: tokens.cyan } },
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
  primary: tokens.cyan,
  secondary: tokens.violet,
  tertiary: "#f59e0b",
  success: "#34d399",
  error: "#f87171",
  info: "#38bdf8",
  grid: "rgba(148, 163, 184, 0.15)",
  axis: tokens.textSecondary,
  reference: "#64748b",
  tooltipBg: tokens.surfaceRaised,
  tooltipBorder: alpha(tokens.cyan, 0.3),
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
  labelStyle: { color: tokens.textPrimary },
  itemStyle: { color: tokens.textPrimary },
};

export const chartLegendStyle = { wrapperStyle: { color: chartColors.axis, fontSize: 13 } };

/** Confusion-matrix heat-map cell color, scaled by value against the matrix max. */
export function heatCellColor(value: number, max: number): string {
  const alphaValue = max > 0 ? Math.min(value / max, 1) : 0;
  return alpha(chartColors.primary, Math.max(alphaValue, 0.04));
}
