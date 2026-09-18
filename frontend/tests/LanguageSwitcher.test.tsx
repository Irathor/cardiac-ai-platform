import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { App } from "../src/app/App";
import i18n from "../src/i18n";

// The switcher lives in SiteHeader, not on any individual page — rendering
// the real App (same pattern as App.test.tsx) is what actually exercises
// it, rather than a page component in isolation.
function renderApp() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={["/"]}>
        <App />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("LanguageSwitcher", () => {
  beforeEach(() => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({ ok: true, json: async () => ({ status: "ok" }) }),
    );
  });

  afterEach(async () => {
    vi.unstubAllGlobals();
    // Every test in this file changes global i18next state — reset it and
    // clear the persisted choice so other test files aren't affected by
    // whichever one ran last.
    localStorage.removeItem("cardiacai.language");
    await i18n.changeLanguage("en");
  });

  it("switches every translated string on the page and persists the choice", async () => {
    renderApp();
    expect(screen.getByText("CardiacAI Research Platform")).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Imaging viewer" })).toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: "Español" }));

    expect(
      await screen.findByText(
        "Segmentación automatizada de RM cardíaca, extracción de biomarcadores funcionales y clasificación explicable de enfermedades",
      ),
    ).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Visor de imágenes" })).toBeInTheDocument();
    expect(localStorage.getItem("cardiacai.language")).toBe("es");
  });

  it("switches back to English immediately, no reload needed", async () => {
    renderApp();
    await userEvent.click(screen.getByRole("button", { name: "Español" }));
    await screen.findByRole("heading", { name: "Visor de imágenes" });

    await userEvent.click(screen.getByRole("button", { name: "English" }));

    expect(await screen.findByRole("heading", { name: "Imaging viewer" })).toBeInTheDocument();
    expect(localStorage.getItem("cardiacai.language")).toBe("en");
  });
});
