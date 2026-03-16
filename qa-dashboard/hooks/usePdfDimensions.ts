/**
 * Hook to track rendered PDF page dimensions.
 * Uses ResizeObserver for live updates if user resizes the browser.
 */

'use client'

import { useCallback, useEffect, useRef, useState } from 'react'

interface PdfDimensions {
  width: number
  height: number
}

export function usePdfDimensions() {
  const [dimensions, setDimensions] = useState<PdfDimensions>({
    width: 0,
    height: 0,
  })

  const containerRef = useRef<HTMLDivElement | null>(null)
  const observerRef = useRef<ResizeObserver | null>(null)

  const attachRef = useCallback((node: HTMLDivElement | null) => {
    // Clean up previous observer
    if (observerRef.current) {
      observerRef.current.disconnect()
      observerRef.current = null
    }

    if (node) {
      containerRef.current = node

      observerRef.current = new ResizeObserver((entries) => {
        for (const entry of entries) {
          const { width, height } = entry.contentRect
          if (width > 0 && height > 0) {
            setDimensions({ width, height })
          }
        }
      })

      observerRef.current.observe(node)
    }
  }, [])

  useEffect(() => {
    return () => {
      if (observerRef.current) {
        observerRef.current.disconnect()
      }
    }
  }, [])

  return { dimensions, containerRef: attachRef }
}
