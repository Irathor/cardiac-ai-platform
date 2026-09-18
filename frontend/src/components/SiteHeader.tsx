import MonitorHeartIcon from "@mui/icons-material/MonitorHeart";
import { AppBar, Box, Button, Stack, Toolbar, Typography } from "@mui/material";
import { Link, useLocation } from "react-router-dom";

import { quietSurface, tokens } from "../theme";

const NAV_ITEMS: Array<{ to: string; label: string }> = [
  { to: "/", label: "Dashboard" },
  { to: "/viewer", label: "Viewer" },
  // Engineering/governance items grouped together, deliberately next to each
  // other and away from /viewer — the explainability showcase is a
  // pedagogical artifact for engineers, never part of the clinical flow
  // (see EPIC-15 "Contrato técnico" point 5).
  { to: "/admin/training", label: "Training" },
  { to: "/explainability-showcase", label: "Explainability showcase" },
];

/** Slim site-wide nav so /viewer, /admin/training, and /explainability-showcase are reachable without editing the URL. */
export function SiteHeader() {
  const location = useLocation();

  return (
    <AppBar position="sticky" elevation={0}>
      <Toolbar sx={{ gap: 2 }}>
        <Box component={Link} to="/" sx={{ textDecoration: "none", flexGrow: 1, display: "flex" }}>
          {/* `width: fit-content` (not the outer flexGrow Box) is what the
              spark's 0%/100% `left` resolves against — it needs to travel
              exactly from the icon to the end of "CardiacAI", not across
              the header's whole remaining width. */}
          <Stack direction="row" spacing={1.25} alignItems="center" sx={{ position: "relative", width: "fit-content" }}>
            <MonitorHeartIcon sx={{ color: "primary.main" }} />
            <Typography
              variant="h6"
              sx={{
                fontFamily: '"Bricolage Grotesque", "IBM Plex Sans", sans-serif',
                color: "text.primary",
                fontWeight: 600,
              }}
            >
              CardiacAI
            </Typography>
            <Box className="logo-spark" aria-hidden="true" />
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
                {item.label}
              </Button>
            );
          })}
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
