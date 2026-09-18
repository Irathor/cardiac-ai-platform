import {
  Alert,
  Box,
  Button,
  Card,
  CardContent,
  CircularProgress,
  Slider,
  Stack,
  ToggleButton,
  ToggleButtonGroup,
  Typography,
} from "@mui/material";
import { useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";

import { fetchGradcamAttribution } from "../api/analysis";
import { parseNpyFloat32, type ParsedNpyFloat32 } from "../lib/npy";
import { quietSurface, tokens } from "../theme";

export interface GradcamPanelProps {
  analysisId: string;
  token: string;
  /** From `AIAnalysis.gradcam_available` — whether the endpoint has a map to serve. */
  gradcamAvailable: boolean;
  /** From `AIAnalysis.gradcam_error` — the honest reason when it doesn't. */
  gradcamError: string | null;
}

function hexToRgb(hex: string): [number, number, number] {
  const clean = hex.replace("#", "");
  return [
    Number.parseInt(clean.slice(0, 2), 16),
    Number.parseInt(clean.slice(2, 4), 16),
    Number.parseInt(clean.slice(4, 6), 16),
  ];
}

function lerp(a: number, b: number, t: number): number {
  return a + (b - a) * t;
}

// Attribution-intensity colormap for the Grad-CAM canvas. Deliberately NOT
// the literal rainbow "jet" colormap (red/green/blue hue rotation) that
// generic heatmap tropes default to — that would fight the theme's
// domain-coded accent system (EPIC-13: cyan = "looking at a patient",
// violet = "looking at the model") by introducing hues with no meaning in
// this app. Instead it's a brightness ramp on the theme's own clinical
// accent: dark surface (low attribution) rising through bioluminescent
// cyan into a saturated near-white glow at peak attribution — still reads
// unambiguously as "more attribution = more intense", just on-brand.
const COLOR_LOW = hexToRgb(tokens.bgVoid);
const COLOR_MID = hexToRgb(tokens.cyan);
const COLOR_HIGH = hexToRgb("#f4fff9");

export function siteAttributionColor(value: number): [number, number, number] {
  const raw = Math.min(1, Math.max(0, value));
  // Gamma-boost midtones (v^0.6) before mapping to color: a raw linear ramp
  // made a real (smooth, low-magnitude) attribution map read as a flat,
  // contextless blob. Boosting contrast in the low-to-mid range without
  // changing the palette gives the hot core real visual separation from
  // its halo, while staying on-brand (still the same three theme colors,
  // not a rainbow) — this is the "Website colors" mode.
  const v = raw ** 0.6;
  const [a, b, t] = v < 0.5 ? [COLOR_LOW, COLOR_MID, v / 0.5] : [COLOR_MID, COLOR_HIGH, (v - 0.5) / 0.5];
  return [Math.round(lerp(a[0], b[0], t)), Math.round(lerp(a[1], b[1], t)), Math.round(lerp(a[2], b[2], t))];
}

/** Standard "jet" colormap (blue -> cyan -> green -> yellow -> red) —
 * the same colormap `ml/scripts/run_explainability_showcase.py` already
 * uses (matplotlib `cmap="jet"`) for the offline Seg-Grad-CAM/Grad-CAM
 * renders, so switching to this mode shows the same visual language as
 * those reference images. Standard piecewise-linear jet approximation. */
function jetAttributionColor(value: number): [number, number, number] {
  const v = Math.min(1, Math.max(0, value));
  const r = Math.min(Math.max(Math.min(4 * v - 1.5, -4 * v + 4.5), 0), 1);
  const g = Math.min(Math.max(Math.min(4 * v - 0.5, -4 * v + 3.5), 0), 1);
  const b = Math.min(Math.max(Math.min(4 * v + 0.5, -4 * v + 2.5), 0), 1);
  return [Math.round(r * 255), Math.round(g * 255), Math.round(b * 255)];
}

export type ColorScheme = "site" | "standard";

export function attributionColor(value: number, scheme: ColorScheme = "site"): [number, number, number] {
  return scheme === "standard" ? jetAttributionColor(value) : siteAttributionColor(value);
}

const LEGEND_STOPS = [0, 0.25, 0.5, 0.75, 1];

/** Horizontal legend for the active colormap — without this, the heatmap is
 * an ungrounded blob with no indication of what the colors mean (found via
 * direct user feedback on the first render of this panel). */
function AttributionLegend({ scheme }: { scheme: ColorScheme }) {
  const { t } = useTranslation();
  const gradientStops = LEGEND_STOPS.map((stop) => {
    const [r, g, b] = attributionColor(stop, scheme);
    return `rgb(${r},${g},${b}) ${stop * 100}%`;
  }).join(", ");
  return (
    <Box sx={{ width: "100%" }}>
      <Box
        sx={{
          height: 10,
          borderRadius: "4px",
          background: `linear-gradient(90deg, ${gradientStops})`,
          border: `1px solid ${tokens.line}`,
        }}
      />
      <Stack direction="row" justifyContent="space-between" sx={{ mt: 0.5 }}>
        <Typography variant="caption" color="text.secondary">
          {t("gradcam.lowAttribution")}
        </Typography>
        <Typography variant="caption" color="text.secondary">
          {t("gradcam.highAttribution")}
        </Typography>
      </Stack>
    </Box>
  );
}

/**
 * Grad-CAM attribution panel — lives as its own quiet-tier card below the
 * `NiftiViewer`, never inside it (see EPIC-14's "Contrato técnico": the
 * 128×128×12 array lives in the model's own working space, not the native
 * series space, so it's rendered as an independent slice viewer rather than
 * a Niivue overlay that would imply a spatial correspondence that doesn't
 * exist). Owns its own fetch: nothing happens until the user asks to see it.
 */
export function GradcamPanel({ analysisId, token, gradcamAvailable, gradcamError }: GradcamPanelProps) {
  const { t } = useTranslation();
  const [expanded, setExpanded] = useState(false);
  const [loading, setLoading] = useState(false);
  const [fetchError, setFetchError] = useState<string | null>(null);
  const [parsed, setParsed] = useState<ParsedNpyFloat32 | null>(null);
  const [slice, setSlice] = useState(0);
  const [colorScheme, setColorScheme] = useState<ColorScheme>("site");
  const canvasRef = useRef<HTMLCanvasElement>(null);

  function handleToggle() {
    setExpanded((prev) => !prev);
    if (!parsed && !loading) {
      setLoading(true);
      setFetchError(null);
      fetchGradcamAttribution(analysisId, token)
        .then((blob) => blob.arrayBuffer())
        .then((buffer) => {
          const result = parseNpyFloat32(buffer);
          setParsed(result);
          setSlice(0);
        })
        .catch((err) => {
          setFetchError(err instanceof Error ? err.message : "Could not load Grad-CAM data");
        })
        .finally(() => setLoading(false));
    }
  }

  const sliceCount = parsed ? parsed.shape[2] : 0;

  useEffect(() => {
    if (!parsed || !canvasRef.current) return;
    const [dimX, dimY, depth] = parsed.shape;
    const canvas = canvasRef.current;
    canvas.width = dimX;
    canvas.height = dimY;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;
    const imageData = ctx.createImageData(dimX, dimY);
    for (let i = 0; i < dimX; i++) {
      for (let j = 0; j < dimY; j++) {
        const value = parsed.data[i * dimY * depth + j * depth + slice];
        const [r, g, b] = attributionColor(value, colorScheme);
        const pixelIndex = (j * dimX + i) * 4;
        imageData.data[pixelIndex] = r;
        imageData.data[pixelIndex + 1] = g;
        imageData.data[pixelIndex + 2] = b;
        imageData.data[pixelIndex + 3] = 255;
      }
    }
    ctx.putImageData(imageData, 0, 0);
  }, [parsed, slice, colorScheme]);

  return (
    <Card sx={{ ...quietSurface() }}>
      <CardContent>
        <Stack direction="row" justifyContent="space-between" alignItems="center" flexWrap="wrap" useFlexGap spacing={1}>
          <Typography variant="subtitle1">{t("gradcam.title")}</Typography>
          {gradcamAvailable && (
            <Button size="small" variant="outlined" onClick={handleToggle} aria-expanded={expanded}>
              {expanded ? t("gradcam.hide") : t("gradcam.show")}
            </Button>
          )}
        </Stack>

        {!gradcamAvailable && (
          <Alert severity="info" sx={{ mt: 1 }}>
            {t("gradcam.notAvailable")}
            {gradcamError ? `: ${gradcamError}` : "."}
          </Alert>
        )}

        {gradcamAvailable && expanded && (
          <Box sx={{ mt: 2 }}>
            <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
              {t("gradcam.spaceNote")}
            </Typography>

            {loading && (
              <Stack direction="row" spacing={1} alignItems="center">
                <CircularProgress size={18} />
                <Typography variant="body2" color="text.secondary">
                  {t("gradcam.loading")}
                </Typography>
              </Stack>
            )}

            {fetchError && <Alert severity="error">{fetchError}</Alert>}

            {parsed && (
              <Stack spacing={1} alignItems="center">
                <ToggleButtonGroup
                  size="small"
                  exclusive
                  value={colorScheme}
                  onChange={(_, value: ColorScheme | null) => {
                    if (value) setColorScheme(value);
                  }}
                  aria-label="Grad-CAM colormap"
                >
                  <ToggleButton value="standard" aria-label="Standard colormap">
                    {t("gradcam.standard")}
                  </ToggleButton>
                  <ToggleButton value="site" aria-label="Website colors">
                    {t("gradcam.websiteColors")}
                  </ToggleButton>
                </ToggleButtonGroup>

                <Box
                  sx={{
                    width: "100%",
                    maxWidth: 320,
                    border: `1px solid ${tokens.line}`,
                    borderRadius: "8px",
                    overflow: "hidden",
                  }}
                >
                  <canvas
                    ref={canvasRef}
                    role="img"
                    aria-label={`Grad-CAM attribution heatmap, slice ${slice + 1} of ${sliceCount}, ${colorScheme} colormap`}
                    style={{ width: "100%", height: "auto", display: "block" }}
                  />
                </Box>
                <Box sx={{ width: "100%", maxWidth: 320, px: 1 }}>
                  <Typography id="gradcam-slice-label" variant="caption" color="text.secondary">
                    {t("gradcam.sliceLabel", { current: slice + 1, total: sliceCount })}
                  </Typography>
                  <Slider
                    aria-labelledby="gradcam-slice-label"
                    getAriaValueText={(v) => `Slice ${v + 1} of ${sliceCount}`}
                    size="small"
                    min={0}
                    max={Math.max(0, sliceCount - 1)}
                    step={1}
                    value={slice}
                    onChange={(_, value) => setSlice(value as number)}
                    valueLabelDisplay="auto"
                    valueLabelFormat={(v) => `${v + 1}`}
                  />
                </Box>
                <Box sx={{ width: "100%", maxWidth: 320, px: 1 }}>
                  <AttributionLegend scheme={colorScheme} />
                </Box>
              </Stack>
            )}
          </Box>
        )}
      </CardContent>
    </Card>
  );
}
