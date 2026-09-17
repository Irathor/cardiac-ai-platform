import MonitorHeartIcon from "@mui/icons-material/MonitorHeart";
import { AppBar, Box, Button, Stack, Toolbar, Typography } from "@mui/material";
import { Link, useLocation } from "react-router-dom";

import { tokens } from "../theme";

const NAV_ITEMS: Array<{ to: string; label: string }> = [
  { to: "/", label: "Dashboard" },
  { to: "/viewer", label: "Viewer" },
  { to: "/admin/training", label: "Training" },
];

/** Slim site-wide nav so /viewer and /admin/training are reachable without editing the URL. */
export function SiteHeader() {
  const location = useLocation();

  return (
    <AppBar position="sticky" elevation={0}>
      <Toolbar sx={{ gap: 2 }}>
        <Stack
          direction="row"
          spacing={1.25}
          alignItems="center"
          component={Link}
          to="/"
          sx={{ textDecoration: "none", flexGrow: 1 }}
        >
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
        </Stack>
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
                  color: active ? "primary.main" : "text.secondary",
                  backgroundColor: active ? "action.selected" : "transparent",
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
