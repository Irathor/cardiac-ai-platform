import { ToggleButton, ToggleButtonGroup } from "@mui/material";
import type { MouseEvent } from "react";
import { useTranslation } from "react-i18next";

import { setLanguage, type SupportedLanguage } from "../i18n";
import { quietSurface } from "../theme";

/** Two-button ES/EN switch, changeable at any time from anywhere in the
 * header — i18next itself re-renders every `useTranslation()` consumer the
 * moment the language changes, so no page reload or extra plumbing is
 * needed for the switch to take effect immediately. Same gradient/glow
 * container language as the nav buttons next to it, just smaller and
 * pinned to the bottom of the toolbar with its own left margin so it
 * still reads as a distinct, secondary control rather than a 5th nav
 * item. */
export function LanguageSwitcher() {
  const { i18n, t } = useTranslation();

  function handleChange(_event: MouseEvent<HTMLElement>, value: SupportedLanguage | null) {
    if (value) setLanguage(value);
  }

  return (
    <ToggleButtonGroup
      size="small"
      exclusive
      value={i18n.language}
      onChange={handleChange}
      aria-label={t("language.spanish") + "/" + t("language.english")}
      sx={{ ml: 2, alignSelf: "flex-end" }}
    >
      {(["es", "en"] as const).map((lang) => (
        <ToggleButton
          key={lang}
          value={lang}
          aria-label={lang === "es" ? "Español" : "English"}
          sx={{
            ...quietSurface(),
            minWidth: 0,
            px: 1,
            py: 0.25,
            fontSize: "0.7rem",
            // Explicit values (never `undefined`) on both branches — MUI's
            // own `.Mui-selected` styleOverrides set a solid background at
            // higher specificity than a base sx rule, so leaving the
            // selected case as `undefined` let that flat default win
            // instead of this gradient (found via direct user report).
            backgroundColor: i18n.language === lang ? quietSurface().backgroundColor : "transparent",
            backgroundImage: i18n.language === lang ? quietSurface().backgroundImage : "none",
            color: i18n.language === lang ? "primary.main" : "text.secondary",
            "&.Mui-selected": {
              backgroundColor: quietSurface().backgroundColor,
              backgroundImage: quietSurface().backgroundImage,
              color: "primary.main",
            },
            "&.Mui-selected:hover": {
              backgroundColor: quietSurface().backgroundColor,
              backgroundImage: quietSurface().backgroundImage,
            },
          }}
        >
          {lang === "es" ? t("language.spanish") : t("language.english")}
        </ToggleButton>
      ))}
    </ToggleButtonGroup>
  );
}
