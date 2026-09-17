import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { DriftTab } from "../src/components/training/DriftTab";
import type { ModelDriftReport } from "../src/api/training";

const baseReport: ModelDriftReport = {
  model_version_id: "model-version-1",
  evaluated_at: "2026-01-05T10:00:00Z",
  biomarkers: [
    {
      biomarker_name: "LVEF",
      ks_statistic: 0.32,
      p_value: 0.01,
      base_sample_size: 120,
      recent_sample_size: 40,
      drift_detected: true,
      skipped_reason: null,
    },
    {
      biomarker_name: "RV_VOLUME",
      ks_statistic: 0.08,
      p_value: 0.42,
      base_sample_size: 120,
      recent_sample_size: 40,
      drift_detected: false,
      skipped_reason: null,
    },
  ],
  biomarkers_skipped_reason: null,
  prediction: {
    psi: 0.05,
    base_sample_size: 120,
    recent_sample_size: 40,
    severity: "NONE",
    drift_detected: false,
    skipped_reason: null,
  },
};

describe("DriftTab", () => {
  it("shows a loading state while the drift report is being computed", () => {
    render(<DriftTab isLoading isError={false} />);
    expect(screen.getByText(/Computing drift/)).toBeInTheDocument();
  });

  it("shows an info alert (not an error) when the query failed, e.g. a 409 race", () => {
    render(<DriftTab isLoading={false} isError errorMessage="This model version is no longer in production." />);
    expect(screen.getByText("This model version is no longer in production.")).toBeInTheDocument();
  });

  it("renders the biomarker KS table and prediction PSI summary", () => {
    render(<DriftTab isLoading={false} isError={false} report={baseReport} />);
    expect(screen.getByText("LVEF")).toBeInTheDocument();
    expect(screen.getByText("Drift detected")).toBeInTheDocument();
    expect(screen.getByText("No drift")).toBeInTheDocument();
    expect(screen.getByText("PSI: 0.050")).toBeInTheDocument();
    expect(screen.getByText("Severity: NONE")).toBeInTheDocument();
  });

  it("shows the report-level skipped reason instead of an empty biomarker table", () => {
    const report: ModelDriftReport = {
      ...baseReport,
      biomarkers: [],
      biomarkers_skipped_reason: "No DatasetVersion available for this deep-learning model.",
    };
    render(<DriftTab isLoading={false} isError={false} report={report} />);
    expect(screen.getByText("No DatasetVersion available for this deep-learning model.")).toBeInTheDocument();
  });

  it("shows a per-biomarker skipped reason instead of a blank row", () => {
    const report: ModelDriftReport = {
      ...baseReport,
      biomarkers: [
        {
          biomarker_name: "LVEF",
          ks_statistic: null,
          p_value: null,
          base_sample_size: 3,
          recent_sample_size: 0,
          drift_detected: false,
          skipped_reason: "Not enough recent samples.",
        },
      ],
    };
    render(<DriftTab isLoading={false} isError={false} report={report} />);
    expect(screen.getByText(/Skipped: Not enough recent samples\./)).toBeInTheDocument();
  });
});
