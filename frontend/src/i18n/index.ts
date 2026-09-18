import i18n from "i18next";
import { initReactI18next } from "react-i18next";

import en from "./locales/en.json";
import es from "./locales/es.json";

export const SUPPORTED_LANGUAGES = ["en", "es"] as const;
export type SupportedLanguage = (typeof SUPPORTED_LANGUAGES)[number];

const STORAGE_KEY = "cardiacai.language";

function isSupportedLanguage(value: string | null): value is SupportedLanguage {
  return value !== null && (SUPPORTED_LANGUAGES as readonly string[]).includes(value);
}

// The app was built English-first (every screen's text is still English by
// default) — the toggle lets a viewer switch to Spanish at any time, it
// doesn't flip the default. A saved choice from a previous visit wins over
// that default.
function initialLanguage(): SupportedLanguage {
  try {
    const saved = localStorage.getItem(STORAGE_KEY);
    if (isSupportedLanguage(saved)) return saved;
  } catch {
    // localStorage can throw in a locked-down browser context (private
    // mode, disabled storage) — falling back to the default is fine, this
    // is a per-viewer convenience, never state anything else depends on.
  }
  return "en";
}

void i18n
  .use(initReactI18next)
  .init({
    resources: { en: { translation: en }, es: { translation: es } },
    lng: initialLanguage(),
    fallbackLng: "en",
    interpolation: { escapeValue: false },
  });

export function setLanguage(language: SupportedLanguage) {
  void i18n.changeLanguage(language);
  try {
    localStorage.setItem(STORAGE_KEY, language);
  } catch {
    // Same as above — persistence is a nice-to-have, not required for the
    // switch to work for the rest of this session.
  }
}

export default i18n;
