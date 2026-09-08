import { Alert } from "@mui/material";

/**
 * Persistent, non-dismissible disclaimer required on every screen (see docs/clinical-limitations.md).
 * This must never be rendered as a closable snackbar/toast — it is a permanent fixture of the layout.
 */
export function ResearchDisclaimerBanner() {
  return (
    <Alert severity="warning" variant="filled" square sx={{ justifyContent: "center" }}>
      Research prototype only. Not validated for clinical diagnosis or treatment decisions.
    </Alert>
  );
}
