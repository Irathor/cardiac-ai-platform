import MonitorHeartIcon from "@mui/icons-material/MonitorHeart";
import { AppBar, Button, Stack, Toolbar, Typography } from "@mui/material";
import { Link, useLocation } from "react-router-dom";

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
          spacing={1}
          alignItems="center"
          component={Link}
          to="/"
          sx={{ textDecoration: "none", flexGrow: 1 }}
        >
          <MonitorHeartIcon sx={{ color: "primary.main" }} />
          <Typography variant="h6" sx={{ color: "text.primary", fontWeight: 700, letterSpacing: 0.4 }}>
            CardiacAI
          </Typography>
        </Stack>
        <Stack direction="row" spacing={0.5}>
          {NAV_ITEMS.map((item) => {
            const active = location.pathname === item.to;
            return (
              <Button
                key={item.to}
                component={Link}
                to={item.to}
                size="small"
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
    </AppBar>
  );
}
