import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { ValidationTab } from "../src/components/training/ValidationTab";
import { cnn3dMetrics, unetMetrics } from "./fixtures/training";

describe("ValidationTab", () => {
  it("renders per-fold accuracy, CV summary, and bootstrap CIs for CNN3D metrics", () => {
    render(<ValidationTab cnn3dMetrics={cnn3dMetrics} />);
    expect(screen.getByText("Per-fold accuracy")).toBeInTheDocument();
    expect(screen.getByText("Bootstrap 95% CI (external test)")).toBeInTheDocument();
    expect(screen.getByText("Out-of-fold vs. external test")).toBeInTheDocument();
    expect(screen.getByText(/Not implemented in this version/)).toBeInTheDocument();
  });

  it("renders bootstrap Dice CIs and marks per-fold CV as not applicable for U-Net metrics", () => {
    render(<ValidationTab unetMetrics={unetMetrics} />);
    expect(screen.getByText(/not applicable to this model/)).toBeInTheDocument();
    expect(screen.getByText("Bootstrap 95% CI (Dice, by structure/phase)")).toBeInTheDocument();
    expect(screen.getByText("LV_ED")).toBeInTheDocument();
  });
});
