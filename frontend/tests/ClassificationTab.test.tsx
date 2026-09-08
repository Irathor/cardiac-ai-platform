import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { ClassificationTab } from "../src/components/training/ClassificationTab";
import { cnn3dMetrics, nearestCentroidMetrics } from "./fixtures/training";

describe("ClassificationTab", () => {
  it("renders the simple per-class accuracy table for nearest-centroid metrics", () => {
    render(<ClassificationTab simpleMetrics={nearestCentroidMetrics} />);
    expect(screen.getByText("30 / 40 cases correct (75.0%)")).toBeInTheDocument();
    expect(screen.getByText("NORMAL")).toBeInTheDocument();
  });

  it("renders confusion matrix, per-class metrics, and ROC/PR curves for CNN3D metrics", () => {
    render(<ClassificationTab cnn3dMetrics={cnn3dMetrics} />);
    expect(screen.getByText("Confusion matrix")).toBeInTheDocument();
    expect(screen.getByText(/Accuracy: 82.0%/)).toBeInTheDocument();
    expect(screen.getByText("Per-class metrics")).toBeInTheDocument();
    expect(screen.getByText("ROC curves (AUC in legend)")).toBeInTheDocument();
    expect(screen.getByText("Precision-recall curves")).toBeInTheDocument();
  });
});
