import { Alert, Box, Button, Card, CardContent, CircularProgress, Slider, Stack, Typography } from "@mui/material";
import { useEffect, useRef, useState } from "react";

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

export function attributionColor(value: number): [number, number, number] {
  const v = Math.min(1, Math.max(0, value));
  const [a, b, t] = v < 0.5 ? [COLOR_LOW, COLOR_MID, v / 0.5] : [COLOR_MID, COLOR_HIGH, (v - 0.5) / 0.5];
  return [Math.round(lerp(a[0], b[0], t)), Math.round(lerp(a[1], b[1], t)), Math.round(lerp(a[2], b[2], t))];
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
  const [expanded, setExpanded] = useState(false);
  const [loading, setLoading] = useState(false);
  const [fetchError, setFetchError] = useState<string | null>(null);
  const [parsed, setParsed] = useState<ParsedNpyFloat32 | null>(null);
  const [slice, setSlice] = useState(0);
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
        const [r, g, b] = attributionColor(value);
        const pixelIndex = (j * dimX + i) * 4;
        imageData.data[pixelIndex] = r;
        imageData.data[pixelIndex + 1] = g;
        imageData.data[pixelIndex + 2] = b;
        imageData.data[pixelIndex + 3] = 255;
      }
    }
    ctx.putImageData(imageData, 0, 0);
  }, [parsed, slice]);

  return (
    <Card sx={{ ...quietSurface() }}>
      <CardContent>
        <Stack direction="row" justifyContent="space-between" alignItems="center" flexWrap="wrap" useFlexGap spacing={1}>
          <Typography variant="subtitle1">Grad-CAM attribution</Typography>
          {gradcamAvailable && (
            <Button size="small" variant="outlined" onClick={handleToggle} aria-expanded={expanded}>
              {expanded ? "Hide Grad-CAM" : "Show Grad-CAM"}
            </Button>
          )}
        </Stack>

        {!gradcamAvailable && (
          <Alert severity="info" sx={{ mt: 1 }}>
            Grad-CAM attribution is not available for this analysis
            {gradcamError ? `: ${gradcamError}` : "."}
          </Alert>
        )}

        {gradcamAvailable && expanded && (
          <Box sx={{ mt: 2 }}>
            <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
              This heatmap lives in the model&apos;s own 128×128×12 working space — it is
              not voxel-aligned with the NIfTI series shown above, so read it as an
              independent visualization, not a precise overlay on the scan.
            </Typography>

            {loading && (
              <Stack direction="row" spacing={1} alignItems="center">
                <CircularProgress size={18} />
                <Typography variant="body2" color="text.secondary">
                  Loading Grad-CAM data…
                </Typography>
              </Stack>
            )}

            {fetchError && <Alert severity="error">{fetchError}</Alert>}

            {parsed && (
              <Stack spacing={1} alignItems="center">
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
                    aria-label={`Grad-CAM attribution heatmap, slice ${slice + 1} of ${sliceCount}`}
                    style={{ width: "100%", height: "auto", display: "block" }}
                  />
                </Box>
                <Box sx={{ width: "100%", maxWidth: 320, px: 1 }}>
                  <Typography id="gradcam-slice-label" variant="caption" color="text.secondary">
                    Slice {slice + 1} of {sliceCount}
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
              </Stack>
            )}
          </Box>
        )}
      </CardContent>
    </Card>
  );
}
