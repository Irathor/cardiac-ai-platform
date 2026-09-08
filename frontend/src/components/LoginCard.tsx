import { Alert, Box, Button, Card, CardContent, Fade, Stack, TextField, Typography } from "@mui/material";

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
  return (
    <Fade in timeout={400}>
      <Box sx={{ display: "flex", justifyContent: "center", mt: 6 }}>
        <Card sx={{ width: "100%", maxWidth: 400 }}>
          <CardContent sx={{ p: 4 }}>
            <Typography variant="h6" gutterBottom>
              {title}
            </Typography>
            <Typography variant="body2" color="text.secondary" sx={{ mb: 3 }}>
              Sign in to continue.
            </Typography>
            <Stack spacing={2}>
              <TextField label="Email" value={email} onChange={(e) => onEmailChange(e.target.value)} fullWidth />
              <TextField
                label="Password"
                type="password"
                value={password}
                onChange={(e) => onPasswordChange(e.target.value)}
                fullWidth
              />
              <Button variant="contained" size="large" onClick={onSubmit}>
                Log in
              </Button>
              {error && <Alert severity="error">{error}</Alert>}
            </Stack>
          </CardContent>
        </Card>
      </Box>
    </Fade>
  );
}
