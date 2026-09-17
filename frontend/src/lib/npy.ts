/**
 * Minimal client-side parser for the `.npy` v1.0 format `np.save` writes,
 * used by GradcamPanel to read the raw attribution array served by
 * `GET /analyses/{id}/gradcam` (`application/octet-stream`) without a new
 * backend endpoint or a bundled `.npy` library — see EPIC-14's "Contrato
 * técnico" for why parsing the header client-side is the chosen approach.
 */

const MAGIC_BYTES = [0x93, 0x4e, 0x55, 0x4d, 0x50, 0x59]; // "\x93NUMPY"

export interface ParsedNpyFloat32 {
  shape: number[];
  data: Float32Array;
}

/**
 * Parses a `.npy` v1.0 buffer holding a `float32` (`<f4`) array. Only v1.0
 * is supported — the format `np.save` writes by default for arrays this
 * size — and only `descr === "<f4"` is accepted: both are validated
 * explicitly and throw a clear error instead of silently assuming today's
 * format still holds if either ever changes.
 */
export function parseNpyFloat32(buffer: ArrayBuffer): ParsedNpyFloat32 {
  const bytes = new Uint8Array(buffer);
  if (bytes.length < 10 || !MAGIC_BYTES.every((b, i) => bytes[i] === b)) {
    throw new Error("Not a valid .npy file: magic string mismatch");
  }

  const majorVersion = bytes[6];
  const minorVersion = bytes[7];
  if (majorVersion !== 1 || minorVersion !== 0) {
    throw new Error(
      `Unsupported .npy version ${majorVersion}.${minorVersion}: only v1.0 is supported`,
    );
  }

  const view = new DataView(buffer);
  // v1.0 header length is a 2-byte little-endian uint16 (v2.0+ uses 4 bytes,
  // deliberately out of scope — see the module docstring).
  const headerLen = view.getUint16(8, true);
  const headerStart = 10;
  const headerEnd = headerStart + headerLen;
  if (bytes.length < headerEnd) {
    throw new Error("Malformed .npy file: header length exceeds buffer size");
  }
  const headerText = new TextDecoder("ascii").decode(bytes.subarray(headerStart, headerEnd));

  const descrMatch = headerText.match(/'descr'\s*:\s*'([^']+)'/);
  const descr = descrMatch?.[1];
  if (descr !== "<f4") {
    throw new Error(
      `Unsupported .npy dtype "${descr ?? "unknown"}": only "<f4" (little-endian float32) is supported`,
    );
  }

  const fortranMatch = headerText.match(/'fortran_order'\s*:\s*(True|False)/);
  if (fortranMatch?.[1] === "True") {
    throw new Error("Unsupported .npy layout: fortran_order=True is not supported");
  }

  const shapeMatch = headerText.match(/'shape'\s*:\s*\(([^)]*)\)/);
  if (!shapeMatch) {
    throw new Error("Malformed .npy header: could not find 'shape'");
  }
  const shape = shapeMatch[1]
    .split(",")
    .map((s) => s.trim())
    .filter((s) => s.length > 0)
    .map((s) => Number.parseInt(s, 10));

  // Slicing (rather than viewing the original buffer at `headerEnd`) sidesteps
  // Float32Array's requirement that its byte offset be a multiple of 4 — the
  // .npy spec pads the header to a 64-byte boundary so this holds in
  // practice, but slicing makes that assumption unnecessary to rely on.
  const data = new Float32Array(buffer.slice(headerEnd));

  return { shape, data };
}
