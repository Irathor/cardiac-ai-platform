import { useEffect, useRef, useState } from "react";

import { tokens } from "../theme";

// Tip of the arrow in the SVG's own coordinate space — the mouse position
// gets offset by this so the tip (not the element's bounding-box corner)
// lands exactly under the pointer, matching how a native cursor's hotspot
// works.
const TIP_X = 1;
const TIP_Y = 1;

/**
 * Replaces the native pointer with a normal arrow-shaped cursor, recolored
 * to the palette's pale bioluminescent green with a bright outline and a
 * rhythmic glow. Tracks the mouse via a direct DOM write (not React state)
 * so it doesn't cause a re-render on every mousemove. Only mounts on
 * devices with a real mouse (`hover: hover` + `pointer: fine`) — touch
 * devices keep their native pointer untouched, since there's nothing to
 * replace there.
 */
export function CustomCursor() {
  const cursorRef = useRef<SVGSVGElement>(null);
  const [enabled] = useState(
    () =>
      typeof window !== "undefined" &&
      typeof window.matchMedia === "function" &&
      window.matchMedia("(hover: hover) and (pointer: fine)").matches,
  );

  useEffect(() => {
    if (!enabled) return;
    const cursor = cursorRef.current;
    if (!cursor) return;

    function onMove(e: MouseEvent) {
      cursor!.style.transform = `translate3d(${e.clientX - TIP_X}px, ${e.clientY - TIP_Y}px, 0)`;
    }
    function onLeave() {
      cursor!.style.opacity = "0";
    }
    function onEnter() {
      cursor!.style.opacity = "1";
    }

    document.body.classList.add("custom-cursor-active");
    window.addEventListener("mousemove", onMove);
    document.documentElement.addEventListener("mouseleave", onLeave);
    document.documentElement.addEventListener("mouseenter", onEnter);

    return () => {
      document.body.classList.remove("custom-cursor-active");
      window.removeEventListener("mousemove", onMove);
      document.documentElement.removeEventListener("mouseleave", onLeave);
      document.documentElement.removeEventListener("mouseenter", onEnter);
    };
  }, [enabled]);

  if (!enabled) return null;
  return (
    <svg
      ref={cursorRef}
      className="custom-cursor"
      width="14"
      height="16"
      viewBox="0 0 14 16"
      aria-hidden="true"
      focusable="false"
    >
      <path
        d="M1 1 L1 12 L4.5 9.3 L6.2 14 L7.8 13.4 L6.1 8.7 L12 8.7 Z"
        fill={tokens.cyanDark}
        stroke={tokens.textPrimary}
        strokeWidth="1"
        strokeLinejoin="round"
      />
    </svg>
  );
}
