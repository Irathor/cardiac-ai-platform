import { Alert, Box, Button, Card, CardContent, Fade, Stack, TextField, Typography } from "@mui/material";
import { useTranslation } from "react-i18next";

import { heroSurface } from "../theme";

interface LoginCardProps {
  title: string;
  email: string;
  password: string;
  error: string | null;
  onEmailChange: (value: string) => void;
  onPasswordChange: (value: string) => void;
  onSubmit: () => void;
}

/** Centered, focused login presentation shared by the viewer and training pages. */
export function LoginCard({ title, email, password, error, onEmailChange, onPasswordChange, onSubmit }: LoginCardProps) {
  const { t } = useTranslation();
  return (
    <Fade in timeout={400}>
      <Box sx={{ display: "flex", justifyContent: "center", mt: 6 }}>
        <Card sx={{ ...heroSurface("cyan"), width: "100%", maxWidth: 400 }}>
          <CardContent sx={{ p: 4 }}>
            <Typography
              variant="h6"
              gutterBottom
              sx={{ fontFamily: '"Bricolage Grotesque", "IBM Plex Sans", sans-serif', fontWeight: 600 }}
            >
              {title}
            </Typography>
            <Typography variant="body2" color="text.secondary" sx={{ mb: 3 }}>
              {t("login.signInToContinue")}
            </Typography>
            <Stack spacing={2}>
              <TextField
                label={t("login.email")}
                value={email}
                onChange={(e) => onEmailChange(e.target.value)}
                fullWidth
              />
              <TextField
                label={t("login.password")}
                type="password"
                value={password}
                onChange={(e) => onPasswordChange(e.target.value)}
                fullWidth
              />
              <Button variant="contained" size="large" onClick={onSubmit}>
                {t("login.logIn")}
              </Button>
              {error && <Alert severity="error">{error}</Alert>}
            </Stack>
          </CardContent>
        </Card>
      </Box>
    </Fade>
  );
}
