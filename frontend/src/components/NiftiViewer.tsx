import { Niivue } from "@niivue/niivue";
import { useEffect, useRef } from "react";

export interface NiftiViewerProps {
  /** Raw NIfTI bytes for the underlying cine/anatomical series. */
  seriesBlob: Blob;
  /** Raw NIfTI bytes for a segmentation mask, rendered as a translucent overlay. */
  maskBlob?: Blob | null;
  seriesFileName?: string;
  maskFileName?: string;
}

/**
 * Renders one NIfTI volume, optionally overlaid with a segmentation mask, via
 * Niivue. Bytes are fetched through the backend API (see api/imaging.ts) —
 * per docs/architecture.md the frontend never talks to MinIO directly, so
 * this component only ever receives already-downloaded blobs, never a MinIO
 * URL, and turns them into short-lived object URLs purely so Niivue (which
 * loads by URL) can read them.
 */
export function NiftiViewer({
  seriesBlob,
  maskBlob,
  seriesFileName = "series.nii.gz",
  maskFileName = "mask.nii.gz",
}: NiftiViewerProps) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const niivueRef = useRef<Niivue | null>(null);

  useEffect(() => {
    if (!canvasRef.current) return;

    const nv = niivueRef.current ?? new Niivue({ backColor: [0, 0, 0, 1] });
    niivueRef.current = nv;
    nv.attachToCanvas(canvasRef.current);

    const seriesUrl = URL.createObjectURL(seriesBlob);
    const maskUrl = maskBlob ? URL.createObjectURL(maskBlob) : null;

    const volumes: { url: string; name: string; colormap: string; opacity?: number }[] = [
      { url: seriesUrl, name: seriesFileName, colormap: "gray" },
    ];
    if (maskUrl) {
      volumes.push({ url: maskUrl, name: maskFileName, colormap: "red", opacity: 0.5 });
    }
    void nv.loadVolumes(volumes);

    return () => {
      URL.revokeObjectURL(seriesUrl);
      if (maskUrl) URL.revokeObjectURL(maskUrl);
    };
  }, [seriesBlob, maskBlob, seriesFileName, maskFileName]);

  return <canvas ref={canvasRef} style={{ width: "100%", height: "100%", display: "block" }} />;
}
