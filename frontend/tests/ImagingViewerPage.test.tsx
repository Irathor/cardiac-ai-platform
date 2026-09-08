import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import * as analysisApi from "../src/api/analysis";
import * as authApi from "../src/api/auth";
import * as imagingApi from "../src/api/imaging";

vi.mock("../src/api/auth");
vi.mock("../src/api/imaging");
vi.mock("../src/api/analysis");
vi.mock("../src/components/NiftiViewer", () => ({
  NiftiViewer: () => <div data-testid="nifti-viewer-stub" />,
}));

import { ImagingViewerPage } from "../src/pages/ImagingViewerPage";

const mockedAuth = vi.mocked(authApi);
const mockedImaging = vi.mocked(imagingApi);
const mockedAnalysis = vi.mocked(analysisApi);

async function loginSuccessfully() {
  mockedAuth.login.mockResolvedValue({
    access_token: "test-token",
    refresh_token: "test-refresh",
    token_type: "bearer",
  });
  render(<ImagingViewerPage />);
  await userEvent.click(screen.getByRole("button", { name: "Log in" }));
  await screen.findByLabelText("Study ID");
}

describe("ImagingViewerPage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("shows the login form before authenticating", () => {
    render(<ImagingViewerPage />);
    expect(screen.getByLabelText("Email")).toBeInTheDocument();
    expect(screen.getByLabelText("Password")).toBeInTheDocument();
    expect(screen.queryByLabelText("Study ID")).not.toBeInTheDocument();
  });

  it("shows an error when login fails and stays on the login form", async () => {
    mockedAuth.login.mockRejectedValue(new Error("Login failed with 401"));
    render(<ImagingViewerPage />);

    await userEvent.click(screen.getByRole("button", { name: "Log in" }));

    expect(await screen.findByText("Login failed with 401")).toBeInTheDocument();
    expect(screen.getByLabelText("Email")).toBeInTheDocument();
  });

  it("reveals the study/series controls after a successful login", async () => {
    await loginSuccessfully();
    expect(screen.getByRole("button", { name: "Load series" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Run AI analysis" })).toBeInTheDocument();
  });

  it("loads and lists series for a study ID", async () => {
    await loginSuccessfully();
    mockedImaging.fetchSeriesForStudy.mockResolvedValue([
      {
        id: "series-1",
        imaging_study_id: "study-1",
        series_type: "CINE_SHORT_AXIS",
        phase: "ED",
        voxel_spacing_x_mm: 1,
        voxel_spacing_y_mm: 1,
        voxel_spacing_z_mm: 1,
        shape_x: 10,
        shape_y: 10,
        shape_z: 10,
        created_at: "2026-01-01T00:00:00Z",
      },
    ]);

    await userEvent.type(screen.getByLabelText("Study ID"), "study-1");
    await userEvent.click(screen.getByRole("button", { name: "Load series" }));

    expect(await screen.findByText("CINE_SHORT_AXIS (ED)")).toBeInTheDocument();
    expect(mockedImaging.fetchSeriesForStudy).toHaveBeenCalledWith("study-1", "test-token");
  });

  it("selecting a series shows the viewer and its biomarkers", async () => {
    await loginSuccessfully();
    mockedImaging.fetchSeriesForStudy.mockResolvedValue([
      {
        id: "series-1", imaging_study_id: "study-1", series_type: "CINE_SHORT_AXIS", phase: "ED",
        voxel_spacing_x_mm: 1, voxel_spacing_y_mm: 1, voxel_spacing_z_mm: 1,
        shape_x: 10, shape_y: 10, shape_z: 10, created_at: "2026-01-01T00:00:00Z",
      },
    ]);
    mockedImaging.fetchSeriesFile.mockResolvedValue(new Blob(["series"]));
    mockedImaging.fetchSegmentationsForSeries.mockResolvedValue([
      { id: "seg-1", image_series_id: "series-1", model_version: null, created_at: "2026-01-01T00:00:00Z", biomarker_measurements: [] },
    ]);
    mockedImaging.fetchSegmentationFile.mockResolvedValue(new Blob(["mask"]));
    mockedImaging.fetchBiomarkers.mockResolvedValue([
      { id: "bm-1", name: "LV_VOLUME", value: 123.456, unit: "mL" },
    ]);

    await userEvent.type(screen.getByLabelText("Study ID"), "study-1");
    await userEvent.click(screen.getByRole("button", { name: "Load series" }));
    await userEvent.click(await screen.findByText("CINE_SHORT_AXIS (ED)"));

    expect(await screen.findByTestId("nifti-viewer-stub")).toBeInTheDocument();
    expect(await screen.findByText("LV_VOLUME: 123.46 mL")).toBeInTheDocument();
  });

  it("requests an AI analysis, polls until completion, and shows the result", async () => {
    await loginSuccessfully();
    mockedAnalysis.requestAnalysis.mockResolvedValue({
      id: "analysis-1", imaging_study_id: "study-1", status: "QUEUED", model_version: "demo-heuristic-v1",
      features: null, predicted_class: null, probabilities: null, confidence: null,
      feature_attributions: null, error_message: null, created_at: "2026-01-01T00:00:00Z", completed_at: null,
    });
    mockedAnalysis.fetchAnalysis.mockResolvedValue({
      id: "analysis-1", imaging_study_id: "study-1", status: "COMPLETED", model_version: "demo-heuristic-v1",
      features: { EJECTION_FRACTION: 65 }, predicted_class: "NORMAL",
      probabilities: { NORMAL: 0.9, DILATED_CARDIOMYOPATHY: 0.1 }, confidence: 0.9,
      feature_attributions: { EJECTION_FRACTION: 0.5 },
      error_message: null, created_at: "2026-01-01T00:00:00Z", completed_at: "2026-01-01T00:00:05Z",
    });

    await userEvent.type(screen.getByLabelText("Study ID"), "study-1");
    await userEvent.click(screen.getByRole("button", { name: "Run AI analysis" }));

    await waitFor(() => expect(screen.getByText(/AI analysis — COMPLETED/)).toBeInTheDocument(), {
      timeout: 3000,
    });
    const predicted = screen.getByText(/Predicted:/);
    expect(within(predicted).getByText("NORMAL")).toBeInTheDocument();
  });

  it("shows the analysis error message when a run fails", async () => {
    await loginSuccessfully();
    mockedAnalysis.requestAnalysis.mockResolvedValue({
      id: "analysis-2", imaging_study_id: "study-1", status: "FAILED", model_version: "demo-heuristic-v1",
      features: null, predicted_class: null, probabilities: null, confidence: null,
      feature_attributions: null, error_message: "study needs an ED and an ES image series",
      created_at: "2026-01-01T00:00:00Z", completed_at: "2026-01-01T00:00:01Z",
    });

    await userEvent.type(screen.getByLabelText("Study ID"), "study-1");
    await userEvent.click(screen.getByRole("button", { name: "Run AI analysis" }));

    expect(await screen.findByText("study needs an ED and an ES image series")).toBeInTheDocument();
  });
});
