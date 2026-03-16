'use client'

import dynamic from 'next/dynamic'
import { useState, useCallback } from 'react'
import { ChevronLeft, ChevronRight } from 'lucide-react'
import { useQAStore } from '@/store/useQAStore'
import { usePdfDimensions } from '@/hooks/usePdfDimensions'

// Lazy import react-pdf to avoid SSR DOMMatrix error
const Document = dynamic(
  () => import('react-pdf').then((mod) => mod.Document),
  { ssr: false }
)
const Page = dynamic(
  () => import('react-pdf').then((mod) => mod.Page),
  { ssr: false }
)

// Set worker source (client-only)
if (typeof window !== 'undefined') {
  import('react-pdf').then((mod) => {
    mod.pdfjs.GlobalWorkerOptions.workerSrc = `//unpkg.com/pdfjs-dist@${mod.pdfjs.version}/build/pdf.worker.min.mjs`
  })
}

const PDF_WIDTH = 520

interface PdfPreviewProps {
  onPageDimensions?: (dims: { width: number; height: number }) => void
  overlay?: React.ReactNode
}

export default function PdfPreview({
  onPageDimensions,
  overlay,
}: PdfPreviewProps) {
  const { pdfUrl, pageCount, setPageCount } = useQAStore()
  const [currentPage, setCurrentPage] = useState(1)
  const { dimensions, containerRef } = usePdfDimensions()

  const onDocumentLoadSuccess = useCallback(
    (pdf: { numPages: number }) => {
      setPageCount(pdf.numPages)
    },
    [setPageCount]
  )

  // Forward dimensions to parent when they change
  const handleContainerRef = useCallback(
    (node: HTMLDivElement | null) => {
      containerRef(node)
    },
    [containerRef]
  )

  // Notify parent of dimension changes
  if (dimensions.height > 0 && onPageDimensions) {
    queueMicrotask(() => onPageDimensions(dimensions))
  }

  if (!pdfUrl) return null

  return (
    <div className="flex flex-col items-center gap-3">
      {/* PDF page container */}
      <div className="relative rounded-lg overflow-hidden bg-white/[0.02]">
        <div ref={handleContainerRef} className="relative">
          <Document
            file={pdfUrl}
            onLoadSuccess={onDocumentLoadSuccess}
            loading={
              <div className="flex items-center justify-center h-[600px] w-[520px]">
                <div className="h-6 w-6 animate-spin rounded-full border-2 border-white/20 border-t-blue-400" />
              </div>
            }
          >
            <Page
              pageNumber={currentPage}
              width={PDF_WIDTH}
              renderAnnotationLayer={false}
              renderTextLayer={false}
            />
          </Document>

          {/* Overlay (crop lines) */}
          {overlay}
        </div>
      </div>

      {/* Page navigation */}
      {pageCount > 1 && (
        <div className="flex items-center gap-3">
          <button
            onClick={() => setCurrentPage((p) => Math.max(1, p - 1))}
            disabled={currentPage <= 1}
            className="
              flex h-8 w-8 items-center justify-center rounded-lg
              bg-white/[0.06] text-white/60 hover:bg-white/[0.1] hover:text-white
              disabled:opacity-30 disabled:cursor-not-allowed
              transition-colors cursor-pointer
            "
            aria-label="Previous page"
          >
            <ChevronLeft className="h-4 w-4" />
          </button>

          <span className="text-xs text-white/40 tabular-nums min-w-[80px] text-center">
            Page {currentPage} of {pageCount}
          </span>

          <button
            onClick={() => setCurrentPage((p) => Math.min(pageCount, p + 1))}
            disabled={currentPage >= pageCount}
            className="
              flex h-8 w-8 items-center justify-center rounded-lg
              bg-white/[0.06] text-white/60 hover:bg-white/[0.1] hover:text-white
              disabled:opacity-30 disabled:cursor-not-allowed
              transition-colors cursor-pointer
            "
            aria-label="Next page"
          >
            <ChevronRight className="h-4 w-4" />
          </button>
        </div>
      )}
    </div>
  )
}
