"use client";

import { motion } from "motion/react";
import { useCallback, useRef, useState, useEffect } from "react";
import { fractionToPixel, pixelToFraction } from "@/lib/pdfScale";

interface CropOverlayProps {
  containerHeightPx: number;
  initialTop: number; // fraction 0.0–1.0
  initialBottom: number; // fraction 0.0–1.0
  initialLeft: number; // fraction 0.0–1.0
  initialRight: number; // fraction 0.0–1.0
  onCropChange: (
    top: number,
    bottom: number,
    left: number,
    right: number,
  ) => void;
}

const MIN_GAP_PX = 50;

export default function CropOverlay({
  containerHeightPx,
  initialTop,
  initialBottom,
  initialLeft,
  initialRight,
  onCropChange,
}: CropOverlayProps) {
  const [topY, setTopY] = useState(() =>
    fractionToPixel(initialTop, containerHeightPx),
  );
  const [bottomY, setBottomY] = useState(() =>
    fractionToPixel(initialBottom, containerHeightPx),
  );
  // Assuming width scales proportionally or is managed similarly; we need containerWidthPx really, but let's see how PDF scales.
  // Wait, fractionToPixel only needs the dimension size.
  // The overlay currently only knows containerHeightPx.
  const [containerWidthPx, setContainerWidthPx] = useState(0);

  const [leftX, setLeftX] = useState(() => 0); // We'll initialize properly when width is known
  const [rightX, setRightX] = useState(() => 0);

  const [dragging, setDragging] = useState<
    "top" | "bottom" | "left" | "right" | null
  >(null);
  const containerRef = useRef<HTMLDivElement>(null);

  // Sync if container dimensions change
  const prevHeightRef = useRef(containerHeightPx);
  if (containerHeightPx !== prevHeightRef.current && containerHeightPx > 0) {
    const topFrac = topY / (prevHeightRef.current || 1);
    const bottomFrac = bottomY / (prevHeightRef.current || 1);
    setTopY(topFrac * containerHeightPx);
    setBottomY(bottomFrac * containerHeightPx);
    prevHeightRef.current = containerHeightPx;
  }

  // We need to sync width too, but React-PDF doesn't give us width explicitly in the same way.
  // We can derive it from the container ref.
  const prevWidthRef = useRef(containerWidthPx);
  if (containerWidthPx !== prevWidthRef.current && containerWidthPx > 0) {
    // If it's the first time we're getting width, initialize from props
    if (prevWidthRef.current === 0) {
      setLeftX(fractionToPixel(initialLeft, containerWidthPx));
      setRightX(fractionToPixel(initialRight, containerWidthPx));
    } else {
      // Otherwise scale existing values
      const leftFrac = leftX / prevWidthRef.current;
      const rightFrac = rightX / prevWidthRef.current;
      setLeftX(leftFrac * containerWidthPx);
      setRightX(rightFrac * containerWidthPx);
    }
    prevWidthRef.current = containerWidthPx;
  }

  // Effect to observe container width
  useEffect(() => {
    if (!containerRef.current) return;
    const observer = new ResizeObserver((entries) => {
      for (const entry of entries) {
        setContainerWidthPx(entry.contentRect.width);
      }
    });
    observer.observe(containerRef.current);
    return () => observer.disconnect();
  }, []);

  const handlePointerDown = useCallback(
    (which: "top" | "bottom" | "left" | "right", e: React.PointerEvent) => {
      e.preventDefault();
      e.stopPropagation();
      (e.target as HTMLElement).setPointerCapture(e.pointerId);
      setDragging(which);
    },
    [],
  );

  const handlePointerMove = useCallback(
    (e: React.PointerEvent) => {
      if (!dragging || !containerRef.current) return;
      const rect = containerRef.current.getBoundingClientRect();

      if (dragging === "top" || dragging === "bottom") {
        const y = e.clientY - rect.top;
        if (dragging === "top") {
          const clamped = Math.max(0, Math.min(y, bottomY - MIN_GAP_PX));
          setTopY(clamped);
        } else {
          const clamped = Math.min(
            containerHeightPx,
            Math.max(y, topY + MIN_GAP_PX),
          );
          setBottomY(clamped);
        }
      } else {
        const x = e.clientX - rect.left;
        if (dragging === "left") {
          const clamped = Math.max(0, Math.min(x, rightX - MIN_GAP_PX));
          setLeftX(clamped);
        } else {
          const clamped = Math.min(
            containerWidthPx,
            Math.max(x, leftX + MIN_GAP_PX),
          );
          setRightX(clamped);
        }
      }
    },
    [
      dragging,
      topY,
      bottomY,
      leftX,
      rightX,
      containerHeightPx,
      containerWidthPx,
    ],
  );

  const handlePointerUp = useCallback(() => {
    if (!dragging) return;
    setDragging(null);

    const topFrac = pixelToFraction(topY, containerHeightPx);
    const bottomFrac = pixelToFraction(bottomY, containerHeightPx);
    const leftFrac =
      containerWidthPx > 0 ? pixelToFraction(leftX, containerWidthPx) : 0;
    const rightFrac =
      containerWidthPx > 0 ? pixelToFraction(rightX, containerWidthPx) : 1;

    onCropChange(topFrac, bottomFrac, leftFrac, rightFrac);
  }, [
    dragging,
    topY,
    bottomY,
    leftX,
    rightX,
    containerHeightPx,
    containerWidthPx,
    onCropChange,
  ]);

  if (containerHeightPx <= 0) return null;

  const topPercent = ((topY / containerHeightPx) * 100).toFixed(1);
  const bottomPercent = ((bottomY / containerHeightPx) * 100).toFixed(1);
  const leftPercent =
    containerWidthPx > 0
      ? ((leftX / containerWidthPx) * 100).toFixed(1)
      : "0.0";
  const rightPercent =
    containerWidthPx > 0
      ? ((rightX / containerWidthPx) * 100).toFixed(1)
      : "100.0";

  return (
    <div
      ref={containerRef}
      className="absolute inset-0 z-10"
      onPointerMove={handlePointerMove}
      onPointerUp={handlePointerUp}
      style={{ touchAction: "none" }}
    >
      {/* Top dark overlay (header zone) */}
      <div
        className="absolute left-0 right-0 top-0 bg-black/45 transition-opacity pointer-events-none"
        style={{ height: topY }}
      />

      {/* Bottom dark overlay (footer zone) */}
      <div
        className="absolute left-0 right-0 bottom-0 bg-black/45 transition-opacity pointer-events-none"
        style={{ height: containerHeightPx - bottomY }}
      />

      {/* Left dark overlay (sidebar zone) */}
      <div
        className="absolute top-0 bottom-0 left-0 bg-black/45 transition-opacity pointer-events-none"
        style={{ width: leftX, top: topY, height: bottomY - topY }}
      />

      {/* Right dark overlay (sidebar zone) */}
      <div
        className="absolute top-0 bottom-0 right-0 bg-black/45 transition-opacity pointer-events-none"
        style={{
          width: containerWidthPx - rightX,
          top: topY,
          height: bottomY - topY,
          left: rightX,
        }}
      />

      {/* Active region tint */}
      <div
        className="absolute bg-blue-500/[0.06] pointer-events-none"
        style={{
          top: topY,
          height: bottomY - topY,
          left: leftX,
          width: rightX - leftX,
        }}
      />

      {/* ─── Top crop line ─── */}
      <motion.div
        className="absolute left-0 right-0 z-20 group"
        style={{ top: topY - 1, left: leftX, width: rightX - leftX }}
        animate={
          dragging === "top"
            ? { boxShadow: "0 0 0 2px rgba(59,130,246,0.6)" }
            : { boxShadow: "0 0 0 0px transparent" }
        }
      >
        <div className="h-[2px] bg-blue-500/60" />
        {/* Handle */}
        <div
          onPointerDown={(e) => handlePointerDown("top", e)}
          className="
            absolute left-1/2 -translate-x-1/2 top-0
            flex items-center gap-1.5 px-3 py-1
            rounded-b-full cursor-ns-resize select-none
            bg-blue-500/20 backdrop-blur-sm border border-blue-500/30
            hover:bg-blue-500/30 transition-colors
          "
        >
          <div className="flex flex-col gap-[2px]">
            <div className="w-3 h-[1px] bg-blue-400/60" />
            <div className="w-3 h-[1px] bg-blue-400/60" />
          </div>
          <span className="text-[10px] font-medium text-blue-300 tabular-nums">
            {topPercent}%
          </span>
        </div>
      </motion.div>

      {/* ─── Bottom crop line ─── */}
      <motion.div
        className="absolute left-0 right-0 z-20 group"
        style={{ top: bottomY - 1, left: leftX, width: rightX - leftX }}
        animate={
          dragging === "bottom"
            ? { boxShadow: "0 0 0 2px rgba(59,130,246,0.6)" }
            : { boxShadow: "0 0 0 0px transparent" }
        }
      >
        <div className="h-[2px] bg-blue-500/60" />
        {/* Handle */}
        <div
          onPointerDown={(e) => handlePointerDown("bottom", e)}
          className="
            absolute left-1/2 -translate-x-1/2 bottom-0
            flex items-center gap-1.5 px-3 py-1
            rounded-t-full cursor-ns-resize select-none
            bg-blue-500/20 backdrop-blur-sm border border-blue-500/30
            hover:bg-blue-500/30 transition-colors
          "
        >
          <div className="flex flex-col gap-[2px]">
            <div className="w-3 h-[1px] bg-blue-400/60" />
            <div className="w-3 h-[1px] bg-blue-400/60" />
          </div>
          <span className="text-[10px] font-medium text-blue-300 tabular-nums">
            {bottomPercent}%
          </span>
        </div>
      </motion.div>
      {/* ─── Left crop line ─── */}
      <motion.div
        className="absolute top-0 bottom-0 z-20 group"
        style={{ left: leftX - 1, top: topY, height: bottomY - topY }}
        animate={
          dragging === "left"
            ? { boxShadow: "0 0 0 2px rgba(59,130,246,0.6)" }
            : { boxShadow: "0 0 0 0px transparent" }
        }
      >
        <div className="w-[2px] h-full bg-blue-500/60" />
        {/* Handle */}
        <div
          onPointerDown={(e) => handlePointerDown("left", e)}
          className="
            absolute top-1/2 -translate-y-1/2 left-0
            flex flex-col items-center gap-1.5 px-1 py-3
            rounded-r-full cursor-ew-resize select-none
            bg-blue-500/20 backdrop-blur-sm border border-blue-500/30
            hover:bg-blue-500/30 transition-colors
          "
        >
          <div className="flex flex-row gap-[2px]">
            <div className="h-3 w-px bg-blue-400/60" />
            <div className="h-3 w-px bg-blue-400/60" />
          </div>
          <span
            className="text-[10px] font-medium text-blue-300 tabular-nums"
            style={{ writingMode: "vertical-rl", transform: "rotate(180deg)" }}
          >
            {leftPercent}%
          </span>
        </div>
      </motion.div>

      {/* ─── Right crop line ─── */}
      <motion.div
        className="absolute top-0 bottom-0 z-20 group"
        style={{ left: rightX - 1, top: topY, height: bottomY - topY }}
        animate={
          dragging === "right"
            ? { boxShadow: "0 0 0 2px rgba(59,130,246,0.6)" }
            : { boxShadow: "0 0 0 0px transparent" }
        }
      >
        <div className="w-[2px] h-full bg-blue-500/60" />
        {/* Handle */}
        <div
          onPointerDown={(e) => handlePointerDown("right", e)}
          className="
            absolute top-1/2 -translate-y-1/2 right-0
            flex flex-col items-center gap-1.5 px-1 py-3
            rounded-l-full cursor-ew-resize select-none
            bg-blue-500/20 backdrop-blur-sm border border-blue-500/30
            hover:bg-blue-500/30 transition-colors
          "
        >
          <div className="flex flex-row gap-[2px]">
            <div className="h-3 w-px bg-blue-400/60" />
            <div className="h-3 w-px bg-blue-400/60" />
          </div>
          <span
            className="text-[10px] font-medium text-blue-300 tabular-nums"
            style={{ writingMode: "vertical-rl", transform: "rotate(180deg)" }}
          >
            {rightPercent}%
          </span>
        </div>
      </motion.div>
    </div>
  );
}
