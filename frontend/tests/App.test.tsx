import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { App } from "../src/app/App";

function renderApp(initialPath = "/") {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={[initialPath]}>
        <App />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("App", () => {
  beforeEach(() => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        ok: true,
        json: async () => ({ status: "ok" }),
      }),
    );
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("always shows the research disclaimer banner, on every route", () => {
    renderApp("/viewer");
    expect(
      screen.getByText(
        "Research prototype only. Not validated for clinical diagnosis or treatment decisions.",
      ),
    ).toBeInTheDocument();
  });

  it("shows the dashboard title and backend status at /", async () => {
    renderApp("/");
    expect(screen.getByText("CardiacAI Research Platform")).toBeInTheDocument();
    await waitFor(() => expect(screen.getByText("online")).toBeInTheDocument());
  });

  it("shows a chip indicating the backend is unreachable when the health check fails", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: false, status: 503 }));
    renderApp("/");
    await waitFor(() => expect(screen.getByText("unreachable")).toBeInTheDocument());
  });

  it("navigates to the imaging viewer when the link is clicked", async () => {
    renderApp("/");
    await userEvent.click(screen.getByRole("link", { name: "Imaging viewer" }));
    expect(await screen.findByRole("heading", { name: "Imaging viewer" })).toBeInTheDocument();
  });

  it("renders the imaging viewer's login form directly at /viewer", () => {
    renderApp("/viewer");
    expect(screen.getByRole("heading", { name: "Imaging viewer" })).toBeInTheDocument();
    expect(screen.getByLabelText("Email")).toBeInTheDocument();
    expect(screen.getByLabelText("Password")).toBeInTheDocument();
  });
});
