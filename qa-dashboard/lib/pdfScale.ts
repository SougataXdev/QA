/**
 * Crop coordinate translation — pixel ↔ fraction.
 *
 * The Python engine expects crop values as 0.0–1.0 fractions of page height.
 * This module converts between browser pixel coordinates (dragged crop lines)
 * and those fractions.
 *
 * CRITICAL: Call pixelToFraction at drag-end time, not at submit time.
 * The rendered page height at drag-end is the correct denominator.
 */

/**
 * Convert a browser pixel Y coordinate to a 0.0–1.0 fraction of page height.
 * Clamps to [0, 1].
 */
export function pixelToFraction(
  pixelY: number,
  renderedPageHeightPx: number
): number {
  if (renderedPageHeightPx <= 0) return 0
  const clamped = Math.max(0, Math.min(pixelY, renderedPageHeightPx))
  return clamped / renderedPageHeightPx
}

/**
 * Convert a 0.0–1.0 fraction back to pixel coordinates for rendering.
 */
export function fractionToPixel(
  fraction: number,
  renderedPageHeightPx: number
): number {
  return fraction * renderedPageHeightPx
}
