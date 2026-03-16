'use client'

import { AnimatePresence, motion } from 'motion/react'
import { useCallback, useState } from 'react'
import {
  Play,
  RotateCcw,
  Download,
  Crop,
  AlertCircle,
  CheckCircle2,
} from 'lucide-react'

import { useQAStore } from '@/store/useQAStore'
import { useJobPoller } from '@/hooks/useJobPoller'
import { submitJob } from '@/lib/api'

import DropZone from '@/components/upload/DropZone'
import UrlInput from '@/components/upload/UrlInput'
import PdfPreview from '@/components/pdf/PdfPreview'
import CropOverlay from '@/components/pdf/CropOverlay'
import PageRangeSelector from '@/components/pdf/PageRangeSelector'
import JobProgress from '@/components/progress/JobProgress'
import ReportSummary from '@/components/report/ReportSummary'
import IssueCard from '@/components/report/IssueCard'
import Badge from '@/components/ui/Badge'
import Button from '@/components/ui/Button'

import type { QAFilterOption } from '@/lib/types'

// ─── Helpers ────────────────────────────────────────

function isValidUrl(str: string): boolean {
  try {
    const url = new URL(str)
    return url.protocol === 'http:' || url.protocol === 'https:'
  } catch {
    return false
  }
}

// ─── Main page ──────────────────────────────────────

