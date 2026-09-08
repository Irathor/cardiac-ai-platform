import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { SegmentationTab } from "../src/components/training/SegmentationTab";
import { unetMetrics } from "./fixtures/training";

describe("SegmentationTab", () => {
  it("renders per-structure bar charts, the dispersion table, and the loss curve", () => {
    render(<SegmentationTab metrics={unetMetrics} />);

    expect(screen.getByText("Per-structure metrics by phase")).toBeInTheDocument();
    // "Dice" appears twice: the bar-chart subtitle and the metric selector's current value.
    expect(screen.getAllByText("Dice").length).toBeGreaterThan(0);
    expect(screen.getByText("Dispersion summary")).toBeInTheDocument();
    expect(screen.getAllByText("LV").length).toBeGreaterThan(0);
    expect(screen.getByText("Empty-mask and anatomical-violation rates")).toBeInTheDocument();
    expect(screen.getByText(/Anatomical violation rate/)).toBeInTheDocument();
    expect(screen.getByText("Training curve")).toBeInTheDocument();
  });
});
