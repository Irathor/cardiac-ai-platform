import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import * as analysisApi from "../src/api/analysis";

vi.mock("../src/api/analysis");

import i18n from "../src/i18n";
import { LlmExplanationPanel } from "../src/components/LlmExplanationPanel";

const mockedAnalysis = vi.mocked(analysisApi);

describe("LlmExplanationPanel", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  afterEach(async () => {
    await i18n.changeLanguage("en");
  });

  it("shows the mandatory suggestion disclaimer and the generated text on click", async () => {
    mockedAnalysis.fetchOrGenerateLlmExplanation.mockResolvedValue({
      explanation: "El modelo predice DILATED_CARDIOMYOPATHY con confianza moderada.",
      error: null,
    });

    render(
      <LlmExplanationPanel
        analysisId="analysis-1"
        token="test-token"
        explanationAvailable={false}
        explanationError={null}
      />,
    );

    await userEvent.click(screen.getByRole("button", { name: "Generate explanation" }));

    expect(await screen.findByText(/DILATED_CARDIOMYOPATHY con confianza moderada/)).toBeInTheDocument();
    expect(screen.getByText(/this is not a diagnosis/)).toBeInTheDocument();
    expect(mockedAnalysis.fetchOrGenerateLlmExplanation).toHaveBeenCalledWith(
      "analysis-1",
      "test-token",
      false,
      "en",
    );
  });

  it("shows the honest error instead of a fabricated explanation when Ollama is unreachable", async () => {
    mockedAnalysis.fetchOrGenerateLlmExplanation.mockResolvedValue({
      explanation: null,
      error: "could not reach Ollama at http://host.docker.internal:11434",
    });

    render(
      <LlmExplanationPanel
        analysisId="analysis-2"
        token="test-token"
        explanationAvailable={false}
        explanationError={null}
      />,
    );

    await userEvent.click(screen.getByRole("button", { name: "Generate explanation" }));

    expect(await screen.findByText(/could not reach Ollama/)).toBeInTheDocument();
  });

  it("regenerating calls the API with force=true", async () => {
    mockedAnalysis.fetchOrGenerateLlmExplanation.mockResolvedValue({
      explanation: "versión inicial",
      error: null,
    });

    render(
      <LlmExplanationPanel
        analysisId="analysis-3"
        token="test-token"
        explanationAvailable={true}
        explanationError={null}
      />,
    );

    await userEvent.click(screen.getByRole("button", { name: "View explanation" }));
    await screen.findByText("versión inicial");

    mockedAnalysis.fetchOrGenerateLlmExplanation.mockResolvedValue({
      explanation: "versión regenerada",
      error: null,
    });
    await userEvent.click(screen.getByRole("button", { name: "Regenerate" }));

    expect(await screen.findByText("versión regenerada")).toBeInTheDocument();
    expect(mockedAnalysis.fetchOrGenerateLlmExplanation).toHaveBeenLastCalledWith(
      "analysis-3",
      "test-token",
      true,
      "en",
    );
  });

  it("re-fetches in the new language when the UI language changes while open", async () => {
    mockedAnalysis.fetchOrGenerateLlmExplanation.mockResolvedValue({
      explanation: "In English.",
      error: null,
    });

    render(
      <LlmExplanationPanel
        analysisId="analysis-4"
        token="test-token"
        explanationAvailable={false}
        explanationError={null}
      />,
    );

    await userEvent.click(screen.getByRole("button", { name: "Generate explanation" }));
    await screen.findByText("In English.");

    mockedAnalysis.fetchOrGenerateLlmExplanation.mockResolvedValue({
      explanation: "En español.",
      error: null,
    });
    await i18n.changeLanguage("es");

    expect(await screen.findByText("En español.")).toBeInTheDocument();
    expect(mockedAnalysis.fetchOrGenerateLlmExplanation).toHaveBeenLastCalledWith(
      "analysis-4",
      "test-token",
      false,
      "es",
    );
  });
});
