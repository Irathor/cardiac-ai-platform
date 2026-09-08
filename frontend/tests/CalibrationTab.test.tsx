import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { CalibrationTab } from "../src/components/training/CalibrationTab";
import { cnn3dMetrics } from "./fixtures/training";

describe("CalibrationTab", () => {
  it("renders Brier/log-loss/ECE chips, the reliability diagram, and the risk-coverage curve", () => {
    render(<CalibrationTab report={cnn3dMetrics.external_test.validation} />);

    expect(screen.getByText(/Multiclass Brier score: 0.120/)).toBeInTheDocument();
    expect(screen.getByText(/Log loss: 0.400/)).toBeInTheDocument();
    expect(screen.getByText("Reliability diagram")).toBeInTheDocument();
    expect(screen.getByText("Risk-coverage curve")).toBeInTheDocument();
    expect(screen.getByText(/Selective accuracy \(reject 5%\)/)).toBeInTheDocument();
  });
});
