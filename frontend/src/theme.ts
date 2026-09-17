import { alpha, createTheme } from "@mui/material/styles";
import type { CSSObject } from "@mui/material/styles";

/**
 * "Bioluminescent Dark" theme — see docs/epics/EPIC-13-rediseno-bioluminescent-dark.md
 * for the full design-token rationale. Evolves the "AI-Ops" dark theme from
 * EPIC-10 onto the same token architecture (`quietSurface()`/`heroSurface()`,
 * domain-coded accents, two elevation tiers): only the palette and typefaces
 * change, not the structural ideas.
 *
 * Palette: a teal-black void (`bgVoid`) instead of a navy one, with a
 * bioluminescent-green accent for the clinical/patient domain and a violet
 * accent for the MLOps/model domain — same domain-coding role EPIC-10 gave
 * cyan/violet, so the `cyan`/`violet` token and `Accent` type names are kept
 * as-is (only their hex values change) to avoid touching every call site
 * that already reads `tokens.cyan`/`heroSurface("cyan")` as "the clinical
 * accent". Derived tones (`*Dark`, `*Light`, `surfaceRaised`) are recomputed
 * from the new hexes by blending 35% toward black/white, not left over from
 * EPIC-10.
 *
 * Typography: IBM Plex Sans for body/UI, Bricolage Grotesque — a genuinely
 * variable display face — reserved for page titles and hero numerals, using
 * its own weight axis (700 for h3, 600 for h4) to carry hierarchy instead of
 * reaching for a second display family.
 *
 * "Señal viva" (live signal) is the narrative metaphor for this palette:
 * traces and pulses that read as biological activity, not ambient neon.
 * It only shows up where EPIC-10 already had motion with a reason (the
 * lub-dub pulse-glow on a truly live state, the header's heartbeat trace)
 * — never as decorative glow added to yet another static component.
 *
 * Two structural ideas carry the whole redesign instead of one repeated
 * card style everywhere:
 *
 * 1. Domain-coded accent — the bioluminescent green always means "looking
 *    at a patient" (imaging/clinical surfaces: the viewer, biomarkers,
 *    segmentation), violet always means "looking at the model" (MLOps
 *    surfaces: training runs, model versions, calibration). The color
 *    carries information, it isn't picked per-component for variety.
 * 2. Two elevation tiers, used deliberately — "quiet" (flat, hairline
 *    border, no glow: tables, lists, secondary panels — the majority of
 *    the UI) and "hero" (raised surface + directional glow, reserved for
 *    the one focal element per screen: the volume viewer, the in-flight
 *    training run, the leading metric). Never both tiers look the same,
 *    and never more than one hero per screen.
 */

export const tokens = {
  bgVoid: "#071a1a",
  surface: "#0f2b28",
  surfaceRaised: "#163f3a",
  cyan: "#34f5c1",
  cyanDark: "#229f7d",
  cyanLight: "#7bf9d7",
  violet: "#7c6ff2",
  violetDark: "#51489d",
  violetLight: "#aaa1f7",
  line: "#163634",
  textPrimary: "#eafaf6",
  textSecondary: "#8fb8ae",
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
    primary: { main: tokens.cyan, light: tokens.cyanLight, dark: tokens.cyanDark, contrastText: "#03120f" },
    secondary: { main: tokens.violet, light: tokens.violetLight, dark: tokens.violetDark, contrastText: "#0d0b1f" },
    success: { main: "#22c55e", light: "#4ade80", dark: "#15803d", contrastText: "#04140a" },
    warning: { main: "#f59e0b", light: "#fbbf24", dark: "#b45309", contrastText: "#1a1102" },
    error: { main: "#ef4444", light: "#f87171", dark: "#b91c1c" },
    background: { default: tokens.bgVoid, paper: tokens.surface },
    divider: tokens.line,
    text: { primary: tokens.textPrimary, secondary: tokens.textSecondary },
  },
  shape: { borderRadius: 10 },
  typography: {
    fontFamily: '"IBM Plex Sans", "Helvetica", "Arial", sans-serif',
    // Bricolage Grotesque is reserved for page titles and hero numerals only
    // — it never runs into body copy or small labels, so it reads as a
    // display role rather than a themed re-skin of every string in the app.
    // It's a genuinely variable font, so h3 vs. h4 lean on its own weight
    // axis (700 vs. 600) instead of loading a second display family.
    h3: { fontFamily: '"Bricolage Grotesque", "IBM Plex Sans", sans-serif', fontWeight: 700, letterSpacing: -0.3 },
    h4: { fontFamily: '"Bricolage Grotesque", "IBM Plex Sans", sans-serif', fontWeight: 600, letterSpacing: -0.2 },
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
          backgroundColor: alpha(tokens.bgVoid, 0.82),
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
          color: "#03120f",
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
          backgroundColor: alpha(tokens.bgVoid, 0.5),
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
  // Was a near-duplicate of the new bioluminescent-green primary in
  // EPIC-10's palette (both mid-lightness greens) — a real hue that reads
  // clearly next to `primary` in a categorical legend (confusion matrix
  // labels, per-class ROC/PR curves) matters more here than a literal
  // "success" association, since this slot is only ever used as the 4th
  // categorical color, never as a standalone semantic indicator.
  quaternary: "#f472b6",
  error: "#f87171",
  info: "#38bdf8",
  grid: alpha(tokens.textSecondary, 0.15),
  axis: tokens.textSecondary,
  reference: alpha(tokens.textSecondary, 0.45),
  tooltipBg: tokens.surfaceRaised,
  tooltipBorder: alpha(tokens.cyan, 0.3),
};

export const categoricalChartColors = [
  chartColors.primary,
  chartColors.secondary,
  chartColors.tertiary,
  chartColors.quaternary,
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
