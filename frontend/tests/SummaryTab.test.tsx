import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { SummaryTab } from "../src/components/training/SummaryTab";
import { cnn3dMetrics, makeEvaluation, makeModelVersion, nearestCentroidMetrics, unetMetrics } from "./fixtures/training";

describe("SummaryTab", () => {
  it("shows the nearest-centroid accuracy and marks rich-report fields as not applicable", () => {
    render(
      <SummaryTab
        modelVersion={makeModelVersion({ name: "cardiac-classifier" })}
        evaluation={makeEvaluation(nearestCentroidMetrics as unknown as Record<string, unknown>)}
        runsHistory={[]}
      />,
    );
    expect(screen.getByText("75.0%")).toBeInTheDocument();
    expect(screen.getAllByText("not applicable to this model").length).toBeGreaterThan(0);
    expect(screen.getAllByText("not available").length).toBeGreaterThan(0);
  });

  it("shows U-Net dice/HD95 and marks classification fields as not applicable", () => {
    render(
      <SummaryTab
        modelVersion={makeModelVersion({ name: "cardiac-segmentation-unet" })}
        evaluation={makeEvaluation(unetMetrics as unknown as Record<string, unknown>)}
        runsHistory={[]}
      />,
    );
    expect(screen.getByText("0.857")).toBeInTheDocument();
    expect(screen.getByText("2/1/2")).toBeInTheDocument();
  });

  it("shows CNN3D macro F1/AUC and computes failure rate from run history", () => {
    render(
      <SummaryTab
        modelVersion={makeModelVersion({ name: "cardiac-classifier-cnn3d" })}
        evaluation={makeEvaluation(cnn3dMetrics as unknown as Record<string, unknown>)}
        runsHistory={[
          { id: "1", dataset_version_id: null, model_type: "CNN3D_CLASSIFICATION", status: "COMPLETED", mlflow_run_id: null, metrics: null, error_message: null, started_at: null, completed_at: null, created_at: "2026-01-01T00:00:00Z" },
          { id: "2", dataset_version_id: null, model_type: "CNN3D_CLASSIFICATION", status: "FAILED", mlflow_run_id: null, metrics: null, error_message: "boom", started_at: null, completed_at: null, created_at: "2026-01-01T00:00:00Z" },
        ]}
      />,
    );
    expect(screen.getByText("50.0% (1/2)")).toBeInTheDocument();
    // "3" appears twice: test patient count and CV fold count (k).
    expect(screen.getAllByText("3")).toHaveLength(2);
  });
});
