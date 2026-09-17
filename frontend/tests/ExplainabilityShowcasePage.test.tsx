import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import * as authApi from "../src/api/auth";
import * as explainabilityApi from "../src/api/explainability";
import { ApiError } from "../src/api/client";
import type { ExplainabilityShowcase } from "../src/api/explainability";

vi.mock("../src/api/auth");
vi.mock("../src/api/explainability");

import { ExplainabilityShowcasePage } from "../src/pages/ExplainabilityShowcasePage";

const mockedAuth = vi.mocked(authApi);
const mockedExplainability = vi.mocked(explainabilityApi);

const SAMPLE_SHOWCASE: ExplainabilityShowcase = {
  unet_seg_grad_cam: {
    patient_id: "patient101",
    slice_index: 5,
    structures: {
      LV: { png_path: "data\\models\\explainability\\unet_gradcam_patient101_LV.png", attribution_mean: 0.03 },
      RV: { png_path: "data\\models\\explainability\\unet_gradcam_patient101_RV.png", attribution_mean: 0.01 },
      MYO: { png_path: "data\\models\\explainability\\unet_gradcam_patient101_MYO.png", attribution_mean: 0.02 },
    },
  },
  cnn3d_grad_cam: {
    patient_id: "patient101",
    true_class: "DILATED_CARDIOMYOPATHY",
    predicted_class: "DILATED_CARDIOMYOPATHY",
    png_path: "data\\models\\explainability\\cnn3d_gradcam_patient101_z6.png",
  },
  lime_shapley_panel: {
    patient_id: "patient101",
    predicted_class: "MYOCARDIAL_INFARCTION",
    method_attributions: {
      "LIME (aproximado)": { EJECTION_FRACTION: -0.26, LV_EDV: -0.02 },
      "Shapley (exacto)": { EJECTION_FRACTION: 3.82, LV_EDV: -0.31 },
    },
    note: "Panel comparativo pedagogico (ver ADR-3).",
  },
};

function renderPage() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <ExplainabilityShowcasePage />
    </QueryClientProvider>,
  );
}

async function loginSuccessfully() {
  mockedAuth.login.mockResolvedValue({ access_token: "test-token", refresh_token: "test-refresh", token_type: "bearer" });
  renderPage();
  await userEvent.click(screen.getByRole("button", { name: "Log in" }));
}

describe("ExplainabilityShowcasePage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockedExplainability.pngBasename.mockImplementation((path: string) => path.split(/[/\\]/).pop() ?? path);
    mockedExplainability.fetchExplainabilityShowcaseImage.mockResolvedValue(new Blob(["png-bytes"]));
    URL.createObjectURL = vi.fn(() => "blob:mock-url");
    URL.revokeObjectURL = vi.fn();
  });

  it("shows the permanent pedagogical disclaimer even before logging in", () => {
    renderPage();
    expect(
      screen.getByText(
        "Esta página es una comparación pedagógica offline, no una explicación de producción — ver ADR-3.",
      ),
    ).toBeInTheDocument();
  });

  it("shows the login form before authenticating", () => {
    renderPage();
    expect(screen.getByLabelText("Email")).toBeInTheDocument();
    expect(screen.getByLabelText("Password")).toBeInTheDocument();
  });

  it("renders the Grad-CAM sections and the LIME vs. Shapley panel with the literal backend labels on success", async () => {
    mockedExplainability.fetchExplainabilityShowcase.mockResolvedValue(SAMPLE_SHOWCASE);
    await loginSuccessfully();

    expect(await screen.findByText("Seg-Grad-CAM — U-Net")).toBeInTheDocument();
    expect(screen.getByText("Grad-CAM — CNN3D")).toBeInTheDocument();
    expect(screen.getByText("LIME vs. Shapley")).toBeInTheDocument();

    // Method labels must be shown exactly as the backend returns them.
    expect(screen.getByText("LIME (aproximado)")).toBeInTheDocument();
    expect(screen.getByText("Shapley (exacto)")).toBeInTheDocument();
    expect(screen.getByText("EJECTION_FRACTION")).toBeInTheDocument();

    // The permanent disclaimer is still visible while the data is shown.
    expect(
      screen.getByText(
        "Esta página es una comparación pedagógica offline, no una explicación de producción — ver ADR-3.",
      ),
    ).toBeInTheDocument();
  });

  it("shows an honest message when the showcase has not been generated in this environment (404)", async () => {
    mockedExplainability.fetchExplainabilityShowcase.mockRejectedValue(
      new ApiError(404, "GET /explainability/showcase failed with 404"),
    );
    await loginSuccessfully();

    expect(
      await screen.findByText(
        "Explainability showcase not generated in this environment. Run ml/scripts/run_explainability_showcase.py first.",
      ),
    ).toBeInTheDocument();
    expect(screen.queryByText("Seg-Grad-CAM — U-Net")).not.toBeInTheDocument();
  });

  it("shows a generic error message for a non-404 failure, not an infinite loading state", async () => {
    mockedExplainability.fetchExplainabilityShowcase.mockRejectedValue(new Error("Network error"));
    await loginSuccessfully();

    expect(await screen.findByText("Network error")).toBeInTheDocument();
  });
});
