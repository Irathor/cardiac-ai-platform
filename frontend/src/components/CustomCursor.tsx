import { useEffect, useRef, useState } from "react";

/**
 * Replaces the native pointer with a small bioluminescent dot that tracks
 * the mouse via direct DOM writes (not React state) so it doesn't cause a
 * re-render on every mousemove. Only mounts on devices with a real mouse
 * (`hover: hover` + `pointer: fine`) — touch devices keep their native
 * pointer untouched, since there's nothing to replace there.
 */
export function CustomCursor() {
  const dotRef = useRef<HTMLDivElement>(null);
  const [enabled] = useState(
    () => typeof window !== "undefined" && typeof window.matchMedia === "function"
      && window.matchMedia("(hover: hover) and (pointer: fine)").matches,
  );

  useEffect(() => {
    if (!enabled) return;
    const dot = dotRef.current;
    if (!dot) return;

    function onMove(e: MouseEvent) {
      dot!.style.transform = `translate3d(${e.clientX}px, ${e.clientY}px, 0) translate(-50%, -50%)`;
    }
    function onLeave() {
      dot!.style.opacity = "0";
    }
    function onEnter() {
      dot!.style.opacity = "1";
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
  return <div ref={dotRef} className="custom-cursor" aria-hidden="true" />;
}
