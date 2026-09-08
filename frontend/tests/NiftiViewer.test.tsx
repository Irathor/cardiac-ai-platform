import { render } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

const attachToCanvas = vi.fn();
const loadVolumes = vi.fn();

vi.mock("@niivue/niivue", () => ({
  // jsdom has no WebGL context, so the real Niivue can't run in tests —
  // this verifies our wiring (which volumes get passed, in what order,
  // with what colormap) rather than actual rendering.
  Niivue: vi.fn().mockImplementation(() => ({
    attachToCanvas,
    loadVolumes,
  })),
}));

import { NiftiViewer } from "../src/components/NiftiViewer";

describe("NiftiViewer", () => {
  beforeEach(() => {
    attachToCanvas.mockClear();
    loadVolumes.mockClear();
    vi.stubGlobal("URL", {
      ...URL,
      createObjectURL: vi.fn(() => "blob:mock/x"),
      revokeObjectURL: vi.fn(),
    });
  });

  it("loads only the series volume in grayscale when there is no mask", () => {
    const seriesBlob = new Blob(["series-bytes"]);
    render(<NiftiViewer seriesBlob={seriesBlob} />);

    expect(attachToCanvas).toHaveBeenCalledTimes(1);
    expect(loadVolumes).toHaveBeenCalledTimes(1);
    const volumes = loadVolumes.mock.calls[0][0];
    expect(volumes).toHaveLength(1);
    expect(volumes[0]).toMatchObject({ colormap: "gray", name: "series.nii.gz" });
  });

  it("adds the mask as a translucent red overlay when provided", () => {
    const seriesBlob = new Blob(["series-bytes"]);
    const maskBlob = new Blob(["mask-bytes"]);
    render(<NiftiViewer seriesBlob={seriesBlob} maskBlob={maskBlob} maskFileName="mask.nii.gz" />);

    const volumes = loadVolumes.mock.calls[0][0];
    expect(volumes).toHaveLength(2);
    expect(volumes[1]).toMatchObject({ colormap: "red", opacity: 0.5, name: "mask.nii.gz" });
  });
});
