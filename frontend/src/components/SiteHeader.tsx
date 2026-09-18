import MonitorHeartIcon from "@mui/icons-material/MonitorHeart";
import { AppBar, Box, Button, Stack, Toolbar, Typography } from "@mui/material";
import { type RefObject, useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { Link, useLocation } from "react-router-dom";

import { quietSurface, tokens } from "../theme";
import { LanguageSwitcher } from "./LanguageSwitcher";

// Hand-traced approximation of the "spike" in MonitorHeartIcon's own glyph
// (baseline -> small dip -> sharp peak -> baseline), in the icon's own
// 24x24 viewBox units — re-anchored onto the icon's real rendered box by
// LogoSpark below. The dot only ever travels this far now — once it
// reaches the icon's right edge it hands off to the text-outline border
// (see BORDER_RECT_PADDING below), rather than continuing in a straight
// line through the letters.
const ICON_ZIGZAG: Array<[number, number]> = [
  [1, 12],
  [8, 12],
  [10, 15.5],
  [13.5, 6.5],
  [17, 12],
  [23, 12],
];

// Trailing echoes: same path, same timing, just started a little later —
// since they're identical animations offset only in time, they naturally
// lag behind the lead dot by exactly that time, which is what reads as a
// fading trail (longer while the dot is moving fast through the middle,
// short while it's slow at the start/end, same as a real comet tail).
// Close together + many of them (not 3 spaced-out ones) is what makes this
// blur into a continuous fading line rather than a string of separate dots.
const SPARK_ECHOES: Array<{ delayMs: number; peakOpacity: number }> = [
  { delayMs: 25, peakOpacity: 0.55 },
  { delayMs: 50, peakOpacity: 0.42 },
  { delayMs: 75, peakOpacity: 0.3 },
  { delayMs: 100, peakOpacity: 0.2 },
  { delayMs: 130, peakOpacity: 0.12 },
  { delayMs: 165, peakOpacity: 0.06 },
];

// Padding around the measured text box the outline sits at, and its corner
// radius — just enough breathing room that the stroke doesn't touch the
// letters themselves.
const BORDER_RECT_PADDING = 4;
const BORDER_RECT_RADIUS = 6;

/**
 * The animated dot (+ fading trail) that crosses the icon's own "spike",
 * then hands off to `TextOutline` (below) once it reaches the icon's right
 * edge. Renders nothing until it has measured the icon's real position, so
 * it never flashes at a wrong spot.
 */
function LogoSpark({ iconRef, containerRef }: { iconRef: RefObject<SVGSVGElement | null>; containerRef: RefObject<HTMLDivElement | null> }) {
  const [offsetPath, setOffsetPath] = useState<string | null>(null);

  useEffect(() => {
    const icon = iconRef.current;
    const container = containerRef.current;
    if (!icon || !container) return;
    const iconBox = icon.getBoundingClientRect();
    const containerBox = container.getBoundingClientRect();
    const iconLeft = iconBox.left - containerBox.left;
    const iconTop = iconBox.top - containerBox.top;
    const scaleX = iconBox.width / 24;
    const scaleY = iconBox.height / 24;

    const points = ICON_ZIGZAG.map(([x, y]) => `${iconLeft + x * scaleX},${iconTop + y * scaleY}`);
    setOffsetPath(`path("M ${points.join(" L ")}")`);
  }, [iconRef, containerRef]);

  if (!offsetPath) return null;

  return (
    <>
      <Box aria-hidden="true" className="logo-spark" sx={{ offsetPath }} />
      {SPARK_ECHOES.map(({ delayMs, peakOpacity }) => (
        <Box
          key={delayMs}
          aria-hidden="true"
          className="logo-spark-echo"
          sx={{ offsetPath }}
          style={{ animationDelay: `${delayMs}ms`, ["--spark-peak-opacity" as string]: peakOpacity }}
        />
      ))}
    </>
  );
}

/**
 * The glowing border that draws itself around "CardiacAI" once the dot
 * finishes crossing the icon, holds fully drawn for a beat, then fades out
 * again right as the dot reappears at the icon to start the next loop —
 * timed via `container-text-outline` sharing the same 3.2s cycle as
 * `.logo-spark`'s own `logo-spark-travel` (see index.css for exactly how
 * the handoff is split across that one cycle).
 */
function TextOutline({ textRef, containerRef }: { textRef: RefObject<HTMLElement | null>; containerRef: RefObject<HTMLDivElement | null> }) {
  const [rect, setRect] = useState<{ x: number; y: number; width: number; height: number } | null>(null);

  useEffect(() => {
    const text = textRef.current;
    const container = containerRef.current;
    if (!text || !container) return;
    const textBox = text.getBoundingClientRect();
    const containerBox = container.getBoundingClientRect();
    setRect({
      x: textBox.left - containerBox.left - BORDER_RECT_PADDING,
      y: textBox.top - containerBox.top - BORDER_RECT_PADDING,
      width: textBox.width + BORDER_RECT_PADDING * 2,
      height: textBox.height + BORDER_RECT_PADDING * 2,
    });
  }, [textRef, containerRef]);

  if (!rect) return null;

  return (
    <Box
      aria-hidden="true"
      component="svg"
      className="logo-text-outline"
      sx={{ position: "absolute", top: 0, left: 0, overflow: "visible", pointerEvents: "none" }}
    >
      <rect
        x={rect.x}
        y={rect.y}
        width={rect.width}
        height={rect.height}
        rx={BORDER_RECT_RADIUS}
        pathLength={1}
        fill="none"
      />
    </Box>
  );
}

const NAV_ITEMS: Array<{ to: string; labelKey: string }> = [
  { to: "/", labelKey: "nav.dashboard" },
  { to: "/viewer", labelKey: "nav.viewer" },
  // Engineering/governance items grouped together, deliberately next to each
  // other and away from /viewer — the explainability showcase is a
  // pedagogical artifact for engineers, never part of the clinical flow
  // (see EPIC-15 "Contrato técnico" point 5).
  { to: "/admin/training", labelKey: "nav.training" },
  { to: "/explainability-showcase", labelKey: "nav.explainabilityShowcase" },
];

/** Slim site-wide nav so /viewer, /admin/training, and /explainability-showcase are reachable without editing the URL. */
export function SiteHeader() {
  const location = useLocation();
  const { t } = useTranslation();
  const iconRef = useRef<SVGSVGElement>(null);
  const logoTextRef = useRef<HTMLElement>(null);
  const logoContainerRef = useRef<HTMLDivElement>(null);

  return (
    <AppBar position="sticky" elevation={0}>
      <Toolbar sx={{ gap: 2 }}>
        <Box component={Link} to="/" sx={{ textDecoration: "none", flexGrow: 1, display: "flex" }}>
          {/* `width: fit-content` (not the outer flexGrow Box) is what
              LogoSpark measures against — the path needs to run exactly
              from the icon to the end of "CardiacAI", not across the
              header's whole remaining width. */}
          <Stack
            ref={logoContainerRef}
            direction="row"
            spacing={1.25}
            alignItems="center"
            sx={{ position: "relative", width: "fit-content" }}
          >
            <MonitorHeartIcon ref={iconRef} sx={{ color: "primary.main" }} />
            <Typography
              ref={logoTextRef}
              variant="h6"
              sx={{
                fontFamily: '"Bricolage Grotesque", "IBM Plex Sans", sans-serif',
                color: "text.primary",
                fontWeight: 600,
              }}
            >
              CardiacAI
            </Typography>
            <LogoSpark iconRef={iconRef} containerRef={logoContainerRef} />
            <TextOutline textRef={logoTextRef} containerRef={logoContainerRef} />
          </Stack>
        </Box>
        <Stack direction="row" spacing={0.5} component="nav" aria-label="Primary">
          {NAV_ITEMS.map((item) => {
            const active = location.pathname === item.to;
            return (
              <Button
                key={item.to}
                component={Link}
                to={item.to}
                size="small"
                aria-current={active ? "page" : undefined}
                sx={{
                  ...quietSurface(),
                  // Nav items are the same "container box" language as every
                  // other card on the site (gradient + hover glow) — only
                  // the active one keeps its own filled background; inactive
                  // ones stay transparent until hovered.
                  backgroundColor: active ? undefined : "transparent",
                  backgroundImage: active ? quietSurface().backgroundImage : "none",
                  color: active ? "primary.main" : "text.secondary",
                }}
              >
                {t(item.labelKey)}
              </Button>
            );
          })}
          <LanguageSwitcher />
        </Stack>
      </Toolbar>
      {/* The single structural motif tying the chrome to the subject matter:
          a flat baseline that breaks into one heartbeat trace, instead of a
          generic gradient rule under the header. Decorative only — the real
          "live" signal is the pulse-glow chip elsewhere on each page. */}
      <Box
        aria-hidden
        component="svg"
        viewBox="0 0 1200 20"
        preserveAspectRatio="none"
        sx={{ display: "block", width: "100%", height: 10, opacity: 0.55 }}
      >
        <polyline
          points="0,10 520,10 545,10 560,2 575,18 590,10 610,10 1200,10"
          fill="none"
          stroke={tokens.cyan}
          strokeWidth={1.25}
          vectorEffect="non-scaling-stroke"
        />
      </Box>
    </AppBar>
  );
}