export default function DashboardPage() {
  const store = useQAStore()
  const {
    pdfFile,
    targetUrl,
    pageCount,
    pageRangeStart,
    pageRangeEnd,
    cropTop,
    cropBottom,
    cropLeft,
    cropRight,
    isCropActive,
    jobId,
    jobStatus,
    results,
    activeFilter,
    setPdf,
    setCrop,
    toggleCrop,
    setJobId,
    setFilter,
    reset,
  } = store

  useJobPoller(jobId)

  const [submitting, setSubmitting] = useState(false)
  const [pdfPageHeight, setPdfPageHeight] = useState(0)

  // ─── Determine view state ──

  type ViewState = 'UPLOAD' | 'PROCESSING' | 'RESULTS'

  const getViewState = (): ViewState => {
    if (results && (jobStatus === 'COMPLETE' || jobStatus === 'FAILED')) {
      return 'RESULTS'
    }
    if (jobId && (jobStatus === 'QUEUED' || jobStatus === 'RUNNING')) {
      return 'PROCESSING'
    }
    return 'UPLOAD'
  }

  const viewState = getViewState()
  const canSubmit = pdfFile && isValidUrl(targetUrl) && !submitting

  // ─── Submit handler ──

  const handleSubmit = useCallback(async () => {
    if (!pdfFile || !isValidUrl(targetUrl)) return
    setSubmitting(true)
    try {
      const resp = await submitJob(pdfFile, {
        url: targetUrl,
        crop_top: cropTop,
        crop_bottom: cropBottom,
        crop_left: cropLeft,
        crop_right: cropRight,
        page_range_start: pageRangeStart - 1,
        page_range_end: pageRangeEnd === -1 ? -1 : pageRangeEnd,
      })
      setJobId(resp.job_id)
    } catch (err) {
      console.error('Submit failed:', err)
    } finally {
      setSubmitting(false)
    }
  }, [pdfFile, targetUrl, cropTop, cropBottom, cropLeft, cropRight, pageRangeStart, pageRangeEnd, setJobId])

  // ─── Download handler ──

  const handleDownload = useCallback(() => {
    if (!results) return
    const blob = new Blob([JSON.stringify(results, null, 2)], {
      type: 'application/json',
    })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `qa-report-${new Date().toISOString().slice(0, 10)}.json`
    a.click()
    URL.revokeObjectURL(url)
  }, [results])

  // ─── Filter issues ──

  const filteredIssues =
    results?.issues?.filter(
      (i) => activeFilter === 'ALL' || i.type === activeFilter
    ) ?? []

  // ─── Overall status badge ──

  const overallSeverity =
    results?.overall === 'all_clear'
      ? 'all_clear' as const
      : results?.overall === 'minor_issues'
        ? 'minor' as const
        : 'must_fix' as const

  // ─── Render ──

  return (
    <main className="min-h-screen">
      <AnimatePresence mode="wait">
        {/* ════════════════════════════════════════════ */}
        {/*  STATE 1 — UPLOAD VIEW                      */}
        {/* ════════════════════════════════════════════ */}
        {viewState === 'UPLOAD' && (
          <motion.div
            key="upload"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0, y: -20 }}
            transition={{ duration: 0.3 }}
            className="max-w-5xl mx-auto px-6 py-16"
          >
            {/* Header */}
            <div className="mb-12">
              <motion.h1
                initial={{ opacity: 0, y: 10 }}
                animate={{ opacity: 1, y: 0 }}
                className="text-3xl font-light text-white tracking-tight"
              >
                QA Analysis
              </motion.h1>
              <motion.p
                initial={{ opacity: 0, y: 10 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ delay: 0.05 }}
                className="text-sm text-white/30 mt-2"
              >
                Upload a PDF and provide a URL to compare content
              </motion.p>
            </div>

            {/* Two-column layout */}
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-8">
              {/* Left column — PDF upload + settings */}
              <div className="space-y-4">
                <DropZone />
                {pageCount > 0 && <PageRangeSelector />}

                {/* Crop toggle */}
                {pdfFile && (
                  <motion.div
                    initial={{ opacity: 0 }}
                    animate={{ opacity: 1 }}
                    transition={{ delay: 0.1 }}
                  >
                    <button
                      onClick={toggleCrop}
                      className={`
                        flex items-center gap-2 px-3 py-2 rounded-lg
                        text-xs font-medium transition-colors cursor-pointer
                        ${
                          isCropActive
                            ? 'bg-blue-500/10 text-blue-400 border border-blue-500/20'
                            : 'bg-white/[0.04] text-white/40 border border-white/[0.06] hover:text-white/60'
                        }
                      `}
                    >
                      <Crop className="h-3.5 w-3.5" />
                      {isCropActive ? 'Hide Crop Tool' : 'Configure Crop'}
                    </button>
                  </motion.div>
                )}
              </div>

              {/* Right column — URL + Submit */}
              <div className="space-y-6">
                <UrlInput />

                <Button
                  variant="primary"
                  size="lg"
                  pulse={!!canSubmit}
                  disabled={!canSubmit}
                  loading={submitting}
                  onClick={handleSubmit}
                  className="w-full"
                >
                  <Play className="h-4 w-4" />
                  Run QA Analysis
                </Button>

                {pdfFile && isValidUrl(targetUrl) && (
                  <motion.p
                    initial={{ opacity: 0 }}
                    animate={{ opacity: 1 }}
                    className="text-xs text-white/20 leading-relaxed"
                  >
                    The engine will extract text from pages{' '}
                    <span className="text-white/40 tabular-nums">{pageRangeStart}</span>
                    –
                    <span className="text-white/40 tabular-nums">
                      {pageRangeEnd === -1 ? pageCount || '∞' : pageRangeEnd}
                    </span>{' '}
                    of your PDF, scrape the live URL, and run 5 QA checks.
                  </motion.p>
                )}
              </div>
            </div>

            {/* PDF Preview (always shown when PDF uploaded; crop overlay added when active) */}
            <AnimatePresence>
              {pdfFile && (
                <motion.div
                  initial={{ opacity: 0, height: 0 }}
                  animate={{ opacity: 1, height: 'auto' }}
                  exit={{ opacity: 0, height: 0 }}
                  transition={{ duration: 0.4, ease: 'easeInOut' }}
                  className="overflow-hidden mt-8"
                >
                  <div className="border border-white/[0.06] rounded-xl p-6 bg-white/[0.01]">
                    {isCropActive && (
                      <p className="text-xs text-white/30 uppercase tracking-widest mb-4">
                        Drag the lines to set header/footer crop boundaries
                      </p>
                    )}
                    <div className="flex justify-center">
                      <PdfPreview
                        onPageDimensions={(dims) => setPdfPageHeight(dims.height)}
                        overlay={
                          isCropActive && pdfPageHeight > 0 ? (
                            <CropOverlay
                              containerHeightPx={pdfPageHeight}
                              initialTop={cropTop}
                              initialBottom={cropBottom}
                              initialLeft={cropLeft}
                              initialRight={cropRight}
                              onCropChange={(top, bottom, left, right) => setCrop(top, bottom, left, right)}
                            />
                          ) : null
                        }
                      />
                    </div>
                  </div>
                </motion.div>
              )}
            </AnimatePresence>
          </motion.div>
        )}

        {/* ════════════════════════════════════════════ */}
        {/*  STATE 2 — PROCESSING VIEW                  */}
        {/* ════════════════════════════════════════════ */}
        {viewState === 'PROCESSING' && (
          <motion.div
            key="processing"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            className="max-w-2xl mx-auto px-6 py-16"
          >
            <JobProgress />
          </motion.div>
        )}

        {/* ════════════════════════════════════════════ */}
        {/*  STATE 3 — RESULTS VIEW                     */}
        {/* ════════════════════════════════════════════ */}
        {viewState === 'RESULTS' && results && (
          <motion.div
            key="results"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            className="min-h-screen"
          >
            {/* FAILED state */}
            {results.status === 'FAILED' && (
              <div className="max-w-2xl mx-auto px-6 py-20">
                <motion.div
                  initial={{ opacity: 0, y: 20 }}
                  animate={{ opacity: 1, y: 0 }}
                  className="flex flex-col items-center text-center"
                >
                  <div className="h-16 w-16 rounded-2xl bg-red-500/10 flex items-center justify-center mb-6">
                    <AlertCircle className="h-8 w-8 text-red-400" />
                  </div>
                  <h2 className="text-xl font-light text-white mb-2">
                    Analysis Failed
                  </h2>
                  <p className="text-sm text-white/40 mb-6 max-w-md">
                    {results.error || 'An unexpected error occurred during processing.'}
                  </p>
                  <Button variant="secondary" onClick={reset}>
                    <RotateCcw className="h-4 w-4" />
                    New Analysis
                  </Button>
                </motion.div>
              </div>
            )}

            {/* SUCCESS state */}
            {results.status === 'COMPLETE' && results.summary && (
              <div className="max-w-5xl mx-auto px-6 py-8">
                {/* ── Sticky top bar ── */}
                <div className="sticky top-0 z-30 bg-[#0a0a0a]/90 backdrop-blur-xl pb-6 -mx-6 px-6 pt-4 border-b border-white/[0.04]">
                  <div className="flex items-center justify-between mb-6">
                    <div className="flex items-center gap-3">
                      <h1 className="text-xl font-light text-white">
                        QA Report
                      </h1>
                      <Badge severity={overallSeverity} size="sm" />
                    </div>
                    <div className="flex items-center gap-2">
                      <Button variant="ghost" size="sm" onClick={handleDownload}>
                        <Download className="h-3.5 w-3.5" />
                        Export JSON
                      </Button>
                      <Button variant="secondary" size="sm" onClick={reset}>
                        <RotateCcw className="h-3.5 w-3.5" />
                        New Analysis
                      </Button>
                    </div>
                  </div>

                  {/* Meta info */}
                  {results.web_source && (
                    <p className="text-xs text-white/20 mb-4">
                      {results.brand} · {results.pdf_source} ·{' '}
                      <a
                        href={results.web_source}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="text-blue-400/60 hover:text-blue-400 transition-colors"
                      >
                        {results.web_source}
                      </a>
                      {results.run_date && ` · ${results.run_date}`}
                    </p>
                  )}

                  {/* 5 Summary cards */}
                  <ReportSummary
                    summary={results.summary}
                    activeFilter={activeFilter}
                    onFilter={(f: QAFilterOption) => setFilter(f)}
                  />
                </div>

                {/* ── Issues list ── */}
                <div className="mt-6 space-y-3">
                  {/* All clear state */}
                  {results.issues?.length === 0 && (
                    <motion.div
                      initial={{ opacity: 0, scale: 0.95 }}
                      animate={{ opacity: 1, scale: 1 }}
                      className="flex flex-col items-center py-20 text-center
                                 rounded-2xl border-2 border-green-500/20 bg-green-500/[0.03]"
                    >
                      <div className="h-16 w-16 rounded-2xl bg-green-500/10
                                      flex items-center justify-center mb-6">
                        <CheckCircle2 className="h-8 w-8 text-green-400" />
                      </div>
                      <h2 className="text-xl font-light text-green-300 mb-2">
                        Everything matches
                      </h2>
                      <p className="text-sm text-green-400/50">
                        No changes needed. The website content matches the PDF exactly.
                      </p>
                    </motion.div>
                  )}

                  {/* No results for current filter */}
                  {filteredIssues.length === 0 &&
                    results.issues &&
                    results.issues.length > 0 && (
                      <motion.div
                        initial={{ opacity: 0 }}
                        animate={{ opacity: 1 }}
                        className="flex flex-col items-center py-16"
                      >
                        <AlertCircle className="h-8 w-8 text-white/10 mb-3" />
                        <p className="text-sm text-white/30">
                          No issues match the selected filter
                        </p>
                      </motion.div>
                    )}

                  {/* Issue cards */}
                  <AnimatePresence>
                    {filteredIssues.map((issue, i) => (
                      <IssueCard
                        key={issue.id}
                        issue={issue}
                        index={i}
                      />
                    ))}
                  </AnimatePresence>
                </div>
              </div>
            )}
          </motion.div>
        )}
      </AnimatePresence>
    </main>
  )
}
