import { Alert } from "@mui/material";
import { useTranslation } from "react-i18next";

/**
 * Persistent, non-dismissible disclaimer required on every screen (see docs/clinical-limitations.md).
 * This must never be rendered as a closable snackbar/toast — it is a permanent fixture of the layout.
 */
export function ResearchDisclaimerBanner() {
  const { t } = useTranslation();
  return (
    <Alert
      severity="warning"
      variant="filled"
      square
      sx={{ justifyContent: "center", fontWeight: 600, letterSpacing: 0.2 }}
    >
      {t("disclaimer.text")}
    </Alert>
  );
}
