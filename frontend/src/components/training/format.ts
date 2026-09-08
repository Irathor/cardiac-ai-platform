const NOT_AVAILABLE = "not available";

/** Never render undefined/NaN as if it were a real value — always fall back
 * to an explicit label so a missing metric can't be misread as zero. */
export function fmtNumber(value: number | null | undefined, digits = 3): string {
  if (value === null || value === undefined || Number.isNaN(value)) return NOT_AVAILABLE;
  return value.toFixed(digits);
}

export function fmtPercent(value: number | null | undefined, digits = 1): string {
  if (value === null || value === undefined || Number.isNaN(value)) return NOT_AVAILABLE;
  return `${(value * 100).toFixed(digits)}%`;
}

export function fmtCi(ci: [number, number] | null | undefined, digits = 3): string {
  if (!ci) return NOT_AVAILABLE;
  return `[${ci[0].toFixed(digits)}, ${ci[1].toFixed(digits)}]`;
}

export const NOT_APPLICABLE = "not applicable to this model";
export { NOT_AVAILABLE };
