import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { ResearchDisclaimerBanner } from "../src/components/ResearchDisclaimerBanner";

describe("ResearchDisclaimerBanner", () => {
  it("always shows the mandatory research-only disclaimer text", () => {
    render(<ResearchDisclaimerBanner />);
    expect(
      screen.getByText(
        "Research prototype only. Not validated for clinical diagnosis or treatment decisions.",
      ),
    ).toBeInTheDocument();
  });
});
