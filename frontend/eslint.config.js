import js from "@eslint/js";
import tseslint from "@typescript-eslint/eslint-plugin";
import tsParser from "@typescript-eslint/parser";
import globals from "globals";

export default [
  js.configs.recommended,
  {
    files: ["**/*.{ts,tsx}"],
    languageOptions: {
      parser: tsParser,
      parserOptions: { ecmaFeatures: { jsx: true } },
      // Without this, ESLint's no-undef flags every DOM/browser global
      // (fetch, Blob, URL, document, setTimeout, ...) as undefined —
      // this is a browser SPA, not a Node script.
      globals: { ...globals.browser },
    },
    plugins: { "@typescript-eslint": tseslint },
    rules: {
      ...tseslint.configs.recommended.rules,
    },
  },
  { ignores: ["dist/**", "node_modules/**"] },
];
