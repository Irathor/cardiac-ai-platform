import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import * as authApi from "../src/api/auth";
import * as datasetsApi from "../src/api/datasets";
import * as trainingApi from "../src/api/training";
import { cnn3dMetrics, makeEvaluation, makeModelVersion } from "./fixtures/training";

vi.mock("../src/api/auth");
vi.mock("../src/api/datasets");
vi.mock("../src/api/training");

import { ModelTrainingPage } from "../src/pages/ModelTrainingPage";

const mockedAuth = vi.mocked(authApi);
const mockedDatasets = vi.mocked(datasetsApi);
const mockedTraining = vi.mocked(trainingApi);

function renderPage() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <ModelTrainingPage />
    </QueryClientProvider>,
  );
}

async function loginSuccessfully() {
  mockedAuth.login.mockResolvedValue({ access_token: "test-token", refresh_token: "test-refresh", token_type: "bearer" });
  renderPage();
  await userEvent.click(screen.getByRole("button", { name: "Log in" }));
  await screen.findByText("Retrain");
}

describe("ModelTrainingPage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockedDatasets.listDatasets.mockResolvedValue([]);
    mockedDatasets.listDatasetVersions.mockResolvedValue([]);
    mockedTraining.listModelVersions.mockResolvedValue([]);
    mockedTraining.listTrainingRunsForVersion.mockResolvedValue([]);
  });

  it("shows the login form before authenticating", () => {
    renderPage();
    expect(screen.getByLabelText("Email")).toBeInTheDocument();
    expect(screen.getByLabelText("Password")).toBeInTheDocument();
    expect(screen.queryByText("Retrain")).not.toBeInTheDocument();
  });

  it("shows an error and stays on the login form when login fails", async () => {
    mockedAuth.login.mockRejectedValue(new Error("Login failed with 401"));
    renderPage();
    await userEvent.click(screen.getByRole("button", { name: "Log in" }));
    expect(await screen.findByText("Login failed with 401")).toBeInTheDocument();
    expect(screen.getByLabelText("Email")).toBeInTheDocument();
  });

  it("reveals the retrain panel and model history after a successful login", async () => {
    mockedTraining.listModelVersions.mockResolvedValue([
      makeModelVersion({ id: "mv-1", name: "cardiac-classifier-cnn3d", created_at: "2026-01-02T00:00:00Z" }),
    ]);
    await loginSuccessfully();
    expect(screen.getByRole("button", { name: "Start training" })).toBeInTheDocument();
    expect(await screen.findByText("cardiac-classifier-cnn3d")).toBeInTheDocument();
  });

  it("selecting a model version loads its evaluations and shows the Summary tab", async () => {
    mockedTraining.listModelVersions.mockResolvedValue([
      makeModelVersion({ id: "mv-1", name: "cardiac-classifier-cnn3d", created_at: "2026-01-02T00:00:00Z" }),
    ]);
    mockedTraining.listModelEvaluations.mockResolvedValue([
      makeEvaluation(cnn3dMetrics as unknown as Record<string, unknown>, { model_version_id: "mv-1" }),
    ]);
    await loginSuccessfully();

    await userEvent.click(await screen.findByText("cardiac-classifier-cnn3d"));

    expect(await screen.findByRole("tab", { name: "Summary" })).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: "Classification" })).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: "Calibration" })).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: "Validation" })).toBeInTheDocument();
  });
});
